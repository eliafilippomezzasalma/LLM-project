"""Ingestion in Qdrant: embedder finto e Qdrant in memoria, nessun servizio acceso."""

import httpx
import pytest
from finti_rag import EmbedderFinto
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from rag import indice, ingestion
from rag.config import ConfigRag
from rag.corpus import ErroreCorpus
from rag.embedding import ErroreEmbedding
from rag.indice import ErroreCollezioneAssente, ErroreIndiceDiverso, ErroreModelloDiverso, ErroreQdrant
from dataclasses import replace

from rag.chunking import Chunk, contenuto_da_incorporare
from rag.ingestion import esegui_ingestion

from pathlib import Path

ESTRATTO = Path(__file__).parent / "dati_rag" / "estratto.txt"
NOME = "ricette_test"


def config(dimensione=200, overlap=50, corpus=ESTRATTO):
    return ConfigRag(
        lm_base_url="http://x/v1", embedding_model="finto", qdrant_url="http://localhost:6333",
        collezione=NOME, corpus=corpus, strategia="paragrafi",
        dimensione=dimensione, overlap=overlap, k_max=10,
    )


@pytest.fixture
def client():
    return QdrantClient(":memory:")


def tutti_i_punti(client):
    punti, _ = client.scroll(NOME, limit=10_000, with_payload=True, with_vectors=False)
    return punti


def test_punti_uguali_ai_chunk(client):
    esito = esegui_ingestion(config(), EmbedderFinto(), client, attese=4)
    assert esito.ricette == 4
    assert esito.chunk > 4
    assert esito.punti_prima == 0
    assert esito.punti_dopo == esito.chunk == indice.conta_punti(client, NOME)
    assert esito.caratteri_min <= esito.caratteri_medi <= esito.caratteri_max


def test_payload_completo(client):
    esegui_ingestion(config(), EmbedderFinto(), client, attese=4)
    punti = tutti_i_punti(client)
    chiavi = {"ricetta", "titolo", "capitolo", "posizione", "testo", "fonte", "documento_id", "contiene_dosi"}
    for p in punti:
        assert set(p.payload) == chiavi
        assert p.payload["fonte"] == "Pellegrino Artusi, La scienza in cucina e l'arte di mangiar bene"
        assert p.payload["documento_id"] == f"ricetta-{p.payload['ricetta']:03d}"
        assert p.payload["testo"]


def test_due_ingestion_stesso_numero_di_punti(client):
    prima = esegui_ingestion(config(), EmbedderFinto(), client, attese=4)
    seconda = esegui_ingestion(config(), EmbedderFinto(), client, attese=4)
    assert seconda.punti_dopo == prima.punti_dopo
    assert seconda.punti_prima == seconda.punti_dopo
    assert seconda.rimossi == 0


def test_punti_obsoleti_rimossi(client):
    esegui_ingestion(config(dimensione=200), EmbedderFinto(), client, attese=4)
    seconda = esegui_ingestion(config(dimensione=2000), EmbedderFinto(), client, attese=4)
    assert seconda.punti_dopo == seconda.chunk
    assert seconda.rimossi > 0


def test_modello_registrato(client):
    esegui_ingestion(config(), EmbedderFinto(dimensione=64), client, attese=4)
    metadati = client.get_collection(NOME).config.metadata
    assert metadati == {
        "modello_embedding": "finto", "dimensione": 64,
        "prefisso_documento": "", "prefisso_domanda": "", "titolo_nel_testo": False,
        "ingestion_incompleta": False,
    }


@pytest.mark.parametrize("altro", [EmbedderFinto(modello="altro"), EmbedderFinto(dimensione=32)])
def test_cambio_modello_bloccato(client, altro):
    esegui_ingestion(config(), EmbedderFinto(), client, attese=4)
    prima = indice.conta_punti(client, NOME)
    with pytest.raises(ErroreModelloDiverso) as e:
        esegui_ingestion(config(), altro, client, attese=4)
    assert "finto" in str(e.value)
    assert altro.modello in str(e.value)
    assert indice.conta_punti(client, NOME) == prima


