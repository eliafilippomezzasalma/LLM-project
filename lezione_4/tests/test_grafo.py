import logging
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from assistente.config import Config
from assistente.grafo import costruisci_grafo, dopo_revisore, dopo_router, instrada, limite_raggiunto
from assistente.orologio import crea_orologio
from assistente.revisore import PREFISSO_INDICAZIONE, Giudizio
from assistente.strumenti import crea_registro
from finti import (
    APPROVATA, FUORI, IN_AMBITO, MISTA, RESPINTA, RIFIUTO, ModelloFinto, RevisoreFinto, RouterFinto, chiede_ora,
    grafo_in_ambito,
)

ISTANTE = datetime(2026, 10, 26, 11, 30, 41, tzinfo=timezone.utc)
REGISTRO = crea_registro([crea_orologio(adesso=lambda: ISTANTE)])


def _stato(*messaggi, passi=0):
    return {"messages": list(messaggi), "passi_strumento": passi}


def _domanda(grafo, testo="Che ore sono a Tokyo?"):
    return grafo.invoke(_stato(HumanMessage(testo)))


def test_instrada_senza_tool_call():
    assert instrada(_stato(AIMessage("Ciao")), max_passi=3) == "revisore"


def test_instrada_con_tool_call():
    assert instrada(_stato(chiede_ora("Asia/Tokyo")), max_passi=3) == "strumenti"


def test_instrada_al_limite():
    assert instrada(_stato(chiede_ora("Asia/Tokyo"), passi=3), max_passi=3) == "fine"


def test_instrada():
    assert instrada(_stato(AIMessage("Ciao")), max_passi=3) == "revisore"
    assert instrada(_stato(chiede_ora("Asia/Tokyo"), passi=2), max_passi=3) == "strumenti"
    # al limite nel primo tentativo: fine (LimitePassaggiRaggiunto in Sessione)
    stato = _stato(chiede_ora("Asia/Tokyo"), passi=3)
    assert instrada({**stato, "ultima_proposta": None}, max_passi=3) == "fine"
    # al limite in un tentativo dopo la revisione: si restituisce l'ultima risposta proposta
    assert instrada({**stato, "ultima_proposta": AIMessage("prima")}, max_passi=3) == "ultima_risposta"
    # la risposta finale va al revisore anche dopo una revisione
    assert instrada({**_stato(AIMessage("seconda")), "ultima_proposta": AIMessage("prima")}, 3) == "revisore"


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


def test_testo_insieme_alle_chiamate_tolto_e_registrato(caplog):
    # Prova reale del 2026-11-13: il modello scriveva «17 × 23 = 391…» insieme alla chiamata a
    # days_between; vedendolo, la risposta finale riportava solo i giorni e l'utente, che vede
    # solo l'ultimo messaggio, perdeva gli altri risultati.
    caplog.set_level(logging.DEBUG)
    con_testo = chiede_ora("Asia/Tokyo").model_copy(update={"content": "Intanto: 17 × 23 = 391."})
    modello = ModelloFinto([con_testo, AIMessage("A Tokyo sono le 20:30.")])
    stato = _domanda(grafo_in_ambito(modello, REGISTRO, max_passi=3))

    chiamata = stato["messages"][1]
    assert chiamata.content == ""
    assert [c["name"] for c in chiamata.tool_calls] == ["get_current_time"]
    assert modello.chiamate[1][1].content == ""  # il modello non rivede il testo al passaggio dopo
    assert stato["messages"][-1].content == "A Tokyo sono le 20:30."
    assert any(
        r.name == "agente" and r.levelname == "DEBUG" and "Intanto: 17 × 23 = 391." in r.getMessage()
        for r in caplog.records
    )


def test_risposta_finale_senza_chiamate_conserva_il_testo():
    modello = ModelloFinto([AIMessage("Ciao!")])
    stato = _domanda(grafo_in_ambito(modello, REGISTRO, max_passi=3), "Ciao")
    assert stato["messages"][-1].content == "Ciao!"


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
    assert nodi == {"router", "agente", "strumenti", "rifiuto", "revisore", "ultima_risposta"}


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


