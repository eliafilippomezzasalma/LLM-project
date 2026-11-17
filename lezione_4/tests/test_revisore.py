import logging

import pytest
from pydantic import ValidationError
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from assistente.config import Config
from assistente.riassunto import PREFISSO_RIASSUNTO
from assistente.modello import RAGIONAMENTO_DISATTIVATO
from assistente.revisore import (
    ISTRUZIONI_REVISORE,
    Giudizio,
    crea_revisore,
    indicazione,
    messaggi_per_revisore,
    numeri_italiani,
    respinta,
    rivedi,
)
from assistente.router import DomandaMista
from finti import APPROVATA, RESPINTA, RevisoreFinto

CONFIG = Config(
    lm_base_url="http://localhost:1234/v1",
    lm_model="qwen/qwen3.5-9b",
    max_tool_steps=3,
    log_level="INFO",
    ambito_assistente="orari e calcoli",
    messaggio_rifiuto="Non posso aiutarti.",
)


def chiamata(nome: str, args: dict, id_: str) -> AIMessage:
    return AIMessage("", tool_calls=[{"name": nome, "args": args, "id": id_, "type": "tool_call"}])


def test_istruzioni_contengono_l_ambito():
    msgs = messaggi_per_revisore([HumanMessage("ciao"), AIMessage("Ciao!")], 0, "orari e calcoli")
    assert isinstance(msgs[0], SystemMessage)
    assert "orari e calcoli" in msgs[0].content


def test_istruzioni_non_nominano_strumenti():
    testo = ISTRUZIONI_REVISORE.lower()
    for nome in ["get_current_time", "convert_units", "calculate", "days_between", "compute_deadline"]:
        assert nome not in testo


def test_istruzioni_valore_a_mente_esplicito():
    testo = ISTRUZIONI_REVISORE.lower()
    assert "anche se" in testo
    assert "false" in testo or "non coerente" in testo


def test_schema_ordine_campi():
    assert list(Giudizio.model_fields) == ["motivo", "regola", "coerente"]
    with pytest.raises(ValidationError):
        Giudizio(motivo="manca il calcolo", coerente=False)


def test_istruzioni_nominano_le_regole():
    for nome in ["completezza", "contraddizione", "valore_a_mente", "nessuna"]:
        assert nome in ISTRUZIONI_REVISORE


def test_respinta_solo_con_regola():
    assert respinta(RESPINTA)
    assert not respinta(APPROVATA)
    assert not respinta(Giudizio(motivo="mancano i secondi", regola="nessuna", coerente=False))
    assert not respinta(Giudizio(motivo="ok", regola="completezza", coerente=True))


def test_contesto_solo_domande_e_risposte():
    storia = [
        SystemMessage("prompt dell'agente"),
        HumanMessage("che ore sono a Tokyo?"),
        chiamata("get_current_time", {"timezone": "Asia/Tokyo"}, "c0"),
        ToolMessage("Tokyo 09:00", tool_call_id="c0"),
        AIMessage("Sono le 09:00."),
        HumanMessage("converti 2 km in miglia"),
        chiamata("convert_units", {"value": 2}, "c1"),
        ToolMessage("2 km = 1,2427 mi", tool_call_id="c1"),
        AIMessage("2 km sono 1,2427 miglia."),
    ]
    msgs = messaggi_per_revisore(storia, 5, "x")
    assert isinstance(msgs[0], SystemMessage)
    assert "prompt dell'agente" not in msgs[0].content
    assert [(type(m), m.content) for m in msgs[1:3]] == [
        (HumanMessage, "che ore sono a Tokyo?"),
        (AIMessage, "Sono le 09:00."),
    ]
    assert len(msgs) == 4
    turno = msgs[3]
    assert isinstance(turno, HumanMessage)
    for atteso in ["converti 2 km in miglia", "convert_units", "1,2427 mi",
                   "Risposta proposta: 2 km sono 1,2427 miglia."]:
        assert atteso in turno.content
    assert "get_current_time" not in turno.content


