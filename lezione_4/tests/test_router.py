import logging

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from assistente.config import Config
from assistente.modello import RAGIONAMENTO_DISATTIVATO
from assistente.router import (
    ISTRUZIONI_ROUTER,
    classifica,
    crea_router,
    messaggi_per_router,
)
from finti import FUORI, RouterFinto

CONFIG = Config(
    lm_base_url="http://localhost:1234/v1",
    lm_model="qwen/qwen3.5-9b",
    max_tool_steps=3,
    log_level="INFO",
    ambito_assistente="orari e calcoli",
    messaggio_rifiuto="Non posso aiutarti.",
)


def test_istruzioni_contengono_l_ambito():
    msgs = messaggi_per_router([HumanMessage("ciao")], "orari e calcoli")
    assert isinstance(msgs[0], SystemMessage)
    assert "orari e calcoli" in msgs[0].content


def test_istruzioni_non_nominano_strumenti():
    testo = ISTRUZIONI_ROUTER.lower()
    for parola in ["strument", "tool", "get_current_time", "convert_units", "calculate"]:
        assert parola not in testo


def test_istruzioni_seguiti_nel_contesto():
    testo = ISTRUZIONI_ROUTER.lower()
    assert "seguit" in testo
    assert "precedente" in testo


def test_solo_domande_e_risposte():
    chiamata = AIMessage(
        "", tool_calls=[{"name": "convert_units", "args": {}, "id": "c1", "type": "tool_call"}]
    )
    storia = [
        SystemMessage("prompt dell'agente"),
        HumanMessage("converti 2 km"),
        chiamata,
        ToolMessage("2 km = 1,24 mi", tool_call_id="c1"),
        AIMessage("Sono 1,24 mi."),
        HumanMessage("e 3 km?"),
    ]
    msgs = messaggi_per_router(storia, "x")
    assert isinstance(msgs[0], SystemMessage)
    assert "prompt dell'agente" not in msgs[0].content
    resto = msgs[1:]
    assert [(type(m), m.content) for m in resto] == [
        (HumanMessage, "converti 2 km"),
        (AIMessage, "Sono 1,24 mi."),
        (HumanMessage, "e 3 km?"),
    ]
    assert not any(isinstance(m, ToolMessage) or getattr(m, "tool_calls", None) for m in resto)


def test_seguito_di_un_rifiuto_vede_il_rifiuto():
    storia = [
        HumanMessage("ricetta della carbonara"),
        AIMessage("Non posso aiutarti."),
        HumanMessage("e quella dell'amatriciana?"),
    ]
    resto = messaggi_per_router(storia, "x")[1:]
    assert [m.content for m in resto] == [m.content for m in storia]


def test_classifica_restituisce_la_classificazione():
    assert classifica(RouterFinto([FUORI]), [HumanMessage("ricetta")], "x") == FUORI


def test_classifica_eccezione_fail_open(caplog):
    with caplog.at_level(logging.DEBUG, logger="router"):
        esito = classifica(RouterFinto([ConnectionError("giù")]), [HumanMessage("ciao")], "x")
    assert esito is None
    avvisi = [r for r in caplog.records if r.name == "router" and r.levelno == logging.WARNING]
    assert len(avvisi) == 1
    assert "-> agente" in avvisi[0].getMessage()


@pytest.mark.parametrize("uscita", [None, {"categoria": "fuori_ambito"}, "fuori_ambito"])
def test_classifica_output_non_valido(uscita, caplog):
    with caplog.at_level(logging.DEBUG, logger="router"):
        esito = classifica(RouterFinto([uscita]), [HumanMessage("ciao")], "x")
    assert esito is None
    avvisi = [r for r in caplog.records if r.name == "router" and r.levelno == logging.WARNING]
    assert len(avvisi) == 1
    assert "-> agente" in avvisi[0].getMessage()


def test_crea_router_usa_config():
    router = crea_router(CONFIG)
    chat = router.first
    assert chat.openai_api_base == "http://localhost:1234/v1"
    assert chat.model_name == "qwen/qwen3.5-9b"
    assert chat.request_timeout == 60
    assert chat.max_retries == 0
    assert chat.extra_body == RAGIONAMENTO_DISATTIVATO
    assert "tools" not in router.first.kwargs
