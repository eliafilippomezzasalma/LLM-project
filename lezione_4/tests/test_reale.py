"""Prova con il modello vero in LM Studio: attivarla con RUN_REAL_TESTS=1."""

import os
import re

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from assistente.config import carica_config
from assistente.grafo import costruisci_grafo, limite_raggiunto
from assistente.modello import crea_modello, pulisci_ragionamento
from assistente.orologio import crea_orologio
from assistente.revisore import crea_revisore, respinta, rivedi
from assistente.router import classifica, crea_router, domanda_mista
from assistente.sessione import PROMPT_SISTEMA
from assistente.strumenti import crea_registro

pytestmark = [
    pytest.mark.reale,
    pytest.mark.skipif(os.environ.get("RUN_REAL_TESTS") != "1", reason="serve RUN_REAL_TESTS=1 e LM Studio attivo"),
]


def test_tokyo_usa_lo_strumento():
    config = carica_config()
    strumenti = [crea_orologio()]
    grafo = costruisci_grafo(
        crea_modello(config, strumenti),
        crea_registro(strumenti),
        config.max_tool_steps,
        router=crea_router(config),
        ambito=config.ambito_assistente,
        messaggio_rifiuto=config.messaggio_rifiuto,
        revisore=crea_revisore(config),
        max_revisioni=config.max_revisioni,
    )

    stato = grafo.invoke({
        "messages": [SystemMessage(PROMPT_SISTEMA), HumanMessage("Che ore sono a Tokyo?")],
        "passi_strumento": 0,
    })

    risultati = [m.content for m in stato["messages"] if isinstance(m, ToolMessage)]
    assert any("Asia/Tokyo" in r and not r.startswith("Errore") for r in risultati), risultati
    assert not limite_raggiunto(stato)
    finale = stato["messages"][-1]
    assert isinstance(finale, AIMessage)
    assert pulisci_ragionamento(finale.text)
    print("\nStrumento:", risultati, "\nRisposta:", pulisci_ragionamento(finale.text))


def _chiedi_con_strumenti_mcp(domanda):
    """Pone la domanda all'assistente completo, collegato come in main().

    Orologio + convertitore + calcolatrice + scadenze, con la nota gestita da con_nota.
    Restituisce i risultati degli strumenti raggruppati per nome e la risposta finale.
    """
    risultati, finale, _ = _chiedi_con_argomenti(domanda)
    return risultati, finale


def _chiedi_con_argomenti(domanda):
    """Come _chiedi_con_strumenti_mcp, ma restituisce anche gli argomenti delle chiamate per nome.

    La domanda passa da Sessione.chiedi, come nella chat vera (così la nota viene aggiunta se
    il modello la omette); il grafo è avvolto solo per leggere i passaggi intermedi.
    """
    from assistente.nota import NotaNonNormativa, con_nota
    from assistente.sessione import Sessione
    from assistente.terminale import collega_calcolatrice, collega_convertitore, collega_scadenze

    config = carica_config()
    remoti = [collega_convertitore(), collega_calcolatrice(), collega_scadenze()]
    try:
        assert all(remoti), "un server MCP non si è avviato"
        nota = NotaNonNormativa()
        strumenti = con_nota([crea_orologio(), *(s for r in remoti for s in r.strumenti())], nota)
        grafo = costruisci_grafo(
            crea_modello(config, strumenti),
            crea_registro(strumenti),
            config.max_tool_steps,
            router=crea_router(config),
            ambito=config.ambito_assistente,
            messaggio_rifiuto=config.messaggio_rifiuto,
            revisore=crea_revisore(config),
            max_revisioni=config.max_revisioni,
        )
        catturato = {}

        class GrafoSpia:
            def invoke(self, stato, *args, **kwargs):
                catturato["stato"] = grafo.invoke(stato, *args, **kwargs)
                return catturato["stato"]

        finale = Sessione(GrafoSpia(), nota).chiedi(domanda)
        stato = catturato["stato"]
    finally:
        for remoto in remoti:
            if remoto:
                remoto.chiudi()
    risultati: dict[str, list[str]] = {}
    argomenti: dict[str, list[dict]] = {}
    for m in stato["messages"]:
        if isinstance(m, ToolMessage):
            risultati.setdefault(m.name, []).append(m.content)
        elif isinstance(m, AIMessage):
            for chiamata in m.tool_calls:
                argomenti.setdefault(chiamata["name"], []).append(chiamata["args"])
    print("\nStrumenti:", risultati, "\nArgomenti:", argomenti, "\nRisposta:", finale)
    return risultati, finale, argomenti