def _grafo(modello, router, ambito="ambito di prova", revisore=None):
    return costruisci_grafo(
        modello, REGISTRO, 3, router=router, ambito=ambito, messaggio_rifiuto=RIFIUTO,
        revisore=revisore if revisore is not None else RevisoreFinto([APPROVATA]), max_revisioni=2,
    )


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

    esito = Classificazione(
        motivo='riga uno\nriga "due"', parti_fuori_ambito=[], domanda_in_ambito="x", categoria="conversazione"
    )
    _domanda(_grafo(ModelloFinto([AIMessage("x")]), RouterFinto([esito])))
    righe = _righe(caplog, "router", "INFO")
    assert len(righe) == 1 and "\n" not in righe[0]


def test_router_riceve_l_ambito():
    router = RouterFinto([IN_AMBITO])
    _domanda(_grafo(ModelloFinto([AIMessage("x")]), router, ambito="solo orari"))
    primo = router.chiamate[0][0]
    assert isinstance(primo, SystemMessage) and "solo orari" in primo.content


# --- revisore (specs §18) ---


def _proposte(stato):
    """Testi delle risposte finali proposte dall'agente nel turno."""
    return [m.content for m in stato["messages"] if isinstance(m, AIMessage) and not m.tool_calls]


def _indicazioni(messaggi):
    return [m for m in messaggi if isinstance(m, HumanMessage) and m.content.startswith(PREFISSO_INDICAZIONE)]


def test_dopo_revisore():
    assert dopo_revisore({"coerente": True, "revisioni": 0}, max_revisioni=2) == "fine"
    assert dopo_revisore({"coerente": None, "revisioni": 0}, max_revisioni=2) == "fine"  # revisore non valido
    assert dopo_revisore({}, max_revisioni=2) == "fine"
    assert dopo_revisore({"coerente": False, "revisioni": 1}, max_revisioni=2) == "agente"
    assert dopo_revisore({"coerente": False, "revisioni": 2}, max_revisioni=2) == "agente"
    assert dopo_revisore({"coerente": False, "revisioni": 3}, max_revisioni=2) == "fine"
    assert dopo_revisore({"coerente": False, "revisioni": 1}, max_revisioni=0) == "fine"


def test_coerente_al_primo_passaggio(caplog):
    # Evidenza 2: risposta coerente approvata al primo passaggio, una sola riga «revisore:».
    caplog.set_level(logging.INFO)
    modello = ModelloFinto([AIMessage("A Tokyo sono le 20:30.")])
    stato = _domanda(grafo_in_ambito(modello, REGISTRO))
    assert _righe(caplog, "revisore") == ['coerente=sì regola=nessuna motivo="risponde a tutto" -> fine']
    assert stato["messages"][-1].content == "A Tokyo sono le 20:30."
    assert [type(m) for m in stato["messages"]] == [HumanMessage, AIMessage]
    assert len(modello.chiamate) == 1


def test_risposta_parziale_rimandata(caplog):
    # Evidenza 1: domanda in due parti, risposta parziale rifiutata con il motivo, poi completa.
    caplog.set_level(logging.INFO)
    revisore = RevisoreFinto([RESPINTA, APPROVATA])
    modello = ModelloFinto([AIMessage("parte 1"), AIMessage("parte 1 e parte 2")])
    stato = _domanda(grafo_in_ambito(modello, REGISTRO, revisore=revisore, max_revisioni=2))
    assert stato["messages"][-1].content == "parte 1 e parte 2"
    assert len(modello.chiamate) == 2
    seconda = modello.chiamate[1]
    assert isinstance(seconda[-2], AIMessage) and seconda[-2].content == "parte 1"
    assert isinstance(seconda[-1], HumanMessage)
    assert seconda[-1].content.startswith("[Revisione] Regola violata: completezza.")
    assert "manca la seconda parte" in seconda[-1].content
    assert _righe(caplog, "revisore", "INFO") == [
        'coerente=no regola=completezza motivo="manca la seconda parte" -> agente (revisione 1/2)',
        'coerente=sì regola=nessuna motivo="risponde a tutto" -> fine',
    ]
    assert len(revisore.chiamate) == 2


