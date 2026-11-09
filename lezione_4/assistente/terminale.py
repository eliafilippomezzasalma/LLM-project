"""Interfaccia da terminale: legge le domande, stampa le risposte, gestisce uscita ed errori."""

import logging
import sys
from collections.abc import Callable

import openai
from mcp import StdioServerParameters

from assistente.config import Config, ErroreConfigurazione, carica_config
from assistente.grafo import costruisci_grafo
from assistente.log import configura_log
from assistente.mcp_remoto import (
    ClientMCP,
    ErroreMCP,
    parametri_calcolatrice,
    parametri_convertitore,
    parametri_scadenze,
)
from assistente.modello import crea_modello
from assistente.nota import NotaNonNormativa, con_nota
from assistente.orologio import crea_orologio
from assistente.sessione import LimitePassaggiRaggiunto, Sessione
from assistente.strumenti import crea_registro

log = logging.getLogger("sessione")

AIUTO = "Scrivi la tua domanda. Per uscire: esci, exit, Ctrl+D o Ctrl+C."
COMANDI_USCITA = {"esci", "exit"}
AVVISO_LIMITE = "Limite di passaggi raggiunto, riprova riformulando la domanda."


def esegui_chat(
    sessione: Sessione,
    intestazione: str,
    indirizzo: str,
    leggi: Callable[[str], str] = input,
    scrivi: Callable[[str], None] = print,
) -> None:
    """Ciclo Tu>/Assistente> fino all'uscita; gli errori di un turno non chiudono la chat."""
    scrivi(intestazione)
    scrivi(AIUTO)
    try:
        while True:
            domanda = leggi("Tu> ").strip()
            if not domanda:
                continue
            if domanda.lower() in COMANDI_USCITA:
                scrivi("Ciao!")
                return
            scrivi("(sto pensando...)")
            try:
                scrivi(f"Assistente> {sessione.chiedi(domanda)}")
            except LimitePassaggiRaggiunto:
                log.warning("limite di passaggi raggiunto")
                scrivi(AVVISO_LIMITE)
            except openai.APIStatusError as errore:
                # Il server ha risposto, ma con un errore (es. cronologia oltre il contesto).
                log.warning("errore del modello: HTTP %s %s", errore.status_code, errore.message)
                scrivi(f"Errore dal modello (HTTP {errore.status_code}): {errore.message}")
            except Exception as errore:
                # Connessione fallita o risposta non valida (es. LM_BASE_URL senza /v1).
                log.warning("errore del modello: %s", errore)
                log.debug("dettaglio dell'errore", exc_info=True)
                scrivi(f"Impossibile contattare il modello su {indirizzo}: {errore}")
    except (EOFError, KeyboardInterrupt):
        scrivi("\nCiao!")


def _collega(nome: str, parametri: StdioServerParameters) -> ClientMCP | None:
    """Avvia un server MCP; None se non parte: la chat va avanti senza."""
    try:
        return ClientMCP.apri(parametri)
    except ErroreMCP as errore:
        log.warning("%s MCP non disponibile: %s", nome, errore)
        return None


def collega_convertitore(parametri: StdioServerParameters | None = None) -> ClientMCP | None:
    """Avvia il convertitore di unità (server MCP); None se non parte."""
    return _collega("convertitore", parametri or parametri_convertitore())


def collega_calcolatrice(parametri: StdioServerParameters | None = None) -> ClientMCP | None:
    """Avvia la calcolatrice sicura (server MCP); None se non parte."""
    return _collega("calcolatrice", parametri or parametri_calcolatrice())


def collega_scadenze(parametri: StdioServerParameters | None = None) -> ClientMCP | None:
    """Avvia il server di giorni e scadenze (server MCP); None se non parte."""
    return _collega("scadenze", parametri or parametri_scadenze())


def intestazione(config: Config, convertitore: bool, calcolatrice: bool, scadenze: bool) -> str:
    """Le quattro righe iniziali: modello e stato dei tre server MCP."""
    stato = {True: "attivo", False: "non disponibile"}
    return (
        f"Assistente del laboratorio — modello: {config.lm_model} @ {config.lm_base_url}\n"
        f"Convertitore di unità (MCP): {stato[convertitore]}\n"
        f"Calcolatrice (MCP): {stato[calcolatrice]}\n"
        f"Giorni e scadenze (MCP): {stato[scadenze]}"
    )


def _usa_utf8() -> None:
    # Su Windows, con output rediretto, Python userebbe cp1252 e rovinerebbe «—» e «lunedì».
    for flusso in (sys.stdout, sys.stderr):
        flusso.reconfigure(encoding="utf-8")


def main() -> int:
    """Avvia l'assistente: configurazione, log, strumenti (anche via MCP), modello, grafo e chat."""
    _usa_utf8()
    try:
        config = carica_config()
    except ErroreConfigurazione as errore:
        print(f"Configurazione non valida: {errore}", file=sys.stderr)
        return 1
    configura_log(config.log_level)
    convertitore, calcolatrice, scadenze = collega_convertitore(), collega_calcolatrice(), collega_scadenze()
    remoti = [r for r in (convertitore, calcolatrice, scadenze) if r]
    nota = NotaNonNormativa()
    try:
        strumenti = con_nota([crea_orologio(), *(s for r in remoti for s in r.strumenti())], nota)
        modello = crea_modello(config, strumenti)
        grafo = costruisci_grafo(modello, crea_registro(strumenti), config.max_tool_steps)
        testo = intestazione(config, convertitore is not None, calcolatrice is not None, scadenze is not None)
        esegui_chat(Sessione(grafo, nota), testo, config.lm_base_url)
    finally:
        for remoto in remoti:
            remoto.chiudi()
    return 0
