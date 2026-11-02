"""Sessione di conversazione: cronologia in memoria, persa alla chiusura del programma."""

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from assistente.grafo import limite_raggiunto
from assistente.modello import pulisci_ragionamento

PROMPT_SISTEMA = (
    "Sei l'assistente del laboratorio. Rispondi in italiano, in modo breve e chiaro. "
    "Per conoscere la data o l'ora attuale usa sempre lo strumento get_current_time, "
    "anche se nella conversazione compare già un orario: quelli precedenti non sono più validi. "
    "Per ogni città o fuso orario richiesto chiama lo strumento con quel fuso: "
    "non calcolare l'ora partendo da un altro fuso o da un orario già citato. "
    "Riporta l'ora così come la restituisce lo strumento."
)
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
        # Solo domanda e risposta finale: le chiamate allo strumento restano nei log,
        # così un orario vecchio non rimane nel contesto del modello.
        self.cronologia += [domanda_msg, AIMessage(testo)]
        return testo