def test_limite_revisioni(caplog):
    # Evidenza 3: revisore che rifiuta sempre -> MAX_REVISIONI + 1 revisioni, ultima risposta, WARNING.
    caplog.set_level(logging.INFO)
    modello = ModelloFinto([AIMessage("r1"), AIMessage("r2"), AIMessage("r3")])
    stato = _domanda(grafo_in_ambito(modello, REGISTRO, revisore=RevisoreFinto([RESPINTA]), max_revisioni=2))
    assert stato["messages"][-1].content == "r3"
    assert _righe(caplog, "revisore", "INFO") == [
        'coerente=no regola=completezza motivo="manca la seconda parte" -> agente (revisione 1/2)',
        'coerente=no regola=completezza motivo="manca la seconda parte" -> agente (revisione 2/2)',
        'coerente=no regola=completezza motivo="manca la seconda parte" -> fine',
    ]
    assert _righe(caplog, "revisore", "WARNING") == [
        "limite di 2 revisioni raggiunto, restituita l'ultima risposta"
    ]
    assert len(modello.chiamate) == 3
    assert not limite_raggiunto(stato)


def test_limite_revisioni_zero(caplog):
    caplog.set_level(logging.INFO)
    modello = ModelloFinto([AIMessage("r1"), AIMessage("r2")])
    revisore = RevisoreFinto([RESPINTA])
    stato = _domanda(grafo_in_ambito(modello, REGISTRO, revisore=revisore, max_revisioni=0))
    assert stato["messages"][-1].content == "r1"
    assert len(revisore.chiamate) == 1 and len(modello.chiamate) == 1
    assert _righe(caplog, "revisore", "INFO") == ['coerente=no regola=completezza motivo="manca la seconda parte" -> fine']
    assert _righe(caplog, "revisore", "WARNING") == [
        "limite di 0 revisioni raggiunto, restituita l'ultima risposta"
    ]


def test_valore_a_mente_rimandato():
    # Evidenza 4: valore non preso da uno strumento -> rimandato, l'orologio viene eseguito.
    revisore = RevisoreFinto([Giudizio(motivo="valore non preso da uno strumento", regola="valore_a_mente", coerente=False), APPROVATA])
    modello = ModelloFinto(
        [AIMessage("Mancano 41 giorni."), chiede_ora("Europe/Rome"), AIMessage("Mancano 41 giorni.")]
    )
    stato = _domanda(grafo_in_ambito(modello, REGISTRO, revisore=revisore), "Quanti giorni mancano a Natale?")
    messaggi = stato["messages"]
    indicazione = _indicazioni(messaggi)[0]
    assert "valore non preso da uno strumento" in indicazione.content
    strumenti = [i for i, m in enumerate(messaggi) if isinstance(m, ToolMessage)]
    assert len(strumenti) == 1 and strumenti[0] > messaggi.index(indicazione)
    assert messaggi[strumenti[0]].name == "get_current_time"
    assert messaggi[-1].content == "Mancano 41 giorni."


def test_strumenti_dopo_la_revisione_contatore_azzerato():
    revisore = RevisoreFinto([RESPINTA, APPROVATA])
    modello = ModelloFinto([
        chiede_ora("Asia/Tokyo", "c1"), AIMessage("r1"), chiede_ora("Europe/Rome", "c2"), AIMessage("r2"),
    ])
    stato = _domanda(grafo_in_ambito(modello, REGISTRO, max_passi=1, revisore=revisore))
    assert [m.tool_call_id for m in stato["messages"] if isinstance(m, ToolMessage)] == ["c1", "c2"]
    assert stato["messages"][-1].content == "r2"
    assert stato["passi_strumento"] == 1
    assert not limite_raggiunto(stato)


def test_limite_strumenti_dopo_revisione(caplog):
    # Dopo una revisione il modello chiede strumenti oltre il limite: si restituisce l'ultima
    # risposta proposta invece di un errore all'utente (specs §18.3).
    caplog.set_level(logging.INFO)
    revisore = RevisoreFinto([RESPINTA, APPROVATA])
    modello = ModelloFinto([AIMessage("prima"), chiede_ora("Europe/Rome", "c1"), chiede_ora("Asia/Tokyo", "c2")])
    stato = _domanda(grafo_in_ambito(modello, REGISTRO, max_passi=1, revisore=revisore))
    assert stato["messages"][-1].content == "prima"
    assert not stato["messages"][-1].tool_calls
    assert not limite_raggiunto(stato)
    assert len(revisore.chiamate) == 1
    assert _righe(caplog, "revisore", "WARNING") == [
        "limite degli strumenti nel tentativo dopo la revisione, restituita l'ultima risposta"
    ]
    # la risposta restituita è un messaggio nuovo in coda, non quella proposta spostata
    assert _proposte(stato) == ["prima", "prima"]