def test_turno_senza_strumenti():
    msgs = messaggi_per_revisore([HumanMessage("ciao"), AIMessage("Ciao!")], 0, "x")
    assert "nessuno" in msgs[-1].content


def test_turno_con_indicazione():
    storia = [
        HumanMessage("che ore sono a Tokyo e quanto fa 2+2?"),
        chiamata("get_current_time", {"timezone": "Asia/Tokyo"}, "c1"),
        ToolMessage("09:00", tool_call_id="c1"),
        AIMessage("Sono le 09:00."),
        indicazione("manca il calcolo", "completezza"),
        chiamata("calculate", {"expression": "2+2"}, "c2"),
        ToolMessage("4", tool_call_id="c2"),
        AIMessage("Sono le 09:00 e 2+2 fa 4."),
    ]
    testo = messaggi_per_revisore(storia, 0, "x")[-1].content
    assert "get_current_time" in testo and "calculate" in testo
    assert "manca il calcolo" in testo
    assert "Risposta proposta: Sono le 09:00 e 2+2 fa 4." in testo


def test_risposta_con_think_o_vuota():
    con_think = [HumanMessage("ora?"), AIMessage("<think>x</think>Sono le 9.")]
    assert "Risposta proposta: Sono le 9." in messaggi_per_revisore(con_think, 0, "x")[-1].content
    vuota = [HumanMessage("ora?"), AIMessage("")]
    assert "Risposta proposta: (nessuna risposta dal modello)" in messaggi_per_revisore(vuota, 0, "x")[-1].content


def test_indicazione_su_una_riga():
    msg = indicazione('manca\n"x"', "completezza")
    assert isinstance(msg, HumanMessage)
    assert msg.content.startswith("[Revisione]")
    assert "\n" not in msg.content
    assert msg.content.endswith("Correggila: rispondi di nuovo all'ultima domanda dell'utente.")


def test_indicazione_nomina_la_regola():
    msg = indicazione("manca il calcolo", "completezza")
    assert msg.content.startswith("[Revisione] Regola violata: completezza.")
    assert msg.content == (
        "[Revisione] Regola violata: completezza. La risposta precedente non va bene: manca il calcolo "
        "Correggila: rispondi di nuovo all'ultima domanda dell'utente."
    )


def test_rivedi_restituisce_il_giudizio():
    assert rivedi(RevisoreFinto([RESPINTA]), [HumanMessage("ciao"), AIMessage("Ciao")], 0, "x") == RESPINTA
    assert rivedi(RevisoreFinto([APPROVATA]), [HumanMessage("ciao"), AIMessage("Ciao")], 0, "x") == APPROVATA


def test_rivedi_eccezione_fail_open(caplog):
    with caplog.at_level(logging.DEBUG, logger="revisore"):
        esito = rivedi(RevisoreFinto([ConnectionError("giù")]), [HumanMessage("ciao")], 0, "x")
    assert esito is None
    avvisi = [r for r in caplog.records if r.name == "revisore" and r.levelno == logging.WARNING]
    assert len(avvisi) == 1
    assert "-> fine" in avvisi[0].getMessage()


@pytest.mark.parametrize("uscita", [None, {"coerente": False}, "no"])
def test_rivedi_output_non_valido(uscita, caplog):
    with caplog.at_level(logging.DEBUG, logger="revisore"):
        esito = rivedi(RevisoreFinto([uscita]), [HumanMessage("ciao")], 0, "x")
    assert esito is None
    avvisi = [r for r in caplog.records if r.name == "revisore" and r.levelno == logging.WARNING]
    assert len(avvisi) == 1
    assert "-> fine" in avvisi[0].getMessage()


def test_crea_revisore_usa_config():
    revisore = crea_revisore(CONFIG)
    chat = revisore.first
    assert chat.openai_api_base == "http://localhost:1234/v1"
    assert chat.model_name == "qwen/qwen3.5-9b"
    assert chat.request_timeout == 60
    assert chat.max_retries == 0
    assert chat.extra_body == RAGIONAMENTO_DISATTIVATO
    assert "tools" not in revisore.first.kwargs


