"""Sessione di conversazione: cronologia in memoria, persa alla chiusura del programma."""

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from assistente.grafo import limite_raggiunto
from assistente.modello import pulisci_ragionamento
from assistente.nota import STRUMENTO_CON_NOTA, NotaNonNormativa

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
    "calculate con expression 'sqrt(16)' e, se risponde con un errore, spiegalo senza dire quanto vale. "
    "Per ogni domanda su date, scadenze, giorni lavorativi, festività o giorni della settimana usa sempre "
    "gli strumenti delle scadenze e non fare i conti a mente, anche quando la risposta sembra ovvia. "
    "Questi strumenti accettano solo date nel formato AAAA-MM-GG: converti tu le date dell'utente "
    "(per esempio «15/03/2024» o «15 marzo 2024» diventano '2024-03-15'). "
    "Quando la domanda parte da oggi («mancano», «sono passati», «fra N giorni», «da oggi»), a ogni "
    "domanda di questo tipo chiama prima get_current_time con il fuso 'Europe/Rome' e poi passa allo "
    "strumento la data che restituisce. Le date citate nelle domande precedenti (per esempio la firma "
    "di un affitto) non sono la data di oggi, e nemmeno quelle nei risultati precedenti: anche se la "
    "data di oggi compare già nella conversazione, chiedila di nuovo a get_current_time. "
    "Esempi: per «quanti giorni mancano al 25/12/2026?» chiama prima get_current_time con timezone "
    "'Europe/Rome' e poi days_between con from_date uguale alla data restituita e to_date '2026-12-25'; "
    "per «che giorno sarà fra 10 giorni lavorativi?» chiama prima get_current_time e poi add_business_days "
    "con start_date uguale alla data restituita; per «quanti giorni sono passati dal 15/03/2024?» chiama "
    "prima get_current_time e poi days_between con from_date '2024-03-15'. "
    "Per scadenze e termini (affitti, fatture, preavvisi, anche in giorni lavorativi) usa compute_deadline; "
    "per un preavviso usa direction 'backward'. "
    "Usa add_business_days solo per sapere che giorno sarà fra N giorni lavorativi quando non si parla "
    "di una scadenza. "
    "days_between dice se una data viene prima o dopo l'altra: se una delle due è oggi, rispondi con "
    "«mancano» o «sono passati». "
    "Anche quando pensi che una data non esista o sia troppo lontana chiama comunque lo strumento, "
    "per esempio per «il 30/02/2026 è festivo?» chiama date_info con date '2026-02-30': è lo strumento "
    "a verificarlo. "
    "Nelle risposte che usano questi strumenti scrivi ogni data solo nel formato AAAA-MM-GG, come nel "
    "risultato dello strumento, anche quando ripeti le date della domanda: mai «30/06/2026», «30-06-2026», "
    "«30.06.2026» o «30 giugno 2026». Esempio: per «il 2 giugno 2027 è festivo?» chiama date_info con "
    "date '2027-06-02' e, dopo il risultato, nella risposta scrivi 2027-06-02, non «2 giugno 2027». "
    "Questa regola non vale per le risposte che usano solo get_current_time. "
    "Se la scadenza è stata spostata, riporta la data calcolata, il motivo e la data finale. "
    "Se il risultato contiene una riga «Nota:», riportala così com'è nella risposta. "
    "Se uno di questi strumenti restituisce un errore, spiega il motivo e fermati, senza calcolare "
    "la data da solo. "
    "Anche quando la domanda contiene più richieste (per esempio «quanto fa 17*23 e quanti giorni "
    "mancano a Natale?»), dopo aver ricevuto la data da get_current_time chiama days_between con quella "
    "data: non contare mai i giorni da solo, nemmeno quando conosci già la data di oggi."
)
# Strumenti le cui chiamate restano nella cronologia: sono esempi utili al modello per
# continuare a usarli. Anche l'orologio: senza le sue chiamate il modello vedeva solo orari
# nelle risposte e ai seguiti («e a Roma?») li copiava spostando il fuso a mente (2026-11-13).
STRUMENTI_IN_CRONOLOGIA = frozenset({
    "get_current_time",
    "convert_units",
    "calculate",
    "compute_deadline",
    "add_business_days",
    "count_business_days",
    "days_between",
    "date_info",
    "list_holidays",
})
RISPOSTA_VUOTA = "(nessuna risposta dal modello)"


class LimitePassaggiRaggiunto(Exception):
    """Il modello ha chiesto strumenti oltre il numero massimo di passaggi."""


class Sessione:
    def __init__(self, grafo, nota: NotaNonNormativa | None = None):
        self.grafo = grafo
        self.nota = nota
        self.cronologia: list[BaseMessage] = [SystemMessage(PROMPT_SISTEMA)]

    def chiedi(self, domanda: str) -> str:
        """Esegue un turno; la cronologia cambia solo se il turno riesce."""
        domanda_msg = HumanMessage(domanda)
        stato = self.grafo.invoke({"messages": [*self.cronologia, domanda_msg], "passi_strumento": 0})
        if limite_raggiunto(stato):
            raise LimitePassaggiRaggiunto()
        testo = pulisci_ragionamento(stato["messages"][-1].text) or RISPOSTA_VUOTA
        if self.nota is not None:
            risultati = [
                str(m.content)
                for m in stato["messages"][len(self.cronologia) + 1 :]
                if isinstance(m, ToolMessage) and m.name == STRUMENTO_CON_NOTA
            ]
            testo = self.nota.completa(testo, risultati)
            self.nota.registra_risposta(testo)
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
