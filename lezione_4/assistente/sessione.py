"""Sessione di conversazione: cronologia in memoria, persa alla chiusura del programma."""

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from assistente.grafo import limite_raggiunto
from assistente.modello import pulisci_ragionamento

PROMPT_SISTEMA = (
    "Sei l'assistente del laboratorio. Rispondi in italiano, in modo breve e chiaro. "
    "Per conoscere la data o l'ora attuale usa sempre lo strumento get_current_time, "
    "anche se nella conversazione compare già un orario: quelli precedenti non sono più validi. "
    "Per ogni città o fuso orario richiesto chiama lo strumento con quel fuso: "
    "non calcolare l'ora partendo da un altro fuso o da un orario già citato. "
    "Riporta l'ora così come la restituisce lo strumento. "
    "Per convertire unità di misura usa sempre lo strumento convert_units e non fare i calcoli a mente. "
    "Chiamalo prima di rispondere a ogni richiesta di conversione, anche quando pensi che la "
    "conversione non sia possibile (per esempio da kg a metri): è lo strumento a verificarlo. "
    "Esempi: per «converti 2 anni luce in km» chiama convert_units con from_unit 'anni luce'; "
    "per «converti -300 °C in kelvin» chiama convert_units con value -300. "
    "Non descrivere da solo i limiti dello strumento: riporta il suo messaggio. "
    "Se lo strumento restituisce un errore, spiegalo all'utente senza inventare un risultato. "
    "Per ogni calcolo aritmetico, anche semplice, usa sempre lo strumento calculate e non fare i conti a mente. "
    "Chiamalo anche quando pensi che il calcolo sia impossibile (per esempio una divisione per zero): "
    "è lo strumento a verificarlo. "
    "Esempio: per «quanto fa 10 / 0?» chiama calculate con expression '10 / 0'. "
    "Per le conversioni di unità usa sempre convert_units, non calculate, anche quando l'unità "
    "non è tra quelle ammesse (per esempio parsec): riporta il suo errore e non calcolare "
    "la conversione da solo con calculate. "
    "Se calculate restituisce un errore, spiega all'utente il motivo e fermati: non dare il risultato, "
    "nemmeno calcolato a mente o riscrivendo l'operazione in un altro modo, e non fare altre chiamate "
    "per aggirare l'errore. Dopo un errore la risposta non contiene il valore richiesto, "
    "anche se lo conosci. "
    "Anche per radici, seni, logaritmi o altre funzioni chiama comunque calculate con l'espressione "
    "richiesta: è lo strumento a dire che cosa è ammesso. Esempio: per «calcola la radice di 16» chiama "
    "calculate con expression 'sqrt(16)' e, se risponde con un errore, spiegalo senza dire quanto vale."
)
# Strumenti le cui chiamate restano nella cronologia: sono esempi utili al modello per
# continuare a usarli. Le chiamate all'orologio no: un orario vecchio non deve restare.
STRUMENTI_IN_CRONOLOGIA = frozenset({"convert_units", "calculate"})
RISPOSTA_VUOTA = "(nessuna risposta dal modello)"


class LimitePassaggiRaggiunto(Exception):
    """Il modello ha chiesto strumenti oltre il numero massimo di passaggi."""


class Sessione:
    def __init__(self, grafo):
        self.grafo = grafo
        self.cronologia: list[BaseMessage] = [SystemMessage(PROMPT_SISTEMA)]

    def chiedi(self, domanda: str) -> str:
        """Esegue un turno; la cronologia cambia solo se il turno riesce."""
        domanda_msg = HumanMessage(domanda)
        stato = self.grafo.invoke({"messages": [*self.cronologia, domanda_msg], "passi_strumento": 0})
        if limite_raggiunto(stato):
            raise LimitePassaggiRaggiunto()
        testo = pulisci_ragionamento(stato["messages"][-1].text) or RISPOSTA_VUOTA
        passaggi = stato["messages"][len(self.cronologia) + 1 : -1]
        self.cronologia += [domanda_msg, *_chiamate_da_conservare(passaggi), AIMessage(testo)]
        return testo


def _chiamate_da_conservare(passaggi: list[BaseMessage]) -> list[BaseMessage]:
    """Dei passaggi intermedi tiene solo le chiamate (e le risposte) di STRUMENTI_IN_CRONOLOGIA.

    Le altre restano solo nei log. Ogni chiamata conservata ha la sua risposta, come
    richiede l'API: le chiamate miste vengono ridotte a quelle conservate.
    """
    conservati: list[BaseMessage] = []
    id_conservati: set[str] = set()
    for messaggio in passaggi:
        if isinstance(messaggio, AIMessage):
            chiamate = [c for c in messaggio.tool_calls if c["name"] in STRUMENTI_IN_CRONOLOGIA]
            if chiamate:
                conservati.append(AIMessage(content="", tool_calls=chiamate))
                id_conservati.update(c["id"] for c in chiamate if c["id"])
        elif isinstance(messaggio, ToolMessage) and messaggio.tool_call_id in id_conservati:
            conservati.append(messaggio)
    return conservati
