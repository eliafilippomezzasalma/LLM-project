"""Oggetti finti per i test: nessuna chiamata a LM Studio."""

from langchain_core.messages import AIMessage

from assistente.grafo import costruisci_grafo
from assistente.revisore import Giudizio
from assistente.router import Classificazione


def chiede_ora(fuso: str, id_: str = "c1") -> AIMessage:
    """Risposta del modello che chiede lo strumento orologio."""
    return AIMessage(
        content="",
        tool_calls=[{"name": "get_current_time", "args": {"timezone": fuso}, "id": id_, "type": "tool_call"}],
    )


class ModelloFinto:
    """Restituisce le risposte preparate in ordine; finite quelle, ripete l'ultima.

    Un'eccezione nella lista viene sollevata al suo turno (errore del modello in una chiamata).
    """

    def __init__(self, risposte: list[AIMessage | Exception]):
        self.risposte = list(risposte)
        self.chiamate: list[list] = []

    def invoke(self, messaggi, config=None, **kwargs) -> AIMessage:
        self.chiamate.append(list(messaggi))
        indice = min(len(self.chiamate), len(self.risposte)) - 1
        if isinstance(self.risposte[indice], Exception):
            raise self.risposte[indice]
        # Copia senza id: il reducer add_messages assegna un id a ogni messaggio nuovo.
        return self.risposte[indice].model_copy(update={"id": None})


class ModelloCheFallisce:
    """Simula un errore di collegamento con il modello."""

    def __init__(self, errore: Exception):
        self.errore = errore

    def invoke(self, messaggi, config=None, **kwargs):
        raise self.errore


IN_AMBITO = Classificazione(
    motivo="domanda su orari", parti_fuori_ambito=[], domanda_in_ambito="Che ore sono?", categoria="conversazione"
)
FUORI = Classificazione(motivo="ricetta di cucina", parti_fuori_ambito=["ricetta"], domanda_in_ambito="", categoria="fuori_ambito")
MISTA = Classificazione(
    motivo="ora in ambito, ricetta fuori ambito",
    parti_fuori_ambito=["dammi la ricetta della pizza"],
    domanda_in_ambito="Che ore sono a Tokyo?",
    categoria="conversazione",
)


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


class RevisoreFinto(RouterFinto):
    """Stesso comportamento di RouterFinto (esiti in ordine, ripete l'ultimo, solleva le eccezioni)."""


APPROVATA = Giudizio(motivo="risponde a tutto", regola="nessuna", coerente=True)
RESPINTA = Giudizio(motivo="manca la seconda parte", regola="completezza", coerente=False)

RIFIUTO = "Non posso aiutarti."


def grafo_in_ambito(modello, registro, max_passi=3, revisore=None, max_revisioni=2):
    """Grafo con router sempre in ambito e revisore che approva (se non indicato altrimenti)."""
    return costruisci_grafo(
        modello, registro, max_passi,
        router=RouterFinto([IN_AMBITO]), ambito="ambito di prova", messaggio_rifiuto=RIFIUTO,
        revisore=revisore if revisore is not None else RevisoreFinto([APPROVATA]),
        max_revisioni=max_revisioni,
    )
