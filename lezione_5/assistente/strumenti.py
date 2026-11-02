"""Registro degli strumenti ed esecuzione sicura delle chiamate richieste dal modello."""

import json
import logging

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool
from pydantic import ValidationError

log = logging.getLogger("strumenti")


def crea_registro(strumenti: list[BaseTool]) -> dict[str, BaseTool]:
    """Associa a ogni nome di strumento lo strumento stesso."""
    return {strumento.name: strumento for strumento in strumenti}


def _errore_argomenti(strumento: BaseTool) -> str:
    nomi = ", ".join(strumento.args)
    return f"Errore: argomento '{nomi}' mancante o non valido"


def _esegui(registro: dict[str, BaseTool], nome: str, args, valida: bool) -> tuple[str, int]:
    """Esegue una chiamata; restituisce (testo per il modello, livello di log)."""
    strumento = registro.get(nome)
    if strumento is None:
        return f"Errore: strumento '{nome}' non disponibile", logging.WARNING
    if not valida:
        return _errore_argomenti(strumento), logging.WARNING
    try:
        risultato = str(strumento.invoke(args))
    except ValidationError:
        return _errore_argomenti(strumento), logging.WARNING
    except Exception as errore:  # uno strumento non deve mai far cadere la chat
        log.error("strumento %s fallito: %r", nome, errore)
        return "Errore: esecuzione dello strumento non riuscita", logging.ERROR
    livello = logging.WARNING if risultato.startswith("Errore:") else logging.INFO
    return risultato, livello


def esegui_chiamate(
    registro: dict[str, BaseTool], messaggio: AIMessage, passo: int, max_passi: int
) -> list[ToolMessage]:
    """Esegue in ordine tutte le chiamate (valide e non) di un messaggio del modello."""
    chiamate = [(c, True) for c in messaggio.tool_calls]
    chiamate += [(c, False) for c in messaggio.invalid_tool_calls]
    risposte = []
    for chiamata, valida in chiamate:
        nome = chiamata.get("name") or "?"
        args = chiamata.get("args")
        testo, livello = _esegui(registro, nome, args, valida)
        if livello != logging.ERROR:  # gli errori sono già registrati con il dettaglio
            args_log = json.dumps(args, ensure_ascii=False) if valida else args
            log.log(livello, "passo %d/%d %s %s -> %s", passo, max_passi, nome, args_log, testo)
        risposte.append(ToolMessage(content=testo, tool_call_id=chiamata.get("id") or "", name=nome))
    return risposte