def test_km_in_miglia_usa_il_convertitore():
    risultati, finale = _chiedi_con_strumenti_mcp("Converti 10 km in miglia")
    chiamate = risultati.get("convert_units", [])
    assert any(c.startswith("10 km = 6.21371 mi") for c in chiamate), chiamate
    assert "6,2" in finale or "6.2" in finale


def test_kg_in_metri_nessun_risultato_inventato():
    # Il modello di solito chiama lo strumento (tra 8 e 10 volte su 12 per giro, 21 su 24 nell'ultimo giro, 2026-11-03),
    # ma non sempre; in ogni caso non deve inventare un numero.
    risultati, finale = _chiedi_con_strumenti_mcp("Converti 5 kg in metri")
    chiamate = risultati.get("convert_units", [])
    assert all(c.startswith("Errore:") for c in chiamate), chiamate
    assert finale
    assert not re.search(r"\d+(?:[.,]\d+)?\s*(?:m|metri)\b", finale), finale
    print("Strumento usato:", bool(chiamate))


def test_espressione_usa_la_calcolatrice():
    risultati, finale = _chiedi_con_strumenti_mcp("Quanto fa (3,5 + 2) * 4?")
    chiamate = risultati.get("calculate", [])
    assert any(c.endswith("= 22") for c in chiamate), risultati
    assert "22" in finale


def test_divisione_per_zero_usa_la_calcolatrice():
    # Severo per scelta dell'utente: anche un calcolo impossibile va fatto con lo strumento.
    risultati, finale = _chiedi_con_strumenti_mcp("Quanto fa 10 / 0?")
    chiamate = risultati.get("calculate", [])
    assert chiamate, f"la calcolatrice non è stata chiamata: {finale!r}"
    assert all(c == "Errore: divisione per zero" for c in chiamate), chiamate
    assert finale
    assert not re.search(r"=\s*-?\d", finale), finale
    assert "infinit" not in finale.lower(), finale


def test_scadenza_spostata_con_nota():
    risultati, finale = _chiedi_con_strumenti_mcp(
        "Ho un termine che parte dal 25/03/2026 e dura un mese: quando scade?"
    )
    chiamate = risultati.get("compute_deadline", [])
    assert any(c.startswith("Scadenza: 2026-04-27") for c in chiamate), risultati
    assert "2026-04-27" in finale, finale
    # La data calcolata e il motivo vanno sempre riportati; il formato ISO della data calcolata no:
    # il modello a volte la riscrive in italiano (limite misurato, vedi README).
    assert any(d in finale for d in ("2026-04-25", "25/04/2026", "25 aprile")), finale
    assert "Liberazione" in finale or "sabato" in finale.lower(), finale
    assert "valore legale" in finale.lower(), finale


def test_domanda_da_oggi_usa_orologio_e_scadenze():
    risultati, finale = _chiedi_con_strumenti_mcp("Quanti giorni mancano al 25/12/2040?")
    assert risultati.get("get_current_time"), risultati
    chiamate = [c for c in risultati.get("days_between", []) if not c.startswith("Errore:")]
    assert chiamate, risultati
    giorni = re.search(r"viene (\d+) giorn", chiamate[-1]).group(1)
    assert giorni in finale.replace(".", ""), finale


