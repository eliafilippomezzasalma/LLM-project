"""Router d'ambito: un modello classifica la domanda prima che parta l'agente."""

import logging
from typing import Literal

from langchain_core.messages import AIMessage, AnyMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from assistente.config import Config
from assistente.modello import CHIAVE_SEGNAPOSTO, RAGIONAMENTO_DISATTIVATO

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
- Il motivo è una frase breve."""


class Classificazione(BaseModel):
    """Esito del router: il motivo viene prima, così il modello ragiona prima di scegliere."""

    motivo: str = Field(min_length=1)
    categoria: Literal["conversazione", "fuori_ambito"]


def messaggi_per_router(messaggi: list[AnyMessage], ambito: str) -> list[BaseMessage]:
    """Istruzioni del router più le sole domande e risposte in testo della cronologia."""
    contesto: list[BaseMessage] = []
    for m in messaggi:
        if isinstance(m, HumanMessage):
            contesto.append(m)
        elif isinstance(m, AIMessage) and not m.tool_calls and m.content:
            contesto.append(m)
    return [SystemMessage(ISTRUZIONI_ROUTER.format(ambito=ambito)), *contesto]


def classifica(router: Runnable, messaggi: list[AnyMessage], ambito: str) -> Classificazione | None:
    """Classifica l'ultima domanda; None se il router fallisce (si procede verso l'agente)."""
    inviati = messaggi_per_router(messaggi, ambito)
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
