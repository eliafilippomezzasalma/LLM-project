from pathlib import Path

import pytest

from assistente.config import carica_config
from rag.config import ConfigRag, ErroreConfigurazioneRag, carica_config_rag
from rag.errori import ErroreRag

BASE = {"LM_BASE_URL": "http://h:1234/v1", "EMBEDDING_MODEL": "m"}
CARTELLA_PROGETTO = Path(__file__).resolve().parent.parent


def test_predefiniti():
    config = carica_config_rag(BASE)
    assert config == ConfigRag(
        lm_base_url="http://h:1234/v1",
        embedding_model="m",
        qdrant_url="http://localhost:6333",
        collezione="ricette",
        corpus=CARTELLA_PROGETTO / "dati" / "artusi.txt",
        strategia="paragrafi",
        dimensione=1200,
        overlap=200,
        k_max=10,
    )


def test_corpus_assoluto_resta_invariato(tmp_path):
    file = tmp_path / "libro.txt"
    assert carica_config_rag({**BASE, "RAG_CORPUS": str(file)}).corpus == file


def test_valori_personalizzati():
    config = carica_config_rag(
        {
            **BASE,
            "QDRANT_URL": "http://q:6333",
            "QDRANT_COLLECTION": "altra",
            "CHUNK_STRATEGIA": "finestra",
            "CHUNK_DIMENSIONE": "500",
            "CHUNK_OVERLAP": "50",
            "RICERCA_K_MAX": "3",
        }
    )
    assert (config.qdrant_url, config.collezione, config.strategia) == ("http://q:6333", "altra", "finestra")
    assert (config.dimensione, config.overlap, config.k_max) == (500, 50, 3)


def test_embedding_model_obbligatorio():
    with pytest.raises(ErroreConfigurazioneRag, match="EMBEDDING_MODEL"):
        carica_config_rag({"LM_BASE_URL": "http://h:1234/v1"})


def test_lm_base_url_obbligatoria():
    with pytest.raises(ErroreConfigurazioneRag, match="LM_BASE_URL"):
        carica_config_rag({"EMBEDDING_MODEL": "m"})


def test_errore_e_un_errore_rag():
    assert issubclass(ErroreConfigurazioneRag, ErroreRag)


@pytest.mark.parametrize(
    "extra, nome",
    [
        ({"CHUNK_STRATEGIA": "frasi"}, "CHUNK_STRATEGIA"),
        ({"CHUNK_DIMENSIONE": "0"}, "CHUNK_DIMENSIONE"),
        ({"CHUNK_DIMENSIONE": "abc"}, "CHUNK_DIMENSIONE"),
        ({"CHUNK_OVERLAP": "-1"}, "CHUNK_OVERLAP"),
        ({"CHUNK_DIMENSIONE": "1200", "CHUNK_OVERLAP": "1200"}, "CHUNK_OVERLAP"),
        ({"RICERCA_K_MAX": "0"}, "RICERCA_K_MAX"),
    ],
)
def test_valori_non_validi(extra, nome):
    with pytest.raises(ErroreConfigurazioneRag, match=nome):
        carica_config_rag({**BASE, **extra})


def test_assistente_non_richiede_variabili_rag():
    config = carica_config(
        {
            "LM_BASE_URL": "http://localhost:1234/v1",
            "LM_MODEL": "x",
            "AMBITO_ASSISTENTE": "orari",
            "MESSAGGIO_RIFIUTO": "no",
        }
    )
    assert config.lm_model == "x"


# §21: leve del retrieval


def test_leve_predefinite_come_paragrafo_20():
    config = carica_config_rag(BASE)
    assert config.prefisso_documento == "" and config.prefisso_domanda == ""
    assert config.titolo_nel_testo is False and config.riscrittura is False


def test_leve_attivate():
    config = carica_config_rag({
        **BASE,
        "EMBEDDING_PREFISSO_DOCUMENTO": "search_document:",
        "EMBEDDING_PREFISSO_DOMANDA": " search_query: ",
        "INDICE_CON_TITOLO": "Sì",
        "RICERCA_RISCRITTURA": "si",
        "RISCRITTURA_MODEL": "qwen/qwen3.5-9b",
    })
    assert config.prefisso_documento == "search_document:"
    assert config.prefisso_domanda == "search_query:"
    assert config.titolo_nel_testo is True and config.riscrittura is True
    assert config.modello_riscrittura == "qwen/qwen3.5-9b"


def test_booleano_non_valido():
    with pytest.raises(ErroreConfigurazioneRag, match="INDICE_CON_TITOLO"):
        carica_config_rag({**BASE, "INDICE_CON_TITOLO": "forse"})


def test_riscrittura_senza_modello():
    with pytest.raises(ErroreConfigurazioneRag, match="RISCRITTURA_MODEL"):
        carica_config_rag({**BASE, "RICERCA_RISCRITTURA": "si"})