def test_formato_italiano_convertito():
    risultati, finale, argomenti = _chiedi_con_argomenti("Il 2 giugno 2027 è festivo?")
    assert {"date": "2027-06-02"} in argomenti.get("date_info", []), argomenti
    assert "Festa della Repubblica" in finale, finale


def test_anno_fuori_intervallo_senza_data_inventata():
    risultati, finale = _chiedi_con_strumenti_mcp("Che giorno della settimana è il 2045-03-15?")
    chiamate = [c for nome in ("date_info", "days_between", "compute_deadline") for c in risultati.get(nome, [])]
    assert chiamate, f"nessuno strumento delle scadenze chiamato: {finale!r}"
    assert all(c.startswith("Errore:") for c in chiamate), chiamate
    giorni = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
    assert not any(g in finale.lower() for g in giorni), finale


def test_router_in_ambito_reale():
    config = carica_config()
    domanda = "Che ore sono a Tokyo?"
    esito = classifica(crea_router(config), [HumanMessage(domanda)], config.ambito_assistente)
    assert esito is not None
    assert esito.categoria == "conversazione", esito


def test_router_fuori_ambito_reale(caplog):
    config = carica_config()
    domanda = "Dammi la ricetta della carbonara"
    router = crea_router(config)
    esito = classifica(router, [HumanMessage(domanda)], config.ambito_assistente)
    assert esito is not None
    assert esito.categoria == "fuori_ambito", esito

    strumenti = [crea_orologio()]
    grafo = costruisci_grafo(
        crea_modello(config, strumenti),
        crea_registro(strumenti),
        config.max_tool_steps,
        router=router,
        ambito=config.ambito_assistente,
        messaggio_rifiuto=config.messaggio_rifiuto,
        revisore=crea_revisore(config),
        max_revisioni=config.max_revisioni,
    )
    with caplog.at_level("DEBUG", logger="agente"):
        stato = grafo.invoke({
            "messages": [SystemMessage(PROMPT_SISTEMA), HumanMessage(domanda)],
            "passi_strumento": 0,
        })
    assert stato["messages"][-1].content == config.messaggio_rifiuto
    assert not [r for r in caplog.records if r.name == "agente"]


# ── Revisore della risposta (specs.md §18) ──────────────────────────────────────

def _turno(domanda, passi, risposta):
    """Costruisce un turno: domanda, poi (strumento, argomenti, risultato) per ogni passo, poi la risposta."""
    messaggi = [HumanMessage(domanda)]
    for i, (nome, argomenti, risultato) in enumerate(passi, start=1):
        id_chiamata = f"call_{i}"
        messaggi.append(AIMessage("", tool_calls=[{"name": nome, "args": argomenti, "id": id_chiamata}]))
        messaggi.append(ToolMessage(risultato, tool_call_id=id_chiamata, name=nome))
    messaggi.append(AIMessage(risposta))
    return messaggi


def _giudica(messaggi):
    config = carica_config()
    giudizio = rivedi(crea_revisore(config), messaggi, 0, config.ambito_assistente)
    assert giudizio is not None, "il revisore non ha dato un giudizio valido"
    print("\nGiudizio:", giudizio)
    return giudizio


_CONVERSIONE = ("convert_units", {"value": 10, "from_unit": "mi", "to_unit": "km"}, "10 mi = 16.0934 km")


def test_revisore_respinge_risposta_parziale_reale():
    messaggi = _turno(
        "Converti 10 miglia in km e calcola 15 per 4", [_CONVERSIONE], "10 miglia sono 16,0934 km."
    )
    assert respinta(_giudica(messaggi))


def test_revisore_respinge_valore_a_mente_reale():
    messaggi = _turno("Quanti giorni mancano a Natale?", [], "Mancano 41 giorni.")
    assert respinta(_giudica(messaggi))


