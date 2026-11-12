"""Grafo LangGraph esplicito: router d'ambito, agente con strumenti, rifiuto a risposta fissa.

    START → router ──(fuori_ambito)──→ rifiuto → END
                  └─(conversazione o router non valido)──→ agente ──(tool_call e passi < limite)──→ strumenti → agente
                                                                  └─(nessuna tool_call o limite)──→ END
"""

import logging
import time
from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from assistente.router import FUORI_AMBITO, classifica
from assistente.strumenti import esegui_chiamate

log_agente = logging.getLogger("agente")
log_router = logging.getLogger("router")
log_rifiuto = logging.getLogger("rifiuto")


class StatoAssistente(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    passi_strumento: int  # giri agente→strumenti nel turno corrente
    categoria: NotRequired[str | None]  # esito del router; None se il router non ha risposto
    motivo: NotRequired[str | None]


def _chiede_strumenti(messaggio: AnyMessage) -> bool:
    return isinstance(messaggio, AIMessage) and bool(
        messaggio.tool_calls or messaggio.invalid_tool_calls
    )


def dopo_router(stato: StatoAssistente) -> Literal["agente", "rifiuto"]:
    """Dopo il router: rifiuto solo se la domanda è fuori ambito; nel dubbio, l'agente."""
    return "rifiuto" if stato.get("categoria") == FUORI_AMBITO else "agente"


def instrada(stato: StatoAssistente, max_passi: int) -> Literal["strumenti", "fine"]:
    """Dopo l'agente: agli strumenti se li ha chiesti e il limite non è raggiunto."""
    if _chiede_strumenti(stato["messages"][-1]) and stato["passi_strumento"] < max_passi:
        return "strumenti"
    return "fine"


def limite_raggiunto(stato: StatoAssistente) -> bool:
    """Vero se il grafo è terminato mentre il modello chiedeva ancora uno strumento."""
    return _chiede_strumenti(stato["messages"][-1])


def costruisci_grafo(
    modello: Runnable,
    registro: dict[str, BaseTool],
    max_passi: int,
    *,
    router: Runnable,
    ambito: str,
    messaggio_rifiuto: str,
):
    """Costruisce e compila il grafo; modello, router e strumenti arrivano dall'esterno."""

    def nodo_router(stato: StatoAssistente) -> dict:
        esito = classifica(router, stato["messages"], ambito)
        if esito is None:  # classifica ha già registrato l'avviso
            return {"categoria": None, "motivo": None}
        destinazione = dopo_router({"categoria": esito.categoria})
        log_router.info(
            'categoria=%s motivo="%s" -> %s', esito.categoria, " ".join(esito.motivo.split()), destinazione
        )
        return {"categoria": esito.categoria, "motivo": esito.motivo}

    def nodo_rifiuto(stato: StatoAssistente) -> dict:
        log_rifiuto.info("risposta fissa")
        return {"messages": [AIMessage(messaggio_rifiuto)]}

    def nodo_agente(stato: StatoAssistente) -> dict:
        log_agente.info("chiamata %d", stato["passi_strumento"] + 1)
        log_agente.debug("messaggi inviati: %s", [(m.type, m.text) for m in stato["messages"]])
        inizio = time.perf_counter()
        try:
            risposta = modello.invoke(stato["messages"])
        except Exception:
            log_agente.debug("chiamata -> errore (%.1fs)", time.perf_counter() - inizio)
            raise
        esito = "richiesta strumento" if _chiede_strumenti(risposta) else "risposta finale"
        log_agente.debug("chiamata -> %s (%.1fs)", esito, time.perf_counter() - inizio)
        ragionamento = risposta.additional_kwargs.get("reasoning_content")
        if ragionamento:
            log_agente.debug("ragionamento: %s", ragionamento)
        return {"messages": [risposta]}

    def nodo_strumenti(stato: StatoAssistente) -> dict:
        passo = stato["passi_strumento"] + 1
        risposte = esegui_chiamate(registro, stato["messages"][-1], passo, max_passi)
        return {"messages": risposte, "passi_strumento": passo}

    grafo = StateGraph(StatoAssistente)
    grafo.add_node("router", nodo_router)
    grafo.add_node("agente", nodo_agente)
    grafo.add_node("strumenti", nodo_strumenti)
    grafo.add_node("rifiuto", nodo_rifiuto)
    grafo.add_edge(START, "router")
    grafo.add_conditional_edges("router", dopo_router, {"agente": "agente", "rifiuto": "rifiuto"})
    grafo.add_edge("rifiuto", END)
    grafo.add_conditional_edges(
        "agente",
        lambda stato: instrada(stato, max_passi),
        {"strumenti": "strumenti", "fine": END},
    )
    grafo.add_edge("strumenti", "agente")
    # Ogni passaggio usa due super-step (agente + strumenti), più il router iniziale: il limite
    # di ricorsione di LangGraph deve stare sopra al nostro limite, altrimenti scatterebbe prima.
    return grafo.compile().with_config(recursion_limit=2 * max_passi + 7)
