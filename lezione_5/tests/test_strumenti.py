import logging
from datetime import datetime, timezone

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from assistente.orologio import crea_orologio
from assistente.strumenti import crea_registro, esegui_chiamate

ISTANTE = datetime(2026, 10, 26, 11, 30, 41, tzinfo=timezone.utc)
TOKYO = "lunedì 26 ottobre 2026, 20:30:41 — Asia/Tokyo (UTC+09:00)"


@tool
def esplode(testo: str) -> str:
    """Strumento di prova che fallisce sempre."""
    raise RuntimeError("guasto interno")


@pytest.fixture
def registro():
    return crea_registro([crea_orologio(adesso=lambda: ISTANTE), esplode])


def _chiamata(nome, args, id_="c1"):
    return {"name": nome, "args": args, "id": id_, "type": "tool_call"}


def test_crea_registro_per_nome(registro):
    assert set(registro) == {"get_current_time", "esplode"}


def test_chiamata_singola(registro, caplog):
    caplog.set_level(logging.INFO, logger="strumenti")
    messaggio = AIMessage(content="", tool_calls=[_chiamata("get_current_time", {"timezone": "Asia/Tokyo"})])
    risposte = esegui_chiamate(registro, messaggio, passo=1, max_passi=3)
    assert len(risposte) == 1
    assert risposte[0].content == TOKYO
    assert risposte[0].tool_call_id == "c1"
    assert [(r.levelname, r.name, r.getMessage()) for r in caplog.records] == [
        ("INFO", "strumenti", f'passo 1/3 get_current_time {{"timezone": "Asia/Tokyo"}} -> {TOKYO}')
    ]


def test_due_chiamate_in_ordine(registro):
    messaggio = AIMessage(
        content="",
        tool_calls=[
            _chiamata("get_current_time", {"timezone": "Asia/Tokyo"}, "a"),
            _chiamata("get_current_time", {"timezone": "Europe/Rome"}, "b"),
        ],
    )
    risposte = esegui_chiamate(registro, messaggio, passo=2, max_passi=3)
    assert [r.tool_call_id for r in risposte] == ["a", "b"]
    assert "Asia/Tokyo" in risposte[0].content
    assert "Europe/Rome" in risposte[1].content


def test_strumento_sconosciuto(registro, caplog):
    caplog.set_level(logging.INFO, logger="strumenti")
    messaggio = AIMessage(content="", tool_calls=[_chiamata("meteo", {"citta": "Roma"})])
    [risposta] = esegui_chiamate(registro, messaggio, passo=1, max_passi=3)
    assert risposta.content == "Errore: strumento 'meteo' non disponibile"
    assert caplog.records[0].levelname == "WARNING"


def test_argomento_mancante(registro, caplog):
    caplog.set_level(logging.INFO, logger="strumenti")
    messaggio = AIMessage(content="", tool_calls=[_chiamata("get_current_time", {})])
    [risposta] = esegui_chiamate(registro, messaggio, passo=1, max_passi=3)
    assert risposta.content == "Errore: argomento 'timezone' mancante o non valido"
    assert caplog.records[0].levelname == "WARNING"


def test_invalid_tool_call(registro):
    messaggio = AIMessage(
        content="",
        invalid_tool_calls=[
            {"name": "get_current_time", "args": '{"timezone": ', "id": "x1",
             "error": "JSON non valido", "type": "invalid_tool_call"}
        ],
    )
    [risposta] = esegui_chiamate(registro, messaggio, passo=1, max_passi=3)
    assert risposta.content == "Errore: argomento 'timezone' mancante o non valido"
    assert risposta.tool_call_id == "x1"


def test_fuso_non_valido_registrato_come_warning(registro, caplog):
    caplog.set_level(logging.INFO, logger="strumenti")
    messaggio = AIMessage(content="", tool_calls=[_chiamata("get_current_time", {"timezone": "JST"})])
    [risposta] = esegui_chiamate(registro, messaggio, passo=1, max_passi=3)
    assert risposta.content.startswith("Errore: fuso orario 'JST' non valido")
    assert caplog.records[0].levelname == "WARNING"


def test_eccezione_generica(registro, caplog):
    caplog.set_level(logging.INFO, logger="strumenti")
    messaggio = AIMessage(content="", tool_calls=[_chiamata("esplode", {"testo": "x"})])
    [risposta] = esegui_chiamate(registro, messaggio, passo=1, max_passi=3)
    assert risposta.content == "Errore: esecuzione dello strumento non riuscita"
    assert caplog.records[0].levelname == "ERROR"
    assert "guasto interno" in caplog.records[0].getMessage()
