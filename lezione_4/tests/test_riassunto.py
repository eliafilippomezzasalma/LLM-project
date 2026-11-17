import logging
from math import ceil

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from assistente.config import Config
from assistente.modello import RAGIONAMENTO_DISATTIVATO
from assistente.riassunto import (
    PREFISSO_RIASSUNTO,
    ISTRUZIONI_RIASSUNTO,
    coppie_complete,
    conversazione,
    crea_riassuntore,
    messaggi_con_riassunto,
    messaggi_per_riassunto,
    misura,
    punto_di_taglio,
    riassumi,
    stima_token,
    testo_con_riassunto as aggiungi_riassunto,
)
from finti import RiassuntoreFinto

CONFIG = Config(
    lm_base_url="http://localhost:1234/v1",
    lm_model="qwen/qwen3.5-9b",
    max_tool_steps=3,
    log_level="INFO",
    ambito_assistente="orari e calcoli",
    messaggio_rifiuto="Non posso aiutarti.",
)


def _chiamata(nome: str, args: dict, id_: str) -> dict:
    return {"name": nome, "args": args, "id": id_, "type": "tool_call"}


def _turno(domanda: str, risposta: str, chiamate=()) -> list:
    """[Human, (AI con tool_calls, ToolMessage)..., AI(risposta)]; ogni chiamata è (nome, args, risultato)."""
    messaggi = [HumanMessage(domanda)]
    for i, (nome, args, risultato) in enumerate(chiamate):
        id_ = f"{domanda[:3]}{i}"
        messaggi.append(AIMessage("", tool_calls=[_chiamata(nome, args, id_)]))
        messaggi.append(ToolMessage(risultato, tool_call_id=id_))
    messaggi.append(AIMessage(risposta))
    return messaggi


def _turno_complesso(n: int) -> list:
    """Turno con due chiamate in un solo messaggio e un secondo giro di strumenti."""
    return [
        HumanMessage(f"domanda {n}"),
        AIMessage("", tool_calls=[_chiamata("calculate", {"expression": "1+1"}, f"a{n}"),
                                  _chiamata("calculate", {"expression": "2+2"}, f"b{n}")]),
        ToolMessage("2", tool_call_id=f"a{n}"),
        ToolMessage("4", tool_call_id=f"b{n}"),
        AIMessage("", tool_calls=[_chiamata("calculate", {"expression": "3+3"}, f"c{n}")]),
        ToolMessage("6", tool_call_id=f"c{n}"),
        AIMessage(f"risposta {n}"),
    ]


def test_conta_messaggi_senza_sistema():
    msgs = [SystemMessage("s"), HumanMessage("h"), AIMessage("a"), HumanMessage("h2")]
    assert misura(msgs, "messaggi") == 3
    assert conversazione(msgs) == msgs[1:]


def test_stima_token():
    msgs = [
        SystemMessage("x" * 400),
        HumanMessage("a" * 10),
        AIMessage("", tool_calls=[_chiamata("calculate", {"expression": "2+2"}, "c1")]),
    ]
    attesi = ceil((10 + len('{"expression": "2+2"}')) / 4)
    assert stima_token(msgs) == attesi
    assert misura(msgs, "token") == attesi


def test_taglio_tiene_domanda_e_ultimi_n_turni():
    turni = [_turno(f"d{i}", f"r{i}") for i in range(4)]
    conv = [m for t in turni for m in t] + [HumanMessage("nuova")]
    taglio = punto_di_taglio(conv, 2)
    assert conv[taglio] is turni[2][0]


def test_taglio_niente_da_togliere():
    due = [m for i in range(2) for m in _turno(f"d{i}", f"r{i}")] + [HumanMessage("nuova")]
    assert punto_di_taglio(due, 2) == 0
    uno = _turno("d0", "r0") + [HumanMessage("nuova")]
    assert punto_di_taglio(uno, 2) == 0


def test_taglio_mai_tra_chiamata_e_risultato():
    conv = [m for n in range(5) for m in _turno_complesso(n)] + [HumanMessage("nuova")]
    for n in range(1, 5):
        taglio = punto_di_taglio(conv, n)
        assert taglio > 0
        assert coppie_complete(conv[taglio:])
        assert coppie_complete(conv[:taglio])


