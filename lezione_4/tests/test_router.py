import logging

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from assistente.config import Config
from assistente.riassunto import PREFISSO_RIASSUNTO
from assistente.modello import RAGIONAMENTO_DISATTIVATO
from pydantic import ValidationError

from assistente.router import (
    ISTRUZIONI_ROUTER,
    Classificazione,
    DomandaMista,
    classifica,
    domanda_mista,
    crea_router,
    messaggi_per_router,
)
from finti import FUORI, IN_AMBITO, MISTA, RouterFinto

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


# --- domande miste (specs §17/§18.4, V2c) ---


def test_schema_ordine_campi():
    assert list(Classificazione.model_fields) == ["motivo", "parti_fuori_ambito", "domanda_in_ambito", "categoria"]


def test_schema_campi_nuovi_obbligatori():
    with pytest.raises(ValidationError):
        Classificazione(motivo="x", categoria="conversazione")
    schema = Classificazione.model_json_schema()
    assert set(schema["required"]) == {"motivo", "parti_fuori_ambito", "domanda_in_ambito", "categoria"}


def test_istruzioni_chiedono_le_parti():
    assert "parti_fuori_ambito" in ISTRUZIONI_ROUTER
    assert "domanda_in_ambito" in ISTRUZIONI_ROUTER
    assert "stesse parole" in ISTRUZIONI_ROUTER


def test_istruzioni_parti_solo_dall_ultimo_messaggio():
    # Misura g7: dopo una domanda mista il router ripeteva le parti escluse del turno prima.
    testo = ISTRUZIONI_ROUTER.lower()
    assert "solo dall'ultimo messaggio" in testo
    assert "turni precedenti" in testo


def test_domanda_mista_estrae_la_riduzione():
    assert domanda_mista(MISTA, "Che ore sono a Tokyo? E dammi la ricetta della pizza") == DomandaMista("Che ore sono a Tokyo?", ["dammi la ricetta della pizza"])


def _esito(parti, domanda, categoria="conversazione"):
    return Classificazione(motivo="m", parti_fuori_ambito=parti, domanda_in_ambito=domanda, categoria=categoria)


@pytest.mark.parametrize("esito", [
    IN_AMBITO,                                             # nessuna parte fuori ambito
    FUORI,                                                 # tutta fuori ambito
    _esito(["ricetta"], "che ore sono?", "fuori_ambito"),  # categoria fuori ambito
    _esito(["", "   "], "che ore sono?"),                  # parti vuote
    _esito(["ricetta"], "  "),                             # domanda ridotta vuota
])
def test_domanda_mista_none_se_non_mista(esito):
    assert domanda_mista(esito, "che ore sono? e la ricetta?") is None


@pytest.mark.parametrize("domanda", [
    "Converti 3,7 km in miglia",
    "converti 3,7 KM in miglia!",
    "  Converti   3,7 km\nin miglia?  ",
])
def test_domanda_mista_none_se_la_riduzione_coincide_con_la_domanda(domanda):
    # Misura g8: il router ripeteva la parte esclusa del turno prima su una domanda tutta in ambito.
    esito = _esito(["consigliami un film"], "Converti 3,7 km in miglia.")
    assert domanda_mista(esito, domanda) is None


def test_domanda_mista_pulisce_spazi_e_parti_vuote():
    esito = _esito([" ricetta ", "", "barzelletta"], "  che ore\n sono?  ")
    assert domanda_mista(esito, "che ore sono? ricetta e barzelletta") == DomandaMista(
        "che ore sono?", ["ricetta", "barzelletta"]
    )


def test_messaggi_per_router_con_riassunto_nelle_istruzioni():
    storia = [HumanMessage("ciao"), AIMessage("Ciao!"), HumanMessage("e a Tokyo?")]
    senza = messaggi_per_router(storia, "x")
    assert messaggi_per_router(storia, "x", "") == senza
    con = messaggi_per_router(storia, "x", "Si chiama Elia.")
    assert con[0].content == f"{senza[0].content}\n\n{PREFISSO_RIASSUNTO} Si chiama Elia."
    assert con[1:] == senza[1:]
