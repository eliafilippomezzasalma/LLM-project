"""Riassunto della cronologia: un modello sostituisce i turni vecchi con un testo breve."""

import json
import logging
from math import ceil

from langchain_core.messages import AIMessage, AnyMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from assistente.config import Config
from assistente.modello import CHIAVE_SEGNAPOSTO, RAGIONAMENTO_DISATTIVATO, pulisci_ragionamento

log = logging.getLogger("riassunto")

TIMEOUT_RIASSUNTO_SECONDI = 60
PREFISSO_RIASSUNTO = (
    "Riassunto della conversazione precedente (i messaggi più vecchi sono stati tolti dalla cronologia e "
    "sostituiti da questo riassunto: consideralo parte della conversazione. Usalo per il nome dell'utente, "
    "le sue preferenze e le richieste precedenti, anche quando un seguito breve come «e in metri?» si "
    "riferisce a una richiesta che compare solo qui):"
)

ISTRUZIONI_RIASSUNTO = """Sei il componente di memoria di un assistente. Ricevi il riassunto precedente della conversazione e i messaggi più vecchi, che stanno per essere tolti dalla cronologia.
Scrivi un unico riassunto aggiornato: sostituisce quello precedente e ne conserva le informazioni ancora utili.

Regole:
- Scrivi in italiano, in terza persona, al massimo 100 parole.
- Inizia sempre il riassunto con una frase sul nome e sulle preferenze dell'utente, per esempio «L'utente si chiama Elia e preferisce le distanze in miglia.», anche se vengono dal riassunto precedente. Se non li conosci, omettila.
- Conserva il nome e gli altri dati personali dell'utente.
- Conserva le preferenze dell'utente, per esempio le unità di misura.
- Per ogni domanda scrivi solo che cosa ha chiesto l'utente, con i dati della domanda, MAI la risposta: scrivi «ha chiesto l'ora a Londra», non «a Londra sono le 9:00»; scrivi «ha chiesto quanti giorni mancano a Pasqua», non «mancano 120 giorni».
- Usa solo i numeri scritti dall'utente: nessun numero preso dalle risposte dell'assistente o dai risultati degli strumenti, nemmeno approssimato (niente orari, conversioni, risultati di calcoli, date calcolate, conteggi di giorni). Le risposte verranno ricalcolate con gli strumenti se servono.
- Dal riassunto precedente conserva ogni domanda con i suoi dati (per esempio «ha chiesto di convertire 5 miglia in km»), senza accorparle in frasi generiche.
- Annota come rifiutate le richieste fuori ambito, senza spiegare l'ambito.
- Scrivi solo il riassunto, senza titoli né commenti."""


def conversazione(messaggi: list[AnyMessage]) -> list[AnyMessage]:
    """I messaggi senza i SystemMessage."""
    return [m for m in messaggi if not isinstance(m, SystemMessage)]


def _caratteri(messaggio: AnyMessage) -> int:
    """Caratteri del testo del messaggio più quelli degli argomenti delle sue chiamate a strumenti."""
    totale = len(str(messaggio.content))
    for chiamata in getattr(messaggio, "tool_calls", None) or []:
        totale += len(json.dumps(chiamata["args"], ensure_ascii=False))
    return totale


def stima_token(messaggi: list[AnyMessage]) -> int:
    """Stima grossolana: un token ogni 4 caratteri, senza i messaggi di sistema."""
    return ceil(sum(_caratteri(m) for m in conversazione(messaggi)) / 4)


def misura(messaggi: list[AnyMessage], tipo: str) -> int:
    """Dimensione della conversazione (senza SystemMessage) in messaggi o in token stimati."""
    if tipo == "token":
        return stima_token(messaggi)
    return len(conversazione(messaggi))


def punto_di_taglio(conversazione: list[AnyMessage], turni_da_tenere: int) -> int:
    """Indice del primo messaggio da conservare; 0 se non c'è niente da togliere.

    Si taglia sempre all'inizio di un turno (un HumanMessage): l'ultimo è la domanda nuova e
    si tengono gli ultimi turni_da_tenere turni precedenti. Così una chiamata a uno strumento
    non resta mai separata dal suo risultato.
    """
    inizi = [i for i, m in enumerate(conversazione) if isinstance(m, HumanMessage)]
    if len(inizi) > turni_da_tenere + 1:
        return inizi[-(turni_da_tenere + 1)]
    return 0


