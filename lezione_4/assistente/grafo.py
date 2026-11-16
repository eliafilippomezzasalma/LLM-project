"""Grafo LangGraph esplicito: router d'ambito, agente con strumenti, revisore della risposta, rifiuto fisso.

    START → router ──(fuori_ambito)──→ rifiuto → END
                  └─(conversazione o router non valido)──→ agente ⇄ strumenti
                                                            │ (risposta finale)
                                                            ▼
                                                        revisore ──(coerente, revisore non valido,
                                                            │       o limite revisioni)──→ END
                                                            └─(non coerente, sotto il limite)──→ agente

    Limite degli strumenti: al primo tentativo del turno → END (LimitePassaggiRaggiunto in Sessione);
    in un tentativo dopo una revisione → ultima_risposta (l'ultima risposta proposta) → END.
    Errore del modello: al primo tentativo l'eccezione arriva al chiamante; in un tentativo dopo
    una revisione l'agente restituisce l'ultima risposta proposta e si va a END senza revisore.
    Domanda mista (in ambito con parti fuori ambito): il router mette in `mista` la domanda ridotta,
    che il revisore vede al posto di quella intera; l'agente vede sempre la domanda intera.
"""

import logging
import time
from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from assistente.revisore import indicazione, respinta, rivedi
from assistente.router import FUORI_AMBITO, DomandaMista, classifica, domanda_mista
from assistente.strumenti import esegui_chiamate

log_agente = logging.getLogger("agente")
log_router = logging.getLogger("router")
log_rifiuto = logging.getLogger("rifiuto")
log_revisore = logging.getLogger("revisore")