def test_numeri_italiani():
    assert numeri_italiani("80 km = 49.7097 mi") == "80 km = 49,7097 mi"
    assert numeri_italiani("(12.5 + 7.5) * 4 = 80") == "(12,5 + 7,5) * 4 = 80"
    orario = "sabato 14 novembre 2026, 15:42:19 — Europe/Rome (UTC+01:00)"
    assert numeri_italiani(orario) == orario
    date = "Il 2027-01-01 viene 48 giorni dopo il 2026-11-14."
    assert numeri_italiani(date) == date
    assert numeri_italiani("versione 1.2.3") == "versione 1.2.3"
    assert numeri_italiani("-3.5 h") == "-3,5 h"


def test_turno_risultati_in_formato_italiano():
    storia = [
        HumanMessage("quanti km sono 26.2 miglia?"),
        chiamata("convert_units", {"value": 26.2, "from_unit": "mi", "to_unit": "km"}, "c1"),
        ToolMessage("26.2 mi = 42.1648 km", tool_call_id="c1"),
        AIMessage("Sono 42.16 km."),
    ]
    testo = messaggi_per_revisore(storia, 0, "x")[-1].content
    assert "26,2 mi = 42,1648 km" in testo
    assert '"value": 26.2' in testo
    assert "Risposta proposta: Sono 42.16 km." in testo


def test_istruzioni_non_parlano_di_separatori():
    testo = ISTRUZIONI_REVISORE.lower()
    assert "virgola" not in testo
    assert "punto" not in testo


# --- domande miste (V2c) ---

MISTA_RIDOTTA = DomandaMista("Che ore sono a Tokyo?", ["dammi la ricetta della pizza", "raccontami una barzelletta"])


def _turno_misto():
    return [
        HumanMessage("Che ore sono a Tokyo? E dammi la ricetta della pizza e raccontami una barzelletta"),
        chiamata("get_current_time", {"timezone": "Asia/Tokyo"}, "c1"),
        ToolMessage("Tokyo 20:30", tool_call_id="c1"),
        AIMessage("A Tokyo sono le 20:30. Per ricette e barzellette non posso aiutarti."),
    ]


def test_turno_misto_mostra_solo_le_parti_in_ambito():
    testo = messaggi_per_revisore(_turno_misto(), 0, "x", MISTA_RIDOTTA)[-1].content
    righe = testo.splitlines()
    assert righe[0] == "Domanda dell'utente (solo le parti in ambito): Che ore sono a Tokyo?"
    assert righe[1] == (
        "Parti fuori ambito già escluse (l'assistente fa bene a non rispondere, non chiederle mai): "
        "dammi la ricetta della pizza; raccontami una barzelletta"
    )
    assert "Domanda dell'utente: " not in testo
    assert "get_current_time" in testo
    assert testo.endswith("Risposta proposta: A Tokyo sono le 20:30. Per ricette e barzellette non posso aiutarti.")


def test_turno_senza_mista_mostra_la_domanda_originale():
    testo = messaggi_per_revisore(_turno_misto(), 0, "x")[-1].content
    assert testo.splitlines()[0].startswith("Domanda dell'utente: Che ore sono a Tokyo? E dammi la ricetta")
    assert "Parti fuori ambito" not in testo


def test_rivedi_passa_la_mista_al_revisore():
    revisore = RevisoreFinto([APPROVATA])
    assert rivedi(revisore, _turno_misto(), 0, "x", MISTA_RIDOTTA) == APPROVATA
    assert "solo le parti in ambito" in revisore.chiamate[0][-1].content


def test_messaggi_per_revisore_con_riassunto_nelle_istruzioni():
    storia = [HumanMessage("ciao"), AIMessage("Ciao!")]
    senza = messaggi_per_revisore(storia, 0, "x")
    assert messaggi_per_revisore(storia, 0, "x", riassunto="") == senza
    con = messaggi_per_revisore(storia, 0, "x", riassunto="Si chiama Elia.")
    assert con[0].content == f"{senza[0].content}\n\n{PREFISSO_RIASSUNTO} Si chiama Elia."
    assert con[1:] == senza[1:]