def test_coppie_complete():
    normale = _turno("d", "r", [("calculate", {"expression": "1+1"}, "2")])
    assert coppie_complete(normale)
    assert coppie_complete(_turno_complesso(0))
    senza_risultato = [HumanMessage("d"), AIMessage("", tool_calls=[_chiamata("calculate", {}, "x")])]
    assert not coppie_complete(senza_risultato)
    orfano = [ToolMessage("2", tool_call_id="x"), AIMessage("r")]
    assert not coppie_complete(orfano)


def test_testo_con_riassunto():
    assert aggiungi_riassunto("Sei un assistente.", "") == "Sei un assistente."
    assert aggiungi_riassunto("Sei un assistente.", "   ") == "Sei un assistente."
    assert aggiungi_riassunto("Sei un assistente.", "Si chiama Elia.").endswith(
        f"{PREFISSO_RIASSUNTO} Si chiama Elia."
    )


def test_messaggi_con_riassunto():
    msgs = [SystemMessage("Sei un assistente."), HumanMessage("h"), AIMessage("a")]
    assert messaggi_con_riassunto(msgs, "") is msgs
    nuovi = messaggi_con_riassunto(msgs, "Si chiama Elia.")
    assert [isinstance(m, SystemMessage) for m in nuovi] == [True, False, False]
    assert "Sei un assistente." in nuovi[0].content
    assert "Si chiama Elia." in nuovi[0].content
    assert nuovi[1] is msgs[1] and nuovi[2] is msgs[2]
    assert msgs[0].content == "Sei un assistente."


def test_presentazione_dei_tolti():
    tolti = _turno("converti 5 miglia", "Fatto.",
                   [("convert_units", {"value": 5, "from_unit": "mi", "to_unit": "km"}, "5 mi = 8,0467 km")])
    tolti += [HumanMessage("ricetta della carbonara"), AIMessage("Non posso aiutarti.")]
    msgs = messaggi_per_riassunto("Si chiama Elia.", tolti)
    assert isinstance(msgs[0], SystemMessage) and msgs[0].content == ISTRUZIONI_RIASSUNTO
    assert isinstance(msgs[1], HumanMessage)
    testo = msgs[1].content
    assert "Riassunto precedente: Si chiama Elia." in testo
    assert "Utente: ricetta della carbonara" in testo
    assert "Assistente: Non posso aiutarti." in testo
    assert 'convert_units({"value": 5' in testo
    assert "8,0467" not in testo
    assert "Riassunto precedente: (nessuno)" in messaggi_per_riassunto("", tolti)[1].content


def test_istruzioni():
    testo = ISTRUZIONI_RIASSUNTO.lower()
    for chiave in ["inizia sempre il riassunto", "nome", "preferenze", "rifiutat", "usa solo i numeri scritti dall'utente", "mai la risposta", "conserva ogni domanda", "unico riassunto"]:
        assert chiave in testo


def test_riassumi_ripulisce():
    modello = RiassuntoreFinto(["<think>x</think> Si chiama Elia. "])
    assert riassumi(modello, "", _turno("ciao", "ciao")) == "Si chiama Elia."
    assert len(modello.chiamate) == 1


@pytest.mark.parametrize("esito", [RuntimeError("giù"), "", "   ", "<think>x</think>"])
def test_riassumi_fail_open(esito, caplog):
    with caplog.at_level(logging.WARNING, logger="riassunto"):
        assert riassumi(RiassuntoreFinto([esito]), "", _turno("ciao", "ciao")) is None
    avvisi = [r for r in caplog.records if r.name == "riassunto" and r.levelno == logging.WARNING]
    assert len(avvisi) == 1
    assert "cronologia invariata" in avvisi[0].getMessage()


def test_crea_riassuntore_usa_config():
    chat = crea_riassuntore(CONFIG)
    assert chat.openai_api_base == "http://localhost:1234/v1"
    assert chat.model_name == "qwen/qwen3.5-9b"
    assert chat.request_timeout == 60
    assert chat.max_retries == 0
    assert chat.extra_body == RAGIONAMENTO_DISATTIVATO
    assert isinstance(chat, ChatOpenAI)  # nessun bind di strumenti né output strutturato