def test_verifica_modello_collezione_assente(client):
    with pytest.raises(ErroreCollezioneAssente, match="python -m rag.ingestion"):
        indice.verifica_modello(client, NOME, "finto", 64)


class Spia:
    """Inoltra tutto al client vero e registra gli indici richiesti."""

    def __init__(self, vero):
        self._vero = vero
        self.indici = []

    def create_payload_index(self, collection_name, field_name, field_schema=None, **kw):
        self.indici.append((field_name, field_schema))
        return self._vero.create_payload_index(collection_name, field_name, field_schema, **kw)

    def __getattr__(self, nome):
        return getattr(self._vero, nome)


def test_indici_payload(client):
    spia = Spia(client)
    esegui_ingestion(config(), EmbedderFinto(), spia, attese=4)
    # In memoria Qdrant non riporta gli indici in payload_schema: si verifica la chiamata.
    assert {nome: str(tipo.value if hasattr(tipo, "value") else tipo) for nome, tipo in spia.indici} == {
        "capitolo": "keyword",
        "ricetta": "integer",
        "contiene_dosi": "bool",
    }


def test_corpus_incompleto_nessuna_scrittura(client):
    embedder = EmbedderFinto()
    with pytest.raises(ErroreCorpus):
        esegui_ingestion(config(), embedder, client, attese=790)
    assert not client.collection_exists(NOME)
    assert embedder.chiamate == 0


