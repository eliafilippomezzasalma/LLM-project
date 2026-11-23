"""Modifica A (specs.md §22.2): campo contiene_dosi, aggiornamento dei punti e filtro.

Nessun servizio acceso: embedder finto e Qdrant in memoria.
"""

from pathlib import Path

import pytest
from finti_rag import EmbedderFinto
from qdrant_client import QdrantClient, models

from rag import metadati, ricerca, valutazione
from rag.config import ConfigRag
from rag.errori import ErroreRag
from rag.indice import ErroreCollezioneAssente, conta_punti
from rag.ingestion import esegui_ingestion
from rag.metadati import aggiorna_metadati, contiene_dosi
from rag.ricerca import EsitoRicerca, cerca

ESTRATTO = Path(__file__).parent / "dati_rag" / "estratto.txt"
CONFIG = ConfigRag(
    lm_base_url="http://x/v1", embedding_model="finto", qdrant_url="http://localhost:6333",
    collezione="ricette_test", corpus=ESTRATTO, strategia="paragrafi",
    dimensione=200, overlap=50, k_max=10,
)
NOME = CONFIG.collezione


# --- riconoscimento ---


def test_elenco_di_ingredienti():
    testo = "Patate grosse e gialle, grammi 400.\nFarina di grano, grammi 150.\n\nLessate le patate."
    assert contiene_dosi(testo)


def test_elenco_con_quantita_in_lettere_e_virgole_nel_nome():
    testo = "Latte, mezzo litro.\nMagro di manzo nella coscia, senz'osso, grammi 500\nSale, quanto basta."
    assert contiene_dosi(testo)


def test_dosi_solo_nel_discorso():
    testo = (
        "Fate una balsamella con grammi 60 di burro, due cucchiaiate di farina e 4 decilitri di "
        "latte, poi versatela sulla carne e lasciatela cuocere adagio per una mezz'ora abbondante.\n"
        "Fate un battuto con due spicchi d'aglio, un pizzico di prezzemolo e qualche foglia di basilico."
    )
    assert not contiene_dosi(testo)


def test_una_sola_riga_non_basta():
    assert not contiene_dosi("Riso, grammi 300.\n\nCuocetelo nel brodo.")


def test_senza_dosi():
    assert not contiene_dosi("Il minestrone mi richiama alla memoria un anno di pubbliche angoscie.")


# --- rag.metadati: punti esistenti senza nuovi embedding ---


@pytest.fixture
def client_senza_campo():
    """Collezione indicizzata e poi privata del campo, come una collezione della §20/§21."""
    c = QdrantClient(":memory:")
    esegui_ingestion(CONFIG, EmbedderFinto(), c, attese=4)
    ids = [p.id for p in c.scroll(NOME, limit=1000)[0]]
    c.delete_payload(NOME, keys=["contiene_dosi"], points=ids)
    return c


def _vettori(client):
    return {p.id: p.vector for p in client.scroll(NOME, limit=1000, with_vectors=True)[0]}


def test_aggiorna_metadati_senza_ricalcolare_gli_embedding(client_senza_campo, monkeypatch):
    c = client_senza_campo
    prima = _vettori(c)
    punti_prima = conta_punti(c, NOME)
    # Nessun embedder: se aggiorna_metadati provasse a crearne uno, il test fallirebbe.
    monkeypatch.setattr("rag.embedding.EmbedderLMStudio", None)
    esito = aggiorna_metadati(c, NOME)
    assert _vettori(c) == prima
    assert esito.punti == punti_prima == conta_punti(c, NOME)
    assert esito.vero + esito.falso == punti_prima and esito.vero > 0 and esito.falso > 0
    for p in c.scroll(NOME, limit=1000, with_payload=True)[0]:
        assert p.payload["contiene_dosi"] == contiene_dosi(p.payload["testo"])


def test_aggiorna_metadati_rieseguibile(client_senza_campo):
    primo = aggiorna_metadati(client_senza_campo, NOME)
    assert aggiorna_metadati(client_senza_campo, NOME) == primo


def test_aggiorna_metadati_collezione_assente():
    with pytest.raises(ErroreCollezioneAssente):
        aggiorna_metadati(QdrantClient(":memory:"), "manca")


