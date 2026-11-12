"""Oggetti finti per i test: nessuna chiamata a LM Studio."""

from langchain_core.messages import AIMessage

from assistente.grafo import costruisci_grafo
from assistente.router import Classificazione


def chiede_ora(fuso: str, id_: str = "c1") -> AIMessage:
    """Risposta del modello che chiede lo strumento orologio."""
    return AIMessage(
        content="",
        tool_calls=[{"name": "get_current_time", "args": {"timezone": fuso}, "id": id_, "type": "tool_call"}],
    )


class ModelloFinto:
    """Restituisce le risposte preparate in ordine; finite quelle, ripete l'ultima."""

    def __init__(self, risposte: list[AIMessage]):
        self.risposte = list(risposte)
        self.chiamate: list[list] = []

    def invoke(self, messaggi, config=None, **kwargs) -> AIMessage:
        self.chiamate.append(list(messaggi))
        indice = min(len(self.chiamate), len(self.risposte)) - 1
        # Copia senza id: il reducer add_messages assegna un id a ogni messaggio nuovo.
        return self.risposte[indice].model_copy(update={"id": None})


class ModelloCheFallisce:
    """Simula un errore di collegamento con il modello."""

    def __init__(self, errore: Exception):
        self.errore = errore

    def invoke(self, messaggi, config=None, **kwargs):
        raise self.errore


IN_AMBITO = Classificazione(categoria="conversazione", motivo="domanda su orari")
FUORI = Classificazione(categoria="fuori_ambito", motivo="ricetta di cucina")


class RouterFinto:
    """Restituisce gli esiti preparati in ordine (ripete l'ultimo); le eccezioni vengono sollevate."""

    def __init__(self, esiti: list):
        self.esiti = list(esiti)
        self.chiamate: list[list] = []

    def invoke(self, messaggi, config=None, **kwargs):
        self.chiamate.append(list(messaggi))
        esito = self.esiti[min(len(self.chiamate), len(self.esiti)) - 1]
        if isinstance(esito, Exception):
            raise esito
        return esito


RIFIUTO = "Non posso aiutarti."


def grafo_in_ambito(modello, registro, max_passi=3):
    """Grafo con router che classifica sempre in ambito: per i test che non riguardano il router."""
    return costruisci_grafo(
        modello, registro, max_passi,
        router=RouterFinto([IN_AMBITO]), ambito="ambito di prova", messaggio_rifiuto=RIFIUTO,
    )
