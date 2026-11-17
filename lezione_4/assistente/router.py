"""Router d'ambito: un modello classifica la domanda prima che parta l'agente."""

import logging
import re
from typing import Literal, NamedTuple

from langchain_core.messages import AIMessage, AnyMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from assistente.config import Config
from assistente.modello import CHIAVE_SEGNAPOSTO, RAGIONAMENTO_DISATTIVATO
from assistente.riassunto import testo_con_riassunto

log = logging.getLogger("router")

CONVERSAZIONE = "conversazione"
FUORI_AMBITO = "fuori_ambito"
TIMEOUT_ROUTER_SECONDI = 60

ISTRUZIONI_ROUTER = """Sei il router di un assistente. Il tuo unico compito è decidere se l'ultimo messaggio dell'utente rientra nell'ambito dell'assistente.
Ambito dell'assistente: {ambito}

Categorie:
- conversazione: la richiesta rientra nell'ambito indicato. Sono conversazione anche i saluti, i ringraziamenti e le domande su che cosa sa fare l'assistente, e nient'altro: «conversazione» non vuol dire chiacchiera libera.
- fuori_ambito: tutto ciò che non rientra nell'ambito indicato, anche quando è una richiesta cortese, leggera o di svago.

Regole:
- Prima scrivi il motivo: indica a quale parte dell'ambito appartiene la richiesta, oppure che non appartiene a nessuna. Poi scegli la categoria coerente con il motivo.
- Classifica solo in base all'ambito indicato, non alla tua opinione su che cosa sia utile.
- Un seguito («e a Tokyo?», «e 3 km?», «e quella dell'amatriciana?») prende la categoria della domanda precedente a cui si riferisce: guarda la cronologia.
- Una domanda mista con almeno una parte in ambito è conversazione.
- Il motivo è una frase breve.
- Poi scrivi in parti_fuori_ambito le parti della richiesta che sono fuori ambito (lista vuota se non ce ne sono) e in domanda_in_ambito la richiesta riscritta con le sole parti in ambito, con le stesse parole dell'utente (uguale all'originale se è tutta in ambito, vuota se è tutta fuori ambito).
- Le parti fuori ambito si prendono solo dall'ultimo messaggio dell'utente: quelle dei turni precedenti sono già state gestite e non vanno ripetute. Se l'ultimo messaggio non chiede nulla fuori ambito, parti_fuori_ambito è una lista vuota."""


class Classificazione(BaseModel):
    """Esito del router: il motivo viene prima, così il modello ragiona prima di scegliere.

    parti_fuori_ambito e domanda_in_ambito servono al revisore nelle domande miste (specs §18.4).
    """

    motivo: str = Field(min_length=1)
    # Obbligatorie, senza valore predefinito: con un default lo schema JSON le renderebbe facoltative.
    parti_fuori_ambito: list[str]
    domanda_in_ambito: str
    categoria: Literal["conversazione", "fuori_ambito"]


class DomandaMista(NamedTuple):
    """Domanda ridotta alle parti in ambito e parti escluse, da mostrare al revisore."""

    domanda_in_ambito: str
    parti_fuori_ambito: list[str]


def _parole(testo: str) -> list[str]:
    """Le parole del testo in minuscolo, senza punteggiatura né spazi in più."""
    return re.findall(r"\w+", testo.lower())


def domanda_mista(esito: Classificazione, domanda_utente: str) -> DomandaMista | None:
    """La riduzione della domanda se è mista (in ambito con parti fuori ambito); altrimenti None.

    Se la domanda ridotta coincide con quella dell'utente non è stato escluso nulla: le parti
    «fuori ambito» vengono da un turno precedente (misura g8, specs §17.4) e la domanda non è mista.
    """
    fuori = [parte.strip() for parte in esito.parti_fuori_ambito if parte.strip()]
    domanda = " ".join(esito.domanda_in_ambito.split())
    if esito.categoria != CONVERSAZIONE or not fuori or not domanda:
        return None
    if _parole(domanda) == _parole(domanda_utente):
        return None
    return DomandaMista(domanda, fuori)


def messaggi_per_router(messaggi: list[AnyMessage], ambito: str, riassunto: str = "") -> list[BaseMessage]:
    """Istruzioni del router (con il riassunto in coda, se c'è) più le sole domande e risposte in testo della cronologia."""
    contesto: list[BaseMessage] = []
    for m in messaggi:
        if isinstance(m, HumanMessage):
            contesto.append(m)
        elif isinstance(m, AIMessage) and not m.tool_calls and m.content:
            contesto.append(m)
    return [SystemMessage(testo_con_riassunto(ISTRUZIONI_ROUTER.format(ambito=ambito), riassunto)), *contesto]


def classifica(
    router: Runnable, messaggi: list[AnyMessage], ambito: str, riassunto: str = ""
) -> Classificazione | None:
    """Classifica l'ultima domanda; None se il router fallisce (si procede verso l'agente)."""
    inviati = messaggi_per_router(messaggi, ambito, riassunto)
    log.debug("messaggi inviati al router: %s", inviati)
    try:
        esito = router.invoke(inviati)
    except Exception as errore:
        log.warning("risposta non valida (%s: %s) -> agente", type(errore).__name__, errore)
        return None
    if not isinstance(esito, Classificazione):
        log.warning("risposta non valida (%r) -> agente", esito)
        return None
    return esito


def crea_router(config: Config) -> Runnable:
    """Crea il client verso LM Studio che restituisce una Classificazione."""
    chat = ChatOpenAI(
        base_url=config.lm_base_url,
        model=config.lm_model,
        api_key=CHIAVE_SEGNAPOSTO,
        timeout=TIMEOUT_ROUTER_SECONDI,
        max_retries=0,  # niente tentativi ripetuti: allo scadere del timeout si passa subito all'agente
        extra_body=RAGIONAMENTO_DISATTIVATO,
    )
    return chat.with_structured_output(Classificazione, method="json_schema")
