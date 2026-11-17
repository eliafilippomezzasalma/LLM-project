"""Revisore della risposta: un modello giudica la risposta finale dell'agente prima che arrivi all'utente."""

import json
import logging
import re
from typing import Literal

from langchain_core.messages import AIMessage, AnyMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from assistente.config import Config
from assistente.modello import CHIAVE_SEGNAPOSTO, RAGIONAMENTO_DISATTIVATO, pulisci_ragionamento
from assistente.riassunto import testo_con_riassunto
from assistente.router import DomandaMista

log = logging.getLogger("revisore")

TIMEOUT_REVISORE_SECONDI = 60
PREFISSO_INDICAZIONE = "[Revisione]"
NESSUNA_RISPOSTA = "(nessuna risposta dal modello)"

ISTRUZIONI_REVISORE = """Sei il revisore di un assistente. Giudichi solo l'ultima risposta proposta dall'assistente alla domanda dell'utente: non rispondi tu e non riscrivi la risposta.
Ambito dell'assistente: {ambito}

Ti vengono mostrati la domanda, gli strumenti chiamati in questo turno con i loro risultati, le eventuali indicazioni già date e la risposta proposta. Un seguito («e a Tokyo?», «e 3 km?») va letto nel contesto della cronologia.

La risposta NON è coerente (coerente = false) solo per uno di questi motivi:
1. (completezza) una parte della domanda che rientra nell'ambito è rimasta senza risposta;
2. (contraddizione) un valore della risposta contraddice il risultato di uno strumento;
3. (valore_a_mente) valore «a mente»: la risposta contiene un'ora, una data, una conversione, il risultato di un calcolo o un conteggio di giorni che non compare in nessun risultato degli strumenti di questo turno, anche se è plausibile o giusto. Vale anche quando uno strumento ha dato errore e l'assistente ha fatto il calcolo da solo. Fa eccezione solo un valore ripetuto identico da una risposta precedente della cronologia.

NON sono motivi per giudicarla non coerente:
- non aver risposto a una parte fuori ambito (per esempio ricette, barzellette, sport): è giusto così, non chiederla mai;
- arrotondare un valore degli strumenti, anche con «circa»;
- omettere dettagli secondari di un risultato (secondi, sigla del fuso orario, data di riferimento, espressione calcolata);
- un saluto, un ringraziamento o una presentazione di che cosa sa fare l'assistente, che non contengono valori: sono coerenti se rispondono al messaggio dell'utente;
- spiegare un errore di uno strumento senza dare valori inventati;
- l'assenza di note o avvertenze.

In tutti gli altri casi la risposta è coerente (coerente = true).

Prima scrivi il motivo: una sola frase breve (al massimo 25 parole) che, se la risposta non è coerente, dice che cosa manca o è sbagliato, così l'assistente può correggerla. Poi scrivi in regola il nome della regola violata (completezza, contraddizione o valore_a_mente), oppure nessuna se nessuna delle tre è violata. Infine scegli coerente: false solo se hai indicato una regola."""


class Giudizio(BaseModel):
    """Esito del revisore: motivo, poi regola violata, poi decisione (il modello ragiona prima di scegliere)."""

    motivo: str = Field(min_length=1)
    # Obbligatoria, senza valore predefinito: con un default lo schema JSON la renderebbe facoltativa.
    regola: Literal["nessuna", "completezza", "contraddizione", "valore_a_mente"]
    coerente: bool


def respinta(giudizio: Giudizio) -> bool:
    """Decisione effettiva: la risposta torna all'agente solo se non è coerente e viola una regola."""
    return giudizio.coerente is False and giudizio.regola != "nessuna"


def indicazione(motivo: str, regola: str) -> HumanMessage:
    """Messaggio che dice all'agente quale regola viola la risposta e perché (su una sola riga)."""
    una_riga = " ".join(motivo.split())
    return HumanMessage(
        f"{PREFISSO_INDICAZIONE} Regola violata: {regola}. La risposta precedente non va bene: {una_riga} "
        "Correggila: rispondi di nuovo all'ultima domanda dell'utente."
    )


def _testo(messaggio: BaseMessage) -> str:
    return messaggio.content if isinstance(messaggio.content, str) else str(messaggio.content)


def _e_indicazione(messaggio: BaseMessage) -> bool:
    return isinstance(messaggio, HumanMessage) and _testo(messaggio).startswith(PREFISSO_INDICAZIONE)