def test_revisore_approva_risposta_completa_reale():
    messaggi = _turno(
        "Quanti giorni mancano a Natale?",
        [
            ("get_current_time", {"timezone": "Europe/Rome"},
             "sabato 14 novembre 2026, 10:00:00 — Europe/Rome (UTC+01:00)"),
            ("days_between", {"from_date": "2026-11-14", "to_date": "2026-12-25"},
             "Il 2026-12-25 viene 41 giorni dopo 2026-11-14."),
        ],
        "Oggi è sabato 14 novembre 2026: a Natale (25 dicembre) mancano 41 giorni.",
    )
    assert not respinta(_giudica(messaggi))


def test_revisore_ignora_parte_fuori_ambito_reale():
    messaggi = _turno(
        "converti 5 miglia in km e dammi una ricetta",
        [("convert_units", {"value": 5, "from_unit": "mi", "to_unit": "km"}, "5 mi = 8.04672 km")],
        "5 miglia sono 8,04672 km. Per la ricetta non posso aiutarti: non rientra nei miei compiti.",
    )
    assert not respinta(_giudica(messaggi))


def test_router_estrae_le_parti_di_una_domanda_mista_reale():
    config = carica_config()
    domanda = "Che ore sono a Tokyo? E dammi la ricetta della pizza margherita"
    esito = classifica(crea_router(config), [HumanMessage(domanda)], config.ambito_assistente)
    print("\nClassificazione:", esito)
    assert esito is not None and esito.categoria == "conversazione", esito
    mista = domanda_mista(esito, domanda)
    assert mista is not None, esito
    assert "tokyo" in mista.domanda_in_ambito.lower() and "pizza" not in mista.domanda_in_ambito.lower()
    assert any("pizza" in parte.lower() for parte in mista.parti_fuori_ambito)


@pytest.mark.parametrize(
    "precedente, risposta, domanda",
    [
        (
            "Converti 5 miglia in km e dammi la ricetta della pizza",
            "5 miglia sono circa 8,05 km. Per la ricetta non posso aiutarti: non rientra nei miei compiti.",
            "Quali sono le festività di aprile 2027?",
        ),
        (
            "Converti 3,7 km in miglia e consigliami un film",
            "3,7 km sono circa 2,3 miglia. Per il film non posso aiutarti: non rientra nei miei compiti.",
            "e in piedi?",
        ),
    ],
)
def test_router_non_ripete_le_parti_escluse_del_turno_prima_reale(precedente, risposta, domanda):
    # Misura g7: dopo una domanda mista il router segnava «mista» anche la domanda seguente.
    config = carica_config()
    cronologia = [HumanMessage(precedente), AIMessage(risposta), HumanMessage(domanda)]
    esito = classifica(crea_router(config), cronologia, config.ambito_assistente)
    print("\nClassificazione:", esito)
    assert esito is not None and esito.categoria == "conversazione", esito
    assert domanda_mista(esito, domanda) is None, esito


def test_revisore_approva_risposta_giusta_a_domanda_mista_reale():
    # Catena vera router -> riduzione -> revisore (V2c): la parte fuori ambito non va pretesa.
    config = carica_config()
    domanda = "Converti 5 miglia in km e scrivimi una poesia sul mare"
    esito = classifica(crea_router(config), [HumanMessage(domanda)], config.ambito_assistente)
    mista = domanda_mista(esito, domanda) if esito is not None else None
    print("\nClassificazione:", esito)
    assert mista is not None, esito
    messaggi = _turno(
        domanda,
        [("convert_units", {"value": 5, "from_unit": "mi", "to_unit": "km"}, "5 mi = 8.04672 km")],
        "5 miglia sono circa 8,05 km. Per la poesia non posso aiutarti: non rientra nei miei compiti.",
    )
    giudizio = rivedi(crea_revisore(config), messaggi, 0, config.ambito_assistente, mista)
    print("Giudizio:", giudizio)
    assert giudizio is not None and not respinta(giudizio)