def test_main_metadati(capsys, monkeypatch, client_senza_campo):
    monkeypatch.setattr(metadati, "carica_config_rag", lambda: CONFIG)
    monkeypatch.setattr(metadati, "crea_client", lambda url: client_senza_campo)
    assert metadati.main([]) == 0
    assert "contiene_dosi vero:" in capsys.readouterr().out


# --- filtro nella ricerca ---


@pytest.fixture
def client():
    c = QdrantClient(":memory:")
    esegui_ingestion(CONFIG, EmbedderFinto(), c, attese=4)
    return c


def test_solo_dosi_tutti_i_risultati_hanno_il_campo(client):
    esito = cerca("patate farina brodo", client, EmbedderFinto(), CONFIG, k=10, solo_dosi=True)
    assert 0 < len(esito.risultati) <= 10
    assert all(r.contiene_dosi is True for r in esito.risultati)
    senza = cerca("patate farina brodo", client, EmbedderFinto(), CONFIG, k=10)
    assert any(r.contiene_dosi is False for r in senza.risultati)


def test_solo_dosi_al_massimo_k(client):
    esito = cerca("brodo", client, EmbedderFinto(), CONFIG, k=2, solo_dosi=True)
    assert len(esito.risultati) == 2


def test_solo_dosi_combinato_con_il_capitolo(client):
    punti = client.scroll(NOME, limit=1000)[0]
    capitoli = {p.payload["capitolo"] for p in punti if p.payload["contiene_dosi"]}
    capitolo = sorted(capitoli)[0]
    esito = cerca("brodo", client, EmbedderFinto(), CONFIG, k=10, capitolo=capitolo, solo_dosi=True)
    assert esito.risultati
    assert all(r.capitolo == capitolo and r.contiene_dosi for r in esito.risultati)


def test_filtro_inviato_a_qdrant(client):
    ricevuti = []
    vero = client.query_points

    def spia(*a, **kw):
        ricevuti.append(kw["query_filter"])
        return vero(*a, **kw)

    client.query_points = spia
    cerca("brodo", client, EmbedderFinto(), CONFIG, capitolo="Brodi, gelatina e sughi", solo_dosi=True)
    chiavi = {c.key for c in ricevuti[0].must}
    assert chiavi == {"capitolo", "contiene_dosi"}


def test_solo_dosi_senza_campo_da_errore(client_senza_campo):
    with pytest.raises(ErroreRag, match="rag.metadati"):
        cerca("brodo", client_senza_campo, EmbedderFinto(), CONFIG, solo_dosi=True)


def test_main_ricerca_passa_solo_dosi(capsys, monkeypatch):
    ricevuti = {}

    def finta(*a, **kw):
        ricevuti.update(kw)
        return EsitoRicerca([], 5, None, None)

    monkeypatch.setattr(ricerca, "carica_config_rag", lambda: CONFIG)
    monkeypatch.setattr(ricerca, "crea_client", lambda url: None)
    monkeypatch.setattr(ricerca, "cerca", finta)
    assert ricerca.main(["brodo", "--solo-dosi"]) == 0
    assert ricevuti["solo_dosi"] is True


def test_main_valutazione_passa_solo_dosi(capsys, monkeypatch):
    ricevuti = []

    def finta(domanda, client, embedder, config, k, **kw):
        ricevuti.append(kw.get("solo_dosi"))
        return EsitoRicerca([], k, None, None)

    monkeypatch.setattr(valutazione, "carica_config_rag", lambda: CONFIG)
    monkeypatch.setattr(valutazione, "crea_client", lambda url: None)
    monkeypatch.setattr(valutazione, "cerca", finta)
    assert valutazione.main(["--solo-dosi"]) == 0
    assert ricevuti and set(ricevuti) == {True}


def test_indice_booleano_nella_collezione():
    """Il server vero riporta l'indice; in memoria si verifica almeno che la chiamata non fallisca."""
    c = QdrantClient(":memory:")
    esegui_ingestion(CONFIG, EmbedderFinto(), c, attese=4)
    assert c.count(NOME, count_filter=models.Filter(must=[
        models.FieldCondition(key="contiene_dosi", match=models.MatchValue(value=True))
    ])).count > 0