def test_limite_strumenti_primo_tentativo(caplog):
    caplog.set_level(logging.DEBUG)
    revisore = RevisoreFinto([APPROVATA])
    stato = _domanda(grafo_in_ambito(ModelloFinto([chiede_ora("Asia/Tokyo")]), REGISTRO, revisore=revisore))
    assert limite_raggiunto(stato)
    assert revisore.chiamate == []
    assert [r for r in caplog.records if r.name == "revisore"] == []


def test_errore_agente_dopo_revisione_restituisce_ultima_risposta(caplog):
    # Errore del modello nel tentativo dopo una revisione: si restituisce l'ultima risposta
    # proposta invece di un errore all'utente (specs §18.12), senza ripassare dal revisore.
    caplog.set_level(logging.INFO)
    revisore = RevisoreFinto([RESPINTA, APPROVATA])
    modello = ModelloFinto([AIMessage("prima"), ConnectionError("giù")])
    stato = _domanda(grafo_in_ambito(modello, REGISTRO, revisore=revisore))
    assert stato["messages"][-1].content == "prima"
    assert not limite_raggiunto(stato)
    assert len(modello.chiamate) == 2 and len(revisore.chiamate) == 1
    assert _righe(caplog, "revisore", "WARNING") == [
        "errore del modello nel tentativo dopo la revisione (ConnectionError: giù), restituita l'ultima risposta"
    ]
    assert len(_righe(caplog, "revisore", "INFO")) == 1
    # la risposta restituita è un messaggio nuovo in coda, non quella proposta spostata
    assert _proposte(stato) == ["prima", "prima"]


def test_errore_agente_primo_tentativo_si_propaga():
    import pytest

    revisore = RevisoreFinto([APPROVATA])
    with pytest.raises(ConnectionError):
        _domanda(grafo_in_ambito(ModelloFinto([ConnectionError("giù")]), REGISTRO, revisore=revisore))
    assert revisore.chiamate == []


def test_instrada_dopo_errore_dell_agente():
    stato = {**_stato(AIMessage("prima")), "errore_agente": True}
    assert instrada(stato, max_passi=3) == "fine"


def test_revisore_in_errore_fail_open(caplog):
    caplog.set_level(logging.INFO)
    modello = ModelloFinto([AIMessage("Sono le 20:30.")])
    stato = _domanda(grafo_in_ambito(modello, REGISTRO, revisore=RevisoreFinto([ConnectionError("giù")])))
    assert stato["messages"][-1].content == "Sono le 20:30."
    assert len(modello.chiamate) == 1
    assert stato["coerente"] is None
    avvisi = _righe(caplog, "revisore", "WARNING")
    assert len(avvisi) == 1 and "risposta non valida" in avvisi[0]  # scritto da rivedi, non ripetuto
    assert _righe(caplog, "revisore", "INFO") == []


def test_rifiuto_non_passa_dal_revisore():
    revisore = RevisoreFinto([RESPINTA])
    stato = _domanda(_grafo(ModelloFinto([AIMessage("no")]), RouterFinto([FUORI]), revisore=revisore), "ricetta")
    assert stato["messages"][-1].content == RIFIUTO
    assert revisore.chiamate == []


def test_revisore_riceve_l_ambito():
    revisore = RevisoreFinto([APPROVATA])
    grafo = _grafo(ModelloFinto([AIMessage("x")]), RouterFinto([IN_AMBITO]), ambito="solo orari", revisore=revisore)
    _domanda(grafo)
    primo = revisore.chiamate[0][0]
    assert isinstance(primo, SystemMessage) and "solo orari" in primo.content