class _ModelloMisto:
    """Prime due chiamate scritte a mano (strumento, poi risposta parziale); dalla terza il modello vero."""

    def __init__(self, vero):
        self.vero = vero
        self.chiamate = 0

    def invoke(self, messaggi, config=None, **kw):
        self.chiamate += 1
        if self.chiamate == 1:
            nome, argomenti, _ = _CONVERSIONE
            return AIMessage("", tool_calls=[{"name": nome, "args": argomenti, "id": "call_misto"}])
        if self.chiamate == 2:
            ultimo = next(m for m in reversed(messaggi) if isinstance(m, ToolMessage))
            return AIMessage(f"Ecco la conversione: {ultimo.content}.")
        return self.vero.invoke(messaggi, config, **kw)


def _righe_revisore(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "revisore"]


def _approvata(riga):
    """Approvazione, anche come rifiuto senza regola (trattato come coerente)."""
    return "coerente=sì" in riga or "trattato come coerente" in riga


def test_parziale_poi_completa_reale(caplog):
    from assistente.terminale import collega_calcolatrice, collega_convertitore

    config = carica_config()
    remoti = [collega_convertitore(), collega_calcolatrice()]
    try:
        assert all(remoti), "un server MCP non si è avviato"
        strumenti = [crea_orologio(), *(s for r in remoti for s in r.strumenti())]
        grafo = costruisci_grafo(
            _ModelloMisto(crea_modello(config, strumenti)),
            crea_registro(strumenti),
            config.max_tool_steps,
            router=crea_router(config),
            ambito=config.ambito_assistente,
            messaggio_rifiuto=config.messaggio_rifiuto,
            revisore=crea_revisore(config),
            max_revisioni=config.max_revisioni,
        )
        with caplog.at_level("INFO", logger="revisore"):
            stato = grafo.invoke({
                "messages": [
                    SystemMessage(PROMPT_SISTEMA),
                    HumanMessage("Converti 10 miglia in km e calcola 15 per 4"),
                ],
                "passi_strumento": 0,
            })
    finally:
        for remoto in remoti:
            if remoto:
                remoto.chiudi()
    righe = _righe_revisore(caplog)
    finale = stato["messages"][-1].content
    print("\nRevisore:", righe, "\nRisposta:", finale)
    assert any("-> agente (revisione" in r for r in righe), righe
    assert _approvata(righe[-1]), righe
    assert "60" in finale, finale


def test_coerente_al_primo_passaggio_reale(caplog):
    from assistente.nota import NotaNonNormativa, con_nota
    from assistente.terminale import collega_calcolatrice, collega_convertitore, collega_scadenze

    config = carica_config()
    remoti = [collega_convertitore(), collega_calcolatrice(), collega_scadenze()]
    try:
        assert all(remoti), "un server MCP non si è avviato"
        strumenti = con_nota([crea_orologio(), *(s for r in remoti for s in r.strumenti())], NotaNonNormativa())
        grafo = costruisci_grafo(
            crea_modello(config, strumenti),
            crea_registro(strumenti),
            config.max_tool_steps,
            router=crea_router(config),
            ambito=config.ambito_assistente,
            messaggio_rifiuto=config.messaggio_rifiuto,
            revisore=crea_revisore(config),
            max_revisioni=config.max_revisioni,
        )
        with caplog.at_level("INFO", logger="revisore"):
            stato = grafo.invoke({
                "messages": [SystemMessage(PROMPT_SISTEMA), HumanMessage("Quanti km sono 5 miglia?")],
                "passi_strumento": 0,
            })
    finally:
        for remoto in remoti:
            if remoto:
                remoto.chiudi()
    righe = _righe_revisore(caplog)
    print("\nRevisore:", righe, "\nRisposta:", stato["messages"][-1].content)
    assert len(righe) == 1, righe
    assert _approvata(righe[0]), righe
