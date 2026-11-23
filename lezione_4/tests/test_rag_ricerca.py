"""Ricerca top-k con filtro per capitolo: embedder finto e Qdrant in memoria."""

from pathlib import Path

import httpx
import pytest
from finti_rag import EmbedderFinto
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse

from rag import ricerca
from rag.config import ConfigRag
from rag.errori import ErroreRag
from rag.indice import ErroreCollezioneAssente, ErroreQdrant
from rag.ingestion import esegui_ingestion
from rag.ricerca import ErroreCapitolo, EsitoRicerca, Risultato, cerca, normalizza_capitolo

ESTRATTO = Path(__file__).parent / "dati_rag" / "estratto.txt"
CONFIG = ConfigRag(
    lm_base_url="http://x/v1", embedding_model="finto", qdrant_url="http://localhost:6333",
    collezione="ricette_test", corpus=ESTRATTO, strategia="paragrafi",
    dimensione=200, overlap=50, k_max=10,
)


@pytest.fixture
def client():
    c = QdrantClient(":memory:")
    esegui_ingestion(CONFIG, EmbedderFinto(), c, attese=4)
    return c


def test_ordinati_per_score(client):
    esito = cerca("brodo con la carne", client, EmbedderFinto(), CONFIG, k=5)
    scores = [r.score for r in esito.risultati]
    assert scores == sorted(scores, reverse=True)
    assert [r.posizione for r in esito.risultati] == list(range(1, len(scores) + 1))
    assert all(isinstance(r, Risultato) for r in esito.risultati)


def test_k_predefinito(client):
    esito = cerca("brodo", client, EmbedderFinto(), CONFIG)
    assert esito.k == 5
    assert 1 <= len(esito.risultati) <= 5
    assert esito.nota is None


def test_k_oltre_il_massimo(client):
    esito = cerca("brodo", client, EmbedderFinto(), CONFIG, k=50)
    assert esito.k == 10
    assert "10" in esito.nota


def test_k_minore_di_uno(client):
    esito = cerca("brodo", client, EmbedderFinto(), CONFIG, k=0)
    assert esito.k == 1
    assert esito.nota
    assert len(esito.risultati) == 1


def test_domanda_vuota(client):
    with pytest.raises(ErroreRag):
        cerca("  ", client, EmbedderFinto(), CONFIG)


def test_filtro_capitolo(client):
    esito = cerca("brodo", client, EmbedderFinto(), CONFIG, k=10, capitolo="Minestre in brodo")
    assert esito.risultati
    assert all(r.capitolo == "Minestre in brodo" for r in esito.risultati)


def test_filtro_durante_la_ricerca(client):
    # Domanda presa dal testo di una ricetta di un altro capitolo: senza filtro vince quella.
    domanda = "mettere la carne ad acqua diaccia e far bollire la pentola adagino"
    senza = cerca(domanda, client, EmbedderFinto(), CONFIG, k=1)
    assert senza.risultati[0].capitolo == "Brodi, gelatina e sughi"
    con = cerca(domanda, client, EmbedderFinto(), CONFIG, k=1, capitolo="Minestre in brodo")
    assert len(con.risultati) == 1
    assert con.risultati[0].capitolo == "Minestre in brodo"


def test_capitolo_minuscolo(client):
    esito = cerca("brodo", client, EmbedderFinto(), CONFIG, capitolo=" minestre in brodo ")
    assert esito.capitolo == "Minestre in brodo"
    assert isinstance(esito, EsitoRicerca)


def test_capitolo_sconosciuto(client):
    with pytest.raises(ErroreCapitolo) as e:
        cerca("brodo", client, EmbedderFinto(), CONFIG, capitolo="Antipasti")
    assert "Fritti" in str(e.value) and "Uova" in str(e.value)
    with pytest.raises(ErroreCapitolo):
        normalizza_capitolo("Antipasti")


def test_collezione_assente():
    with pytest.raises(ErroreCollezioneAssente):
        cerca("brodo", QdrantClient(":memory:"), EmbedderFinto(), CONFIG)


def test_qdrant_spento_da_errore_qdrant():
    class ClientSpento:
        def collection_exists(self, nome):
            raise httpx.ConnectError("rifiutata")

    with pytest.raises(ErroreQdrant):
        cerca("brodo", ClientSpento(), EmbedderFinto(), CONFIG)


def test_deterministica(client):
    a = cerca("brodo con la carne", client, EmbedderFinto(), CONFIG, k=5)
    b = cerca("brodo con la carne", client, EmbedderFinto(), CONFIG, k=5)
    assert a.risultati == b.risultati


def test_main_stampa(capsys, monkeypatch):
    finto = EsitoRicerca(
        risultati=[Risultato(1, 0.87654, 4, "Minestra", "Minestre in brodo", 0, "testo della ricetta")],
        k=5, capitolo=None, nota="k ridotto a 10, il massimo consentito",
    )
    monkeypatch.setattr(ricerca, "carica_config_rag", lambda: CONFIG)
    monkeypatch.setattr(ricerca, "crea_client", lambda url: None)
    monkeypatch.setattr(ricerca, "cerca", lambda *a, **kw: finto)
    assert ricerca.main(["brodo", "--k", "50"]) == 0
    fuori = capsys.readouterr().out
    assert "Ricetta 4" in fuori and "Minestre in brodo" in fuori and "0.877" in fuori
    assert "k ridotto a 10" in fuori


def test_main_errore_su_stderr(capsys, monkeypatch):
    def guasta(*a, **kw):
        raise ErroreRag("guasto")

    monkeypatch.setattr(ricerca, "carica_config_rag", lambda: CONFIG)
    monkeypatch.setattr(ricerca, "crea_client", lambda url: None)
    monkeypatch.setattr(ricerca, "cerca", guasta)
    assert ricerca.main(["brodo"]) == 1
    assert "guasto" in capsys.readouterr().err


def test_main_risposta_inattesa_di_qdrant_senza_traceback(capsys, monkeypatch):
    class ClientRotto:
        def collection_exists(self, nome):
            raise UnexpectedResponse(503, "Unavailable", b"", None)

    monkeypatch.setattr(ricerca, "carica_config_rag", lambda: CONFIG)
    monkeypatch.setattr(ricerca, "crea_client", lambda url: ClientRotto())
    monkeypatch.setattr(ricerca, "EmbedderLMStudio", lambda *a, **kw: EmbedderFinto())
    assert ricerca.main(["brodo"]) == 1
    err = capsys.readouterr().err
    assert "503" in err and "QDRANT_URL" in err
    assert "Traceback" not in err