_DECIMALE_CON_PUNTO = re.compile(r"(?<![\d.])(\d+)\.(\d+)(?![\d.])")


def numeri_italiani(testo: str) -> str:
    """Punto decimale -> virgola nei numeri decimali; date, orari, interi e versioni (1.2.3) restano uguali."""
    return _DECIMALE_CON_PUNTO.sub(r"\1,\2", testo)


def _presenta_turno(turno: list[AnyMessage], mista: DomandaMista | None = None) -> str:
    """Il turno in testo: domanda, strumenti con risultati, indicazioni già date, risposta proposta.

    In una domanda mista il revisore vede solo le parti in ambito e l'elenco di quelle escluse:
    così non può pretendere la parte fuori ambito (specs §18.4).
    """
    domanda = next((_testo(m) for m in turno if isinstance(m, HumanMessage) and not _e_indicazione(m)), "")
    risultati = {m.tool_call_id: numeri_italiani(_testo(m)) for m in turno if isinstance(m, ToolMessage)}
    righe_strumenti = []
    for m in turno:
        if isinstance(m, AIMessage):
            for c in m.tool_calls:
                argomenti = json.dumps(c["args"], ensure_ascii=False)
                risultato = risultati.get(c["id"], "(nessun risultato)")
                righe_strumenti.append(f"- {c['name']}({argomenti}) -> {risultato}")
    indicazioni = [_testo(m) for m in turno if _e_indicazione(m)]
    risposte = [m for m in turno if isinstance(m, AIMessage)]
    proposta = pulisci_ragionamento(_testo(risposte[-1])) if risposte else ""

    if mista is None:
        righe = [f"Domanda dell'utente: {domanda}"]
    else:
        righe = [
            f"Domanda dell'utente (solo le parti in ambito): {mista.domanda_in_ambito}",
            "Parti fuori ambito già escluse (l'assistente fa bene a non rispondere, non chiederle mai): "
            + "; ".join(mista.parti_fuori_ambito),
        ]
    righe.append("Strumenti chiamati in questo turno:")
    righe += righe_strumenti or ["nessuno"]
    if indicazioni:
        righe.append("Indicazioni già date in questo turno: " + " ".join(indicazioni))
    righe.append(f"Risposta proposta: {proposta or NESSUNA_RISPOSTA}")
    return "\n".join(righe)


def messaggi_per_revisore(
    messaggi: list[AnyMessage], inizio_turno: int, ambito: str, mista: DomandaMista | None = None,
    riassunto: str = "",
) -> list[BaseMessage]:
    """Istruzioni, domande e risposte dei turni precedenti, poi il turno corrente presentato in testo."""
    contesto: list[BaseMessage] = []
    for m in messaggi[:inizio_turno]:
        if isinstance(m, HumanMessage):
            contesto.append(m)
        elif isinstance(m, AIMessage) and not m.tool_calls and m.content:
            contesto.append(m)
    return [
        SystemMessage(testo_con_riassunto(ISTRUZIONI_REVISORE.format(ambito=ambito), riassunto)),
        *contesto,
        HumanMessage(_presenta_turno(messaggi[inizio_turno:], mista)),
    ]


def rivedi(
    revisore: Runnable,
    messaggi: list[AnyMessage],
    inizio_turno: int,
    ambito: str,
    mista: DomandaMista | None = None,
    riassunto: str = "",
) -> Giudizio | None:
    """Giudica la risposta del turno; None se il revisore fallisce (la risposta passa com'è)."""
    inviati = messaggi_per_revisore(messaggi, inizio_turno, ambito, mista, riassunto)
    log.debug("messaggi inviati al revisore: %s", inviati)
    try:
        esito = revisore.invoke(inviati)
    except Exception as errore:
        log.warning("risposta non valida (%s: %s) -> fine", type(errore).__name__, errore)
        return None
    if not isinstance(esito, Giudizio):
        log.warning("risposta non valida (%r) -> fine", esito)
        return None
    return esito


def crea_revisore(config: Config) -> Runnable:
    """Crea il client verso LM Studio che restituisce un Giudizio."""
    chat = ChatOpenAI(
        base_url=config.lm_base_url,
        model=config.lm_model,
        api_key=CHIAVE_SEGNAPOSTO,
        timeout=TIMEOUT_REVISORE_SECONDI,
        max_retries=0,  # niente tentativi ripetuti: allo scadere del timeout la risposta passa com'è
        extra_body=RAGIONAMENTO_DISATTIVATO,
    )
    return chat.with_structured_output(Giudizio, method="json_schema")
