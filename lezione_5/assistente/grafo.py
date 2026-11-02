"""Grafo LangGraph esplicito: nodo «modello», nodo «strumenti» e instradamento tra i due.

    START → modello ──(tool_call e passi < limite)──→ strumenti → modello
                     └─(nessuna tool_call o limite)──→ END
"""

import logging
import time
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from assistente.strumenti import esegui_chiamate

log = logging.getLogger("modello")


class StatoAssistente(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    passi_strumento: int  # giri modello→strumenti nel turno corrente


def _chiede_strumenti(messaggio: AnyMessage) -> bool:
    return isinstance(messaggio, AIMessage) and bool(
        messaggio.tool_calls or messaggio.invalid_tool_calls
    )


def instrada(stato: StatoAssistente, max_passi: int) -> Literal["strumenti", "fine"]:
    """Dopo il modello: agli strumenti se li ha chiesti e il limite non è raggiunto."""
    if _chiede_strumenti(stato["messages"][-1]) and stato["passi_strumento"] < max_passi:
        return "strumenti"
    return "fine"


def limite_raggiunto(stato: StatoAssistente) -> bool:
    """Vero se il grafo è terminato mentre il modello chiedeva ancora uno strumento."""
    return _chiede_strumenti(stato["messages"][-1])


def costruisci_grafo(modello: Runnable, registro: dict[str, BaseTool], max_passi: int):
    """Costruisce e compila il grafo; modello e strumenti arrivano dall'esterno."""

    def nodo_modello(stato: StatoAssistente) -> dict:
        log.debug("messaggi inviati: %s", [(m.type, m.text) for m in stato["messages"]])
        inizio = time.perf_counter()
        try:
            risposta = modello.invoke(stato["messages"])
        except Exception:
            log.debug("chiamata -> errore (%.1fs)", time.perf_counter() - inizio)
            raise
        esito = "richiesta strumento" if _chiede_strumenti(risposta) else "risposta finale"
        log.debug("chiamata -> %s (%.1fs)", esito, time.perf_counter() - inizio)
        ragionamento = risposta.additional_kwargs.get("reasoning_content")
        if ragionamento:
            log.debug("ragionamento: %s", ragionamento)
        return {"messages": [risposta]}

    def nodo_strumenti(stato: StatoAssistente) -> dict:
        passo = stato["passi_strumento"] + 1
        risposte = esegui_chiamate(registro, stato["messages"][-1], passo, max_passi)
        return {"messages": risposte, "passi_strumento": passo}

    grafo = StateGraph(StatoAssistente)
    grafo.add_node("modello", nodo_modello)
    grafo.add_node("strumenti", nodo_strumenti)
    grafo.add_edge(START, "modello")
    grafo.add_conditional_edges(
        "modello",
        lambda stato: instrada(stato, max_passi),
        {"strumenti": "strumenti", "fine": END},
    )
    grafo.add_edge("strumenti", "modello")
    # Ogni passaggio usa due super-step (modello + strumenti): il limite di ricorsione
    # di LangGraph deve stare sopra al nostro limite, altrimenti scatterebbe prima.
    return grafo.compile().with_config(recursion_limit=2 * max_passi + 5)
