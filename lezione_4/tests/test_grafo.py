import logging
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from assistente.grafo import costruisci_grafo, dopo_router, instrada, limite_raggiunto
from assistente.orologio import crea_orologio
from assistente.strumenti import crea_registro
from finti import FUORI, IN_AMBITO, RIFIUTO, ModelloFinto, RouterFinto, chiede_ora, grafo_in_ambito

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
    caplog.set_level(logging.INFO)
    modello = ModelloFinto([chiede_ora("Asia/Tokyo"), AIMessage("A Tokyo sono le 20:30.")])
    stato = _domanda(grafo_in_ambito(modello, REGISTRO, max_passi=3))

    assert [type(m) for m in stato["messages"]] == [HumanMessage, AIMessage, ToolMessage, AIMessage]
    assert "Asia/Tokyo (UTC+09:00)" in stato["messages"][2].content
    assert stato["messages"][3].content == "A Tokyo sono le 20:30."
    assert stato["passi_strumento"] == 1
    assert not limite_raggiunto(stato)
    # la seconda chiamata al modello riceve il risultato dello strumento
    assert isinstance(modello.chiamate[1][-1], ToolMessage)
    assert len([r for r in caplog.records if r.levelname == "INFO" and r.name == "strumenti"]) == 1


def test_risposta_diretta_senza_strumento():
    modello = ModelloFinto([AIMessage("Ciao Elia!")])
    stato = _domanda(grafo_in_ambito(modello, REGISTRO, max_passi=3), "Ciao")
    assert [type(m) for m in stato["messages"]] == [HumanMessage, AIMessage]
    assert stato["passi_strumento"] == 0


def test_si_ferma_al_limite():
    modello = ModelloFinto([chiede_ora("Asia/Tokyo")])  # chiede sempre lo strumento
    stato = _domanda(grafo_in_ambito(modello, REGISTRO, max_passi=3))
    assert len([m for m in stato["messages"] if isinstance(m, ToolMessage)]) == 3
    assert stato["passi_strumento"] == 3
    assert limite_raggiunto(stato)


def test_limite_alto_non_supera_ricorsione():
    modello = ModelloFinto([chiede_ora("Asia/Tokyo")])
    stato = _domanda(grafo_in_ambito(modello, REGISTRO, max_passi=20))
    assert stato["passi_strumento"] == 20
    assert limite_raggiunto(stato)


def test_grafo_ha_nodi_espliciti():
    grafo = grafo_in_ambito(ModelloFinto([AIMessage("x")]), REGISTRO, max_passi=3)
    nodi = set(grafo.get_graph().nodes) - {"__start__", "__end__"}
    assert nodi == {"router", "agente", "strumenti", "rifiuto"}


def test_debug_registra_i_messaggi_inviati(caplog):
    caplog.set_level(logging.DEBUG, logger="agente")
    modello = ModelloFinto([AIMessage("Ciao Elia!")])
    _domanda(grafo_in_ambito(modello, REGISTRO, max_passi=3))
    inviati = [r.getMessage() for r in caplog.records if r.getMessage().startswith("messaggi inviati")]
    assert len(inviati) == 1 and "human" in inviati[0]


def test_debug_registra_la_chiamata_fallita(caplog):
    import pytest

    from finti import ModelloCheFallisce

    caplog.set_level(logging.DEBUG, logger="agente")
    with pytest.raises(ConnectionError):
        _domanda(grafo_in_ambito(ModelloCheFallisce(ConnectionError("giù")), REGISTRO, max_passi=3))
    assert any(r.getMessage().startswith("chiamata -> errore") for r in caplog.records)


def _grafo(modello, router, ambito="ambito di prova"):
    return costruisci_grafo(modello, REGISTRO, 3, router=router, ambito=ambito, messaggio_rifiuto=RIFIUTO)


def _righe(caplog, logger, livello=None):
    return [r.getMessage() for r in caplog.records
            if r.name == logger and (livello is None or r.levelname == livello)]


def test_dopo_router():
    assert dopo_router({"categoria": "fuori_ambito"}) == "rifiuto"
    assert dopo_router({"categoria": "conversazione"}) == "agente"
    assert dopo_router({"categoria": None}) == "agente"
    assert dopo_router({}) == "agente"


def test_in_ambito_passa_all_agente(caplog):
    caplog.set_level(logging.INFO)
    modello = ModelloFinto([chiede_ora("Asia/Tokyo"), AIMessage("Sono le 20:30.")])
    stato = _domanda(_grafo(modello, RouterFinto([IN_AMBITO])))
    assert stato["messages"][-1].content == "Sono le 20:30."
    assert stato["categoria"] == "conversazione"
    righe = _righe(caplog, "router", "INFO")
    assert len(righe) == 1
    assert "categoria=conversazione" in righe[0]
    assert 'motivo="domanda su orari"' in righe[0]
    assert "-> agente" in righe[0]
    assert _righe(caplog, "agente", "INFO") == ["chiamata 1", "chiamata 2"]


def test_fuori_ambito_rifiuta_senza_agente(caplog):
    caplog.set_level(logging.DEBUG)
    modello = ModelloFinto([AIMessage("non deve parlare")])
    stato = _domanda(_grafo(modello, RouterFinto([FUORI])), "dammi una ricetta")
    assert isinstance(stato["messages"][-1], AIMessage)
    assert stato["messages"][-1].content == RIFIUTO
    assert modello.chiamate == []
    assert [r for r in caplog.records if r.name == "agente"] == []
    assert any("-> rifiuto" in r for r in _righe(caplog, "router", "INFO"))
    assert _righe(caplog, "rifiuto", "INFO") == ["risposta fissa"]
    assert not any("ricetta di cucina" in str(m.content) for m in stato["messages"])


def test_router_in_errore_passa_all_agente(caplog):
    caplog.set_level(logging.INFO)
    modello = ModelloFinto([AIMessage("Ciao!")])
    stato = _domanda(_grafo(modello, RouterFinto([ConnectionError("giù")])), "Ciao")
    assert stato["messages"][-1].content == "Ciao!"
    assert len(modello.chiamate) == 1
    assert len(_righe(caplog, "router", "WARNING")) == 1
    assert _righe(caplog, "router", "INFO") == []
    assert stato["categoria"] is None and stato["motivo"] is None


def test_motivo_su_una_riga(caplog):
    caplog.set_level(logging.INFO)
    from assistente.router import Classificazione

    esito = Classificazione(categoria="conversazione", motivo='riga uno\nriga "due"')
    _domanda(_grafo(ModelloFinto([AIMessage("x")]), RouterFinto([esito])))
    righe = _righe(caplog, "router", "INFO")
    assert len(righe) == 1 and "\n" not in righe[0]


def test_router_riceve_l_ambito():
    router = RouterFinto([IN_AMBITO])
    _domanda(_grafo(ModelloFinto([AIMessage("x")]), router, ambito="solo orari"))
    primo = router.chiamate[0][0]
    assert isinstance(primo, SystemMessage) and "solo orari" in primo.content