def coppie_complete(messaggi: list[AnyMessage]) -> bool:
    """Vero se ogni chiamata a uno strumento ha il suo risultato e ogni risultato la sua chiamata."""
    chiamate = {c["id"] for m in messaggi if isinstance(m, AIMessage) for c in m.tool_calls}
    risultati = {m.tool_call_id for m in messaggi if isinstance(m, ToolMessage)}
    return chiamate == risultati


def testo_con_riassunto(testo_sistema: str, riassunto: str) -> str:
    """Il prompt di sistema con il riassunto in coda; invariato se il riassunto è vuoto."""
    if not riassunto.strip():
        return testo_sistema
    return f"{testo_sistema}\n\n{PREFISSO_RIASSUNTO} {riassunto}"


def messaggi_con_riassunto(messaggi: list[AnyMessage], riassunto: str) -> list[AnyMessage]:
    """Copia dei messaggi con il riassunto aggiunto al primo SystemMessage; la stessa lista se è vuoto."""
    if not riassunto.strip():
        return messaggi
    risultato = list(messaggi)
    for i, m in enumerate(risultato):
        if isinstance(m, SystemMessage):
            risultato[i] = SystemMessage(testo_con_riassunto(str(m.content), riassunto))
            break
    return risultato


def _righe(messaggio: AnyMessage) -> list[str]:
    """Le righe con cui un messaggio vecchio viene mostrato al modello (nessun ToolMessage)."""
    if isinstance(messaggio, HumanMessage):
        return [f"Utente: {messaggio.content}"]
    if not isinstance(messaggio, AIMessage):
        return []
    righe = []
    testo = pulisci_ragionamento(str(messaggio.content))
    if testo:
        righe.append(f"Assistente: {testo}")
    for c in messaggio.tool_calls:
        argomenti = json.dumps(c["args"], ensure_ascii=False)
        righe.append(f"Assistente (chiamata a strumento): {c['name']}({argomenti})")
    return righe


def messaggi_per_riassunto(precedente: str, tolti: list[AnyMessage]) -> list[BaseMessage]:
    """Istruzioni più un solo messaggio con il riassunto precedente e i messaggi da riassumere."""
    righe = [f"Riassunto precedente: {precedente.strip() or '(nessuno)'}", "", "Messaggi da riassumere:"]
    for m in tolti:
        righe.extend(_righe(m))
    return [SystemMessage(ISTRUZIONI_RIASSUNTO), HumanMessage("\n".join(righe))]


def riassumi(modello: Runnable, precedente: str, tolti: list[AnyMessage]) -> str | None:
    """Il nuovo riassunto ripulito; None se il modello fallisce o risponde a vuoto (cronologia invariata)."""
    inviati = messaggi_per_riassunto(precedente, tolti)
    log.debug("messaggi inviati al riassuntore: %s", inviati)
    try:
        risposta = modello.invoke(inviati)
        testo = pulisci_ragionamento(str(risposta.content))
    except Exception as errore:
        log.warning("risposta non valida (%s: %s), cronologia invariata", type(errore).__name__, errore)
        return None
    if not testo:
        log.warning("risposta non valida (testo vuoto), cronologia invariata")
        return None
    log.debug("nuovo riassunto: %s", testo)
    return testo


def crea_riassuntore(config: Config) -> Runnable:
    """Crea il client verso LM Studio che restituisce testo libero (senza strumenti)."""
    return ChatOpenAI(
        base_url=config.lm_base_url,
        model=config.lm_model,
        api_key=CHIAVE_SEGNAPOSTO,
        timeout=TIMEOUT_RIASSUNTO_SECONDI,
        max_retries=0,  # allo scadere del timeout la cronologia resta com'è
        extra_body=RAGIONAMENTO_DISATTIVATO,
    )