class StatoAssistente(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    passi_strumento: int  # giri agente→strumenti nel turno corrente
    categoria: NotRequired[str | None]  # esito del router; None se il router non ha risposto
    motivo: NotRequired[str | None]
    inizio_turno: NotRequired[int]  # indice della domanda del turno nei messaggi (impostato dal router)
    revisioni: NotRequired[int]  # risposte giudicate non coerenti nel turno corrente
    coerente: NotRequired[bool | None]  # decisione effettiva sull'ultima risposta (False solo se respinta con una regola); None se il revisore non ha risposto
    ultima_proposta: NotRequired[AIMessage | None]  # ultima risposta rifiutata, per il limite degli strumenti
    errore_agente: NotRequired[bool]  # il modello ha fallito dopo una revisione: restituita l'ultima proposta
    mista: NotRequired[DomandaMista | None]  # domanda mista: al revisore solo le parti in ambito (dal router)


def _chiede_strumenti(messaggio: AnyMessage) -> bool:
    return isinstance(messaggio, AIMessage) and bool(
        messaggio.tool_calls or messaggio.invalid_tool_calls
    )


def dopo_router(stato: StatoAssistente) -> Literal["agente", "rifiuto"]:
    """Dopo il router: rifiuto solo se la domanda è fuori ambito; nel dubbio, l'agente."""
    return "rifiuto" if stato.get("categoria") == FUORI_AMBITO else "agente"


def instrada(
    stato: StatoAssistente, max_passi: int
) -> Literal["strumenti", "revisore", "ultima_risposta", "fine"]:
    """Dopo l'agente: strumenti se li chiede e c'è ancora passo, revisore se la risposta è finale.

    Al limite degli strumenti non si passa dal revisore: se il turno ha già una risposta
    proposta (tentativo dopo una revisione) si restituisce quella, altrimenti si termina.
    Se il modello ha fallito dopo una revisione, l'agente ha già restituito l'ultima risposta
    proposta: si termina senza giudicarla di nuovo.
    """
    if stato.get("errore_agente"):
        return "fine"
    if not _chiede_strumenti(stato["messages"][-1]):
        return "revisore"
    if stato["passi_strumento"] < max_passi:
        return "strumenti"
    return "ultima_risposta" if stato.get("ultima_proposta") else "fine"


def dopo_revisore(stato: StatoAssistente, max_revisioni: int) -> Literal["agente", "fine"]:
    """Dopo il revisore: di nuovo all'agente solo se la risposta non è coerente e c'è ancora revisione."""
    if stato.get("coerente") is False and stato.get("revisioni", 0) <= max_revisioni:
        return "agente"
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
    revisore: Runnable,
    max_revisioni: int,
):
    """Costruisce e compila il grafo; modello, router, revisore e strumenti arrivano dall'esterno."""

    def nodo_router(stato: StatoAssistente) -> dict:
        # Il router apre il turno: azzera lo stato del revisore e segna dove inizia il turno.
        turno = {
            "inizio_turno": len(stato["messages"]) - 1,
            "revisioni": 0,
            "coerente": None,
            "ultima_proposta": None,
            "errore_agente": False,
            "mista": None,
        }
        esito = classifica(router, stato["messages"], ambito)
        if esito is None:  # classifica ha già registrato l'avviso
            return {**turno, "categoria": None, "motivo": None}
        destinazione = dopo_router({"categoria": esito.categoria})
        log_router.info(
            'categoria=%s motivo="%s" -> %s', esito.categoria, " ".join(esito.motivo.split()), destinazione
        )
        mista = domanda_mista(esito, str(stato["messages"][-1].content))
        if mista is not None:
            log_router.info(
                'domanda mista: al revisore solo "%s" (escluse: "%s")',
                mista.domanda_in_ambito, "; ".join(" ".join(p.split()) for p in mista.parti_fuori_ambito),
            )
        return {**turno, "categoria": esito.categoria, "motivo": esito.motivo, "mista": mista}

    def nodo_rifiuto(stato: StatoAssistente) -> dict:
        log_rifiuto.info("risposta fissa")
        return {"messages": [AIMessage(messaggio_rifiuto)]}

    def nodo_agente(stato: StatoAssistente) -> dict:
        log_agente.info("chiamata %d", stato["passi_strumento"] + 1)
        log_agente.debug("messaggi inviati: %s", [(m.type, m.text) for m in stato["messages"]])
        inizio = time.perf_counter()
        try:
            risposta = modello.invoke(stato["messages"])
        except Exception as errore:
            log_agente.debug("chiamata -> errore (%.1fs)", time.perf_counter() - inizio)
            if not stato.get("ultima_proposta"):
                raise
            log_revisore.warning(
                "errore del modello nel tentativo dopo la revisione (%s: %s), restituita l'ultima risposta",
                type(errore).__name__, " ".join(str(errore).split()),
            )
            # Senza id: add_messages la aggiunge in coda invece di sostituire quella già nei messaggi.
            return {
                "messages": [stato["ultima_proposta"].model_copy(update={"id": None})],
                "errore_agente": True,
            }
        esito = "richiesta strumento" if _chiede_strumenti(risposta) else "risposta finale"
        log_agente.debug("chiamata -> %s (%.1fs)", esito, time.perf_counter() - inizio)
        ragionamento = risposta.additional_kwargs.get("reasoning_content")
        if ragionamento:
            log_agente.debug("ragionamento: %s", ragionamento)
        if _chiede_strumenti(risposta) and risposta.text.strip():
            # L'utente vede solo la risposta finale: se il modello rivedesse risultati scritti
            # insieme alle chiamate, nella risposta finale riporterebbe solo quelli mancanti.
            log_agente.debug("testo insieme alle chiamate, tolto: %s", risposta.text)
            risposta = risposta.model_copy(update={"content": ""})
        return {"messages": [risposta]}

    def nodo_strumenti(stato: StatoAssistente) -> dict:
        passo = stato["passi_strumento"] + 1
        risposte = esegui_chiamate(registro, stato["messages"][-1], passo, max_passi)
        return {"messages": risposte, "passi_strumento": passo}

    def nodo_revisore(stato: StatoAssistente) -> dict:
        giudizio = rivedi(revisore, stato["messages"], stato["inizio_turno"], ambito, stato.get("mista"))
        if giudizio is None:  # rivedi ha già registrato l'avviso: la risposta passa com'è
            return {"coerente": None}
        motivo = " ".join(giudizio.motivo.split())
        regola = giudizio.regola
        if giudizio.coerente:
            log_revisore.info('coerente=sì regola=%s motivo="%s" -> fine', regola, motivo)
            return {"coerente": True}
        if not respinta(giudizio):
            # Rifiuto senza una delle tre regole: conta come approvazione, le revisioni non aumentano.
            log_revisore.info(
                'coerente=no regola=%s motivo="%s" -> fine (rifiuto senza regola, trattato come coerente)',
                regola, motivo,
            )
            return {"coerente": True}
        revisioni = stato.get("revisioni", 0) + 1
        if dopo_revisore({"coerente": False, "revisioni": revisioni}, max_revisioni) == "fine":
            log_revisore.info('coerente=no regola=%s motivo="%s" -> fine', regola, motivo)
            log_revisore.warning("limite di %d revisioni raggiunto, restituita l'ultima risposta", max_revisioni)
            return {"coerente": False, "revisioni": revisioni}
        log_revisore.info(
            'coerente=no regola=%s motivo="%s" -> agente (revisione %d/%d)',
            regola, motivo, revisioni, max_revisioni,
        )
        # Ogni tentativo dell'agente ha i suoi passaggi agli strumenti (passi_strumento azzerato).
        return {
            "coerente": False,
            "revisioni": revisioni,
            "messages": [indicazione(giudizio.motivo, regola)],
            "passi_strumento": 0,
            "ultima_proposta": stato["messages"][-1],
        }

    def nodo_ultima_risposta(stato: StatoAssistente) -> dict:
        log_revisore.warning(
            "limite degli strumenti nel tentativo dopo la revisione, restituita l'ultima risposta"
        )
        # Senza id: add_messages la aggiunge in coda invece di sostituire quella già nei messaggi.
        return {"messages": [stato["ultima_proposta"].model_copy(update={"id": None})]}

    grafo = StateGraph(StatoAssistente)
    grafo.add_node("router", nodo_router)
    grafo.add_node("agente", nodo_agente)
    grafo.add_node("strumenti", nodo_strumenti)
    grafo.add_node("rifiuto", nodo_rifiuto)
    grafo.add_node("revisore", nodo_revisore)
    grafo.add_node("ultima_risposta", nodo_ultima_risposta)
    grafo.add_edge(START, "router")
    grafo.add_conditional_edges("router", dopo_router, {"agente": "agente", "rifiuto": "rifiuto"})
    grafo.add_edge("rifiuto", END)
    grafo.add_conditional_edges(
        "agente",
        lambda stato: instrada(stato, max_passi),
        {"strumenti": "strumenti", "revisore": "revisore", "ultima_risposta": "ultima_risposta", "fine": END},
    )
    grafo.add_edge("strumenti", "agente")
    grafo.add_conditional_edges(
        "revisore",
        lambda stato: dopo_revisore(stato, max_revisioni),
        {"agente": "agente", "fine": END},
    )
    grafo.add_edge("ultima_risposta", END)
    # Fino a max_revisioni + 1 tentativi; ognuno usa due super-step per passaggio agli strumenti
    # (agente + strumenti) più la risposta finale e il revisore; poi router e margine. Il limite
    # di ricorsione di LangGraph deve stare sopra ai nostri limiti, altrimenti scatterebbe prima.
    return grafo.compile().with_config(recursion_limit=(max_revisioni + 1) * (2 * max_passi + 2) + 6)