def test_main_errore_senza_traceback(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("LM_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "finto")
    monkeypatch.setenv("RAG_CORPUS", str(tmp_path / "non_esiste.txt"))
    assert ingestion.main([]) == 1
    err = capsys.readouterr().err
    assert "non_esiste.txt" in err
    assert "Traceback" not in err


class ClientIrraggiungibile:
    def __getattr__(self, nome):
        def chiama(*a, **k):
            raise ResponseHandlingException(httpx.ConnectError("connessione rifiutata"))

        return chiama


def test_qdrant_irraggiungibile():
    with pytest.raises(ErroreQdrant) as e:
        esegui_ingestion(config(), EmbedderFinto(), ClientIrraggiungibile(), attese=4)
    assert "Qdrant non raggiungibile su http://localhost:6333" in str(e.value)
    assert "docker compose up -d qdrant" in str(e.value)
    assert "QDRANT_URL" in str(e.value)


def test_crea_client_non_si_connette():
    assert isinstance(indice.crea_client("http://localhost:1"), QdrantClient)


def test_risposta_inattesa_di_qdrant_da_errore_qdrant():
    class ClientRotto:
        def __getattr__(self, nome):
            def chiama(*a, **k):
                raise UnexpectedResponse(404, "Not Found", b"", None)

            return chiama

    with pytest.raises(ErroreQdrant) as e:
        esegui_ingestion(config(), EmbedderFinto(), ClientRotto(), attese=4)
    assert "404" in str(e.value)
    assert "QDRANT_URL" in str(e.value)


def test_vettori_meno_dei_testi(client):
    class EmbedderCorto(EmbedderFinto):
        def incorpora(self, testi):
            return super().incorpora(testi)[:-1] if len(testi) > 1 else super().incorpora(testi)

    with pytest.raises(ErroreEmbedding) as e:
        esegui_ingestion(config(), EmbedderCorto(), client, attese=4)
    assert "vettori per" in str(e.value)


# §21: testo indicizzato e impostazioni registrate


def test_contenuto_da_incorporare():
    c = Chunk(ricetta=1, titolo="Brodo", capitolo="Brodi", posizione=0, testo="Acqua e carne.")
    assert contenuto_da_incorporare(c) == "Acqua e carne."
    assert contenuto_da_incorporare(c, prefisso="search_document:") == "search_document: Acqua e carne."
    assert contenuto_da_incorporare(c, True, "p:") == "p: Brodo — Brodi\n\nAcqua e carne."


def test_titolo_e_prefisso_nel_vettore_non_nel_payload(client):
    embedder = EmbedderFinto()
    cfg = replace(config(), titolo_nel_testo=True, prefisso_documento="search_document:")
    esegui_ingestion(cfg, embedder, client, attese=4)
    assert all(t.startswith("search_document: ") and " — " in t for t in embedder.testi)
    for p in tutti_i_punti(client):
        assert not p.payload["testo"].startswith(("search_document:", f"{p.payload['titolo']} — "))
    meta = client.get_collection(NOME).config.metadata
    assert meta["titolo_nel_testo"] is True and meta["prefisso_documento"] == "search_document:"


def test_modifica_b_ricalcolo_nella_stessa_collezione(client):
    """§22.3: con il titolo attivato l'ingestion ricalcola i vettori senza ricreare la collezione."""
    esegui_ingestion(config(), EmbedderFinto(), client, attese=4)
    prima = {p.id: p.vector for p in client.scroll(NOME, limit=100, with_vectors=True)[0]}
    embedder = EmbedderFinto()
    esito = esegui_ingestion(replace(config(), titolo_nel_testo=True), embedder, client, attese=4)
    dopo = {p.id: p.vector for p in client.scroll(NOME, limit=100, with_vectors=True)[0]}
    assert esito.punti_prima == esito.punti_dopo == len(prima) and esito.rimossi == 0
    assert set(dopo) == set(prima)
    assert all(dopo[i] != prima[i] for i in prima)  # tutti i vettori ricalcolati
    assert all(" — " in t for t in embedder.testi)  # testo passato all'embedder con il titolo
    meta = client.get_collection(NOME).config.metadata
    assert meta["titolo_nel_testo"] is True and meta["ingestion_incompleta"] is False
    with pytest.raises(ErroreIndiceDiverso, match="titolo_nel_testo"):  # la ricerca vecchia è bloccata
        indice.verifica_modello(client, NOME, "finto", 64, indice.impostazioni_indice(config()))


def test_ingestion_interrotta_blocca_la_ricerca(client):
    esegui_ingestion(config(), EmbedderFinto(), client, attese=4)

    class Rotto(EmbedderFinto):
        def incorpora(self, testi):
            if self.chiamate >= 1:
                raise ErroreEmbedding("LM Studio caduto")
            return super().incorpora(testi)

    with pytest.raises(ErroreEmbedding):
        esegui_ingestion(replace(config(), titolo_nel_testo=True), Rotto(), client, attese=4)
    with pytest.raises(indice.ErroreIngestionIncompleta, match="non è terminata"):
        indice.verifica_modello(client, NOME, "finto", 64, indice.impostazioni_indice(config()))
    esegui_ingestion(config(), EmbedderFinto(), client, attese=4)  # rieseguita: torna utilizzabile
    indice.verifica_modello(client, NOME, "finto", 64, indice.impostazioni_indice(config()))


def test_contiene_dosi_nel_payload(client):
    esegui_ingestion(config(), EmbedderFinto(), client, attese=4)
    valori = {p.payload["contiene_dosi"] for p in tutti_i_punti(client)}
    assert valori == {True, False}  # nell'estratto ci sono chunk con e senza elenco di dosi


def test_collezione_senza_impostazioni_vale_come_paragrafo_20(client):
    client.create_collection(
        NOME, vectors_config=indice.models.VectorParams(size=64, distance=indice.models.Distance.COSINE),
        metadata={"modello_embedding": "finto", "dimensione": 64},
    )
    indice.verifica_modello(client, NOME, "finto", 64, indice.impostazioni_indice(config()))
    with pytest.raises(ErroreIndiceDiverso):
        indice.verifica_modello(
            client, NOME, "finto", 64, indice.impostazioni_indice(replace(config(), prefisso_domanda="q:"))
        )