def test_revisore_vede_il_turno_dall_inizio():
    # inizio_turno impostato dal router: con una cronologia, il turno parte dall'ultima domanda.
    revisore = RevisoreFinto([APPROVATA])
    grafo = grafo_in_ambito(ModelloFinto([AIMessage("Prego.")]), REGISTRO, revisore=revisore)
    stato = grafo.invoke(_stato(
        SystemMessage("prompt"), HumanMessage("Ciao"), AIMessage("Ciao!"), HumanMessage("Grazie"),
    ))
    assert stato["inizio_turno"] == 3
    turno = revisore.chiamate[0][-1].content
    assert "Domanda dell'utente: Grazie" in turno and "Risposta proposta: Prego." in turno


def test_motivo_su_una_riga_nel_log(caplog):
    caplog.set_level(logging.INFO)
    giudizio = Giudizio(motivo='riga uno\n  riga "due"', regola="nessuna", coerente=True)
    _domanda(grafo_in_ambito(ModelloFinto([AIMessage("x")]), REGISTRO, revisore=RevisoreFinto([giudizio])))
    assert _righe(caplog, "revisore", "INFO") == ['coerente=sì regola=nessuna motivo="riga uno riga "due"" -> fine']


def test_rifiuto_senza_regola_trattato_come_coerente(caplog):
    # Rifiuto pignolo fuori dalle tre regole: la risposta passa e le revisioni non aumentano.
    caplog.set_level(logging.INFO)
    revisore = RevisoreFinto([Giudizio(motivo="mancano i secondi", regola="nessuna", coerente=False)])
    modello = ModelloFinto([AIMessage("A Tokyo sono le 20:30."), AIMessage("non deve servire")])
    stato = _domanda(grafo_in_ambito(modello, REGISTRO, revisore=revisore, max_revisioni=3))
    assert stato["messages"][-1].content == "A Tokyo sono le 20:30."
    assert len(modello.chiamate) == 1
    assert len(revisore.chiamate) == 1
    assert stato["revisioni"] == 0
    assert stato["coerente"] is True
    assert _righe(caplog, "revisore", "INFO") == [
        'coerente=no regola=nessuna motivo="mancano i secondi" -> fine (rifiuto senza regola, trattato come coerente)'
    ]
    assert not _righe(caplog, "revisore", "WARNING")
    assert not _indicazioni(stato["messages"])


def test_coerente_con_regola_resta_approvazione(caplog):
    caplog.set_level(logging.INFO)
    revisore = RevisoreFinto([Giudizio(motivo="ok", regola="completezza", coerente=True)])
    modello = ModelloFinto([AIMessage("risposta"), AIMessage("non deve servire")])
    stato = _domanda(grafo_in_ambito(modello, REGISTRO, revisore=revisore, max_revisioni=3))
    assert stato["messages"][-1].content == "risposta"
    assert len(modello.chiamate) == 1
    assert not _indicazioni(stato["messages"])
    assert _righe(caplog, "revisore", "INFO") == ['coerente=sì regola=completezza motivo="ok" -> fine']


def test_limite_predefinito_tre_revisioni(caplog):
    # MAX_REVISIONI predefinito 3: quattro risposte proposte, poi l'ultima con il WARNING.
    caplog.set_level(logging.INFO)
    modello = ModelloFinto([AIMessage(f"r{n}") for n in range(1, 6)])
    revisore = RevisoreFinto([RESPINTA])
    stato = _domanda(grafo_in_ambito(modello, REGISTRO, revisore=revisore, max_revisioni=Config.max_revisioni))
    assert stato["messages"][-1].content == "r4"
    assert len(revisore.chiamate) == 4
    assert _righe(caplog, "revisore", "INFO")[-2:] == [
        'coerente=no regola=completezza motivo="manca la seconda parte" -> agente (revisione 3/3)',
        'coerente=no regola=completezza motivo="manca la seconda parte" -> fine',
    ]
    assert _righe(caplog, "revisore", "WARNING") == [
        "limite di 3 revisioni raggiunto, restituita l'ultima risposta"
    ]


def test_limite_alto_con_revisioni_non_supera_ricorsione():
    # Ogni tentativo usa tutti i 20 passaggi agli strumenti, poi risponde; il revisore rifiuta
    # sempre: devono scattare i nostri limiti, non il limite di ricorsione di LangGraph.
    risposte = []
    for n in range(1, 4):
        risposte += [chiede_ora("Asia/Tokyo", f"c{n}")] * 20 + [AIMessage(f"r{n}")]
    modello = ModelloFinto(risposte)
    revisore = RevisoreFinto([RESPINTA])
    stato = _domanda(grafo_in_ambito(modello, REGISTRO, max_passi=20, revisore=revisore, max_revisioni=2))
    assert stato["messages"][-1].content == "r3"
    assert len(revisore.chiamate) == 3
    assert len([m for m in stato["messages"] if isinstance(m, ToolMessage)]) == 60


