import logging
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from assistente.grafo import costruisci_grafo, instrada, limite_raggiunto
from assistente.orologio import crea_orologio
from assistente.strumenti import crea_registro
from finti import ModelloFinto, chiede_ora

ISTANTE = datetime(2026, 10, 26, 11, 30, 41, tzinfo=timezone.utc)
REGISTRO = crea_registro([crea_orologio(adesso=lambda: ISTANTE)])


def _stato(*messaggi, passi=0):
    return {"messages": list(messaggi), "passi_strumento": passi}


def _domanda(grafo, testo="Che ore sono a Tokyo?"):
    return grafo.invoke(_stato(HumanMessage(testo)))


def test_instrada_senza_tool_call():
    assert instrada(_stato(AIMessage("Ciao")), max_passi=3) == "fine"


def test_instrada_con_tool_call():
    assert instrada(_stato(chiede_ora("Asia/Tokyo")), max_passi=3) == "strumenti"


def test_instrada_al_limite():
    assert instrada(_stato(chiede_ora("Asia/Tokyo"), passi=3), max_passi=3) == "fine"


def test_instrada_invalid_tool_call():
    messaggio = AIMessage(
        content="",
        invalid_tool_calls=[{"name": "get_current_time", "args": "{", "id": "x",
                             "error": "JSON", "type": "invalid_tool_call"}],
    )
    assert instrada(_stato(messaggio), max_passi=3) == "strumenti"


def test_giro_completo(caplog):
    caplog.set_level(logging.INFO, logger="strumenti")
    modello = ModelloFinto([chiede_ora("Asia/Tokyo"), AIMessage("A Tokyo sono le 20:30.")])
    stato = _domanda(costruisci_grafo(modello, REGISTRO, max_passi=3))

    assert [type(m) for m in stato["messages"]] == [HumanMessage, AIMessage, ToolMessage, AIMessage]
    assert "Asia/Tokyo (UTC+09:00)" in stato["messages"][2].content
    assert stato["messages"][3].content == "A Tokyo sono le 20:30."
    assert stato["passi_strumento"] == 1
    assert not limite_raggiunto(stato)
    # la seconda chiamata al modello riceve il risultato dello strumento
    assert isinstance(modello.chiamate[1][-1], ToolMessage)
    assert len([r for r in caplog.records if r.levelname == "INFO"]) == 1


def test_risposta_diretta_senza_strumento():
    modello = ModelloFinto([AIMessage("Ciao Elia!")])
    stato = _domanda(costruisci_grafo(modello, REGISTRO, max_passi=3), "Ciao")
    assert [type(m) for m in stato["messages"]] == [HumanMessage, AIMessage]
    assert stato["passi_strumento"] == 0


def test_si_ferma_al_limite():
    modello = ModelloFinto([chiede_ora("Asia/Tokyo")])  # chiede sempre lo strumento
    stato = _domanda(costruisci_grafo(modello, REGISTRO, max_passi=3))
    assert len([m for m in stato["messages"] if isinstance(m, ToolMessage)]) == 3
    assert stato["passi_strumento"] == 3
    assert limite_raggiunto(stato)


def test_limite_alto_non_supera_ricorsione():
    modello = ModelloFinto([chiede_ora("Asia/Tokyo")])
    stato = _domanda(costruisci_grafo(modello, REGISTRO, max_passi=20))
    assert stato["passi_strumento"] == 20
    assert limite_raggiunto(stato)


def test_grafo_ha_nodi_espliciti():
    grafo = costruisci_grafo(ModelloFinto([AIMessage("x")]), REGISTRO, max_passi=3)
    nodi = set(grafo.get_graph().nodes) - {"__start__", "__end__"}
    assert nodi == {"modello", "strumenti"}


def test_debug_registra_i_messaggi_inviati(caplog):
    caplog.set_level(logging.DEBUG, logger="modello")
    modello = ModelloFinto([AIMessage("Ciao Elia!")])
    _domanda(costruisci_grafo(modello, REGISTRO, max_passi=3))
    inviati = [r.getMessage() for r in caplog.records if r.getMessage().startswith("messaggi inviati")]
    assert len(inviati) == 1 and "human" in inviati[0]


def test_debug_registra_la_chiamata_fallita(caplog):
    import pytest

    from finti import ModelloCheFallisce

    caplog.set_level(logging.DEBUG, logger="modello")
    with pytest.raises(ConnectionError):
        _domanda(costruisci_grafo(ModelloCheFallisce(ConnectionError("giù")), REGISTRO, max_passi=3))
    assert any(r.getMessage().startswith("chiamata -> errore") for r in caplog.records)
