"""Leve del retrieval (specs.md §21): prefisso della domanda, riscrittura, coerenza con l'indice.

Nessun servizio acceso: embedder e riscrittore finti, client OpenAI finto, Qdrant in memoria.
"""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import openai
import pytest
from finti_rag import EmbedderFinto
from qdrant_client import QdrantClient

from rag import ricerca
from rag.config import ConfigRag
from rag.indice import ErroreIndiceDiverso
from rag.ingestion import esegui_ingestion
from rag.ricerca import EsitoRicerca, Risultato, cerca, crea_riscrittore
from rag.riscrittura import ErroreRiscrittura, RiscrittoreLMStudio, pulisci
from rag.valutazione import Domanda, tabella_markdown, valuta

ESTRATTO = Path(__file__).parent / "dati_rag" / "estratto.txt"
CONFIG = ConfigRag(
    lm_base_url="http://x/v1", embedding_model="finto", qdrant_url="http://localhost:6333",
    collezione="ricette_test", corpus=ESTRATTO, strategia="paragrafi",
    dimensione=200, overlap=50, k_max=10,
)
PREFISSI = replace(CONFIG, prefisso_documento="search_document:", prefisso_domanda="search_query:")


class RiscrittoreFinto:
    def __init__(self, risposta: str):
        self.risposta = risposta
        self.ricevute: list[str] = []

    def riscrivi(self, domanda: str) -> str:
        self.ricevute.append(domanda)
        return self.risposta


def _client(config):
    c = QdrantClient(":memory:")
    esegui_ingestion(config, EmbedderFinto(), c, attese=4)
    return c


# --- prefisso della domanda e coerenza con l'indice ---


def test_prefisso_della_domanda_arriva_all_embedder():
    client = _client(PREFISSI)
    embedder = EmbedderFinto()
    cerca("brodo", client, embedder, PREFISSI)
    assert embedder.testi == ["search_query: brodo"]


def test_senza_prefisso_la_domanda_resta_com_e():
    client = _client(CONFIG)
    embedder = EmbedderFinto()
    esito = cerca("brodo", client, embedder, CONFIG)
    assert embedder.testi == ["brodo"]
    assert esito.domanda_cercata == "brodo"


def test_ricerca_bloccata_se_la_configurazione_non_e_quella_dell_indice():
    client = _client(CONFIG)
    with pytest.raises(ErroreIndiceDiverso, match="prefisso_domanda"):
        cerca("brodo", client, EmbedderFinto(), PREFISSI)


def test_ricerca_bloccata_se_manca_il_titolo_registrato():
    con_titolo = replace(CONFIG, titolo_nel_testo=True)
    client = _client(con_titolo)
    with pytest.raises(ErroreIndiceDiverso, match="titolo_nel_testo"):
        cerca("brodo", client, EmbedderFinto(), CONFIG)
    assert cerca("brodo", client, EmbedderFinto(), con_titolo).risultati


# --- riscrittura nella ricerca ---


def test_si_cerca_domanda_piu_riscrittura():
    client = _client(PREFISSI)
    embedder = EmbedderFinto()
    finto = RiscrittoreFinto("brodo di carne")
    esito = cerca("zuppa calda", client, embedder, PREFISSI, riscrittore=finto)
    assert finto.ricevute == ["zuppa calda"]
    assert esito.domanda_cercata == "zuppa calda\nbrodo di carne"
    assert embedder.testi == ["search_query: zuppa calda\nbrodo di carne"]


def test_riscrittura_vuota_si_cerca_la_domanda():
    client = _client(CONFIG)
    esito = cerca("brodo", client, EmbedderFinto(), CONFIG, riscrittore=RiscrittoreFinto(""))
    assert esito.domanda_cercata == "brodo"


def test_crea_riscrittore_solo_se_attiva():
    assert crea_riscrittore(CONFIG) is None
    attiva = replace(CONFIG, riscrittura=True, modello_riscrittura="chat")
    r = crea_riscrittore(attiva)
    assert isinstance(r, RiscrittoreLMStudio) and r.modello == "chat"


def test_main_stampa_la_domanda_cercata(capsys, monkeypatch):
    finto = EsitoRicerca([], 5, None, None, domanda_cercata="brodo\nbrodo di carne")
    monkeypatch.setattr(ricerca, "carica_config_rag", lambda: CONFIG)
    monkeypatch.setattr(ricerca, "crea_client", lambda url: None)
    monkeypatch.setattr(ricerca, "cerca", lambda *a, **kw: finto)
    assert ricerca.main(["brodo"]) == 0
    assert "Domanda cercata: brodo" in capsys.readouterr().out


# --- RiscrittoreLMStudio con client OpenAI finto ---


class _Completions:
    def __init__(self, contenuto=None, errore=None):
        self.contenuto, self.errore, self.argomenti = contenuto, errore, None

    def create(self, **kw):
        self.argomenti = kw
        if self.errore:
            raise self.errore
        messaggio = SimpleNamespace(content=self.contenuto)
        return SimpleNamespace(choices=[SimpleNamespace(message=messaggio)])


def _riscrittore(**kw):
    completions = _Completions(**kw)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return RiscrittoreLMStudio("http://x/v1", "qwen", client=client), completions


def test_pulisci():
    assert pulisci("<think>ragiono\nancora</think>\n\n  Sapa, mosto cotto  \naltro") == "Sapa, mosto cotto"
    assert pulisci(None) == "" and pulisci("<think>x</think>") == ""


def test_riscrittore_chiede_temperatura_zero_e_niente_ragionamento():
    r, completions = _riscrittore(contenuto="Gelato di amaretti")
    assert r.riscrivi("dessert ghiacciato") == "Gelato di amaretti"
    assert completions.argomenti["temperature"] == 0
    assert completions.argomenti["model"] == "qwen"
    assert completions.argomenti["extra_body"] == {"reasoning_effort": "none"}
    assert completions.argomenti["messages"][-1] == {"role": "user", "content": "dessert ghiacciato"}


def test_riscrittore_lm_studio_spento():
    errore = openai.APIConnectionError(request=httpx.Request("POST", "http://x/v1"))
    r, _ = _riscrittore(errore=errore)
    with pytest.raises(ErroreRiscrittura, match="non raggiungibile"):
        r.riscrivi("q")


def test_riscrittore_modello_assente():
    risposta = httpx.Response(404, request=httpx.Request("POST", "http://x/v1"))
    errore = openai.NotFoundError("no", response=risposta, body=None)
    r, _ = _riscrittore(errore=errore)
    with pytest.raises(ErroreRiscrittura, match="lms load qwen"):
        r.riscrivi("q")


# --- valutazione ---


def test_valutazione_riepilogo_per_origine_e_riscritture():
    domande = [Domanda("a", (1,), "aula"), Domanda("b", (2,), "propria")]

    def cerca_fn(domanda, k):
        ris = [Risultato(1, 0.9, 1, "R1", "Cap", 0, "t")]
        return EsitoRicerca(ris, k, None, None, domanda_cercata=f"{domanda}\nriscritta {domanda}")

    t = tabella_markdown(valuta(domande, cerca_fn, 5), 5)
    assert "Domande «aula»: 1 su 1" in t and "Domande «propria»: 0 su 1" in t
    assert "- a → riscritta a" in t