# --- domande miste (V2c, specs §18.4) ---


def test_domanda_mista_revisore_vede_domanda_ridotta(caplog):
    caplog.set_level(logging.INFO)
    revisore = RevisoreFinto([APPROVATA])
    modello = ModelloFinto([chiede_ora("Asia/Tokyo"), AIMessage("A Tokyo sono le 20:30.")])
    domanda = "Che ore sono a Tokyo? E dammi la ricetta della pizza"
    stato = _domanda(_grafo(modello, RouterFinto([MISTA]), revisore=revisore), domanda)
    turno = revisore.chiamate[0][-1].content
    assert "Domanda dell'utente (solo le parti in ambito): Che ore sono a Tokyo?" in turno
    assert "non chiederle mai): dammi la ricetta della pizza" in turno
    assert "Domanda dell'utente: " not in turno
    # L'agente vede la domanda intera.
    assert any(isinstance(m, HumanMessage) and m.content == domanda for m in modello.chiamate[0])
    assert stato["mista"] is not None
    assert _righe(caplog, "router", "INFO")[1] == (
        'domanda mista: al revisore solo "Che ore sono a Tokyo?" (escluse: "dammi la ricetta della pizza")'
    )


def test_domanda_non_mista_nessun_log_e_domanda_originale(caplog):
    caplog.set_level(logging.INFO)
    revisore = RevisoreFinto([APPROVATA])
    stato = _domanda(_grafo(ModelloFinto([AIMessage("x")]), RouterFinto([IN_AMBITO]), revisore=revisore))
    assert len(_righe(caplog, "router", "INFO")) == 1
    assert stato["mista"] is None
    assert "Domanda dell'utente: Che ore sono a Tokyo?" in revisore.chiamate[0][-1].content


def test_riduzione_uguale_alla_domanda_non_e_mista(caplog):
    # Misura g8: parte esclusa ripetuta dal turno prima, ma la domanda è tutta in ambito.
    caplog.set_level(logging.INFO)
    revisore = RevisoreFinto([APPROVATA])
    stato = _domanda(_grafo(ModelloFinto([AIMessage("x")]), RouterFinto([MISTA]), revisore=revisore),
                     "che ore sono a Tokyo")
    assert stato["mista"] is None
    assert len(_righe(caplog, "router", "INFO")) == 1
    assert "Domanda dell'utente: che ore sono a Tokyo" in revisore.chiamate[0][-1].content


def test_domanda_mista_azzerata_al_turno_dopo():
    revisore = RevisoreFinto([APPROVATA])
    grafo = _grafo(ModelloFinto([AIMessage("Sono le 20:30."), AIMessage("Prego.")]),
                   RouterFinto([MISTA, IN_AMBITO]), revisore=revisore)
    stato = _domanda(grafo, "Che ore sono a Tokyo? E dammi la ricetta della pizza")
    assert stato["mista"] is not None
    stato = grafo.invoke({**stato, "messages": [*stato["messages"], HumanMessage("Grazie")]})
    assert stato["mista"] is None
    assert "Domanda dell'utente: Grazie" in revisore.chiamate[1][-1].content


def test_domanda_mista_respinta_mantiene_la_riduzione():
    # Dopo una revisione il revisore rivede la risposta con la stessa domanda ridotta.
    revisore = RevisoreFinto([RESPINTA, APPROVATA])
    modello = ModelloFinto([AIMessage("Non so."), chiede_ora("Asia/Tokyo"), AIMessage("A Tokyo sono le 20:30.")])
    _domanda(_grafo(modello, RouterFinto([MISTA]), revisore=revisore),
             "Che ore sono a Tokyo? E dammi la ricetta della pizza")
    assert len(revisore.chiamate) == 2
    assert all("solo le parti in ambito" in c[-1].content for c in revisore.chiamate)
