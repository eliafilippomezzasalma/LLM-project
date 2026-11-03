"""Ponte sincrono verso un server MCP avviato come processo figlio (trasporto stdio).

Il client MCP è asincrono, il resto dell'assistente no. Il ponte tiene la sessione MCP
in un thread dedicato con il proprio event loop asyncio: la apre all'avvio, la usa per
tutta la chat e la chiude all'uscita. Gli strumenti remoti diventano normali strumenti
LangChain, così grafo e registro non cambiano.
"""

import asyncio
import logging
import sys
import threading
from concurrent.futures import Future
from pathlib import Path
from typing import Any

import mcp_types as types
from langchain_core.tools import BaseTool, StructuredTool
from mcp import Client, StdioServerParameters

log = logging.getLogger("mcp")

FILE_CONVERTITORE = Path(__file__).resolve().parent.parent / "convertitore.py"
FILE_CALCOLATRICE = Path(__file__).resolve().parent.parent / "calcolatrice.py"
NON_RAGGIUNGIBILE = "Errore: server MCP non raggiungibile"


class ErroreMCP(Exception):
    """Il server MCP non si avvia o non risponde all'apertura della sessione."""


def parametri_convertitore() -> StdioServerParameters:
    """Comando che avvia il convertitore di unità con lo stesso Python dell'assistente."""
    return StdioServerParameters(command=sys.executable, args=[str(FILE_CONVERTITORE)])


def parametri_calcolatrice() -> StdioServerParameters:
    """Comando che avvia la calcolatrice sicura con lo stesso Python dell'assistente."""
    return StdioServerParameters(command=sys.executable, args=[str(FILE_CALCOLATRICE)])


class ClientMCP:
    """Sessione MCP aperta in un thread di sfondo, usabile da codice sincrono."""

    def __init__(self, parametri: StdioServerParameters, timeout: float):
        self._parametri = parametri
        self._timeout = timeout
        self._pronto = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._fine: asyncio.Event | None = None
        self._compito: asyncio.Task | None = None
        self._client: Client | None = None
        self._strumenti: list[types.Tool] = []
        self._errore: BaseException | None = None
        self._thread = threading.Thread(target=self._vivi, name="client-mcp", daemon=True)

    @classmethod
    def apri(cls, parametri: StdioServerParameters, timeout: float = 20.0) -> "ClientMCP":
        """Avvia il server e apre la sessione; ErroreMCP se non riesce entro `timeout`."""
        client = cls(parametri, timeout)
        client._thread.start()
        if not client._pronto.wait(timeout):
            client._annulla()
            raise ErroreMCP(f"il server non ha risposto entro {timeout:g} s")
        if client._errore is not None or not client.attivo:
            client.chiudi()
            raise ErroreMCP(f"avvio del server non riuscito: {client._errore!r}")
        return client

    # ── thread di sfondo ──

    def _vivi(self) -> None:
        try:
            asyncio.run(self._sessione())
        finally:
            self._pronto.set()  # sblocca apri() anche se l'avvio è fallito

    async def _sessione(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._fine = asyncio.Event()
        self._compito = asyncio.current_task()
        try:
            async with Client(self._parametri, read_timeout_seconds=self._timeout) as client:
                self._strumenti = (await client.list_tools()).tools
                self._client = client
                self._pronto.set()
                await self._fine.wait()
        except BaseException as errore:  # noqa: BLE001 - qualunque fallimento chiude la sessione
            if self._client is not None:
                log.warning("sessione MCP interrotta: %r", errore)
            self._errore = errore
        finally:
            self._client = None

    def _annulla(self) -> None:
        if self._loop is not None and self._compito is not None and not self._loop.is_closed():
            try:
                self._loop.call_soon_threadsafe(self._compito.cancel)
            except RuntimeError:  # loop chiuso nel frattempo: il thread sta già finendo
                pass
        if self._thread.is_alive():
            self._thread.join(self._timeout)

    # ── interfaccia sincrona ──

    @property
    def attivo(self) -> bool:
        """Vero finché la sessione è aperta e il thread è vivo."""
        return self._thread.is_alive() and self._client is not None

    def chiama(self, nome: str, argomenti: dict[str, Any], timeout: float = 30.0) -> str:
        """Chiama uno strumento remoto; ogni problema diventa un testo «Errore: ...»."""
        client, loop = self._client, self._loop
        if client is None or loop is None or not self.attivo:
            log.warning("chiamata a %s: %s", nome, NON_RAGGIUNGIBILE)
            return NON_RAGGIUNGIBILE
        futuro: Future | None = None
        try:
            futuro = asyncio.run_coroutine_threadsafe(client.call_tool(nome, argomenti), loop)
            risultato: types.CallToolResult = futuro.result(timeout)
        except Exception as errore:  # server morto, timeout, sessione o loop chiusi
            if futuro is not None:
                futuro.cancel()
            log.warning("chiamata a %s non riuscita: %r", nome, errore)
            return NON_RAGGIUNGIBILE
        testo = "\n".join(c.text for c in risultato.content if isinstance(c, types.TextContent))
        if risultato.is_error and not testo.startswith("Errore:"):
            testo = f"Errore: {testo}"
        return testo

    def strumenti(self) -> list[BaseTool]:
        """Gli strumenti del server come StructuredTool con lo schema JSON originale.

        Con uno schema in forma di dizionario LangChain non rivalida gli argomenti:
        arrivano intatti al server, che è l'unico punto di validazione.
        """
        return [self._crea_strumento(strumento) for strumento in self._strumenti]

    def _crea_strumento(self, strumento: types.Tool) -> BaseTool:
        nome = strumento.name

        def esegui(**argomenti: Any) -> str:
            return self.chiama(nome, argomenti)

        return StructuredTool(
            name=nome,
            description=strumento.description or "",
            args_schema=strumento.input_schema,
            func=esegui,
        )

    def chiudi(self) -> None:
        """Chiude la sessione e il processo del server; si può chiamare più volte."""
        if self._loop is not None and self._fine is not None and not self._loop.is_closed():
            try:
                self._loop.call_soon_threadsafe(self._fine.set)
            except RuntimeError:  # loop chiuso nel frattempo
                pass
        if self._thread.is_alive():
            self._thread.join(self._timeout)
