"""Prova con il modello vero in LM Studio: attivarla con RUN_REAL_TESTS=1."""

import os
import re

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from assistente.config import carica_config
from assistente.grafo import costruisci_grafo, limite_raggiunto
from assistente.modello import crea_modello, pulisci_ragionamento
from assistente.orologio import crea_orologio
from assistente.sessione import PROMPT_SISTEMA
from assistente.strumenti import crea_registro

pytestmark = [
    pytest.mark.reale,
    pytest.mark.skipif(os.environ.get("RUN_REAL_TESTS") != "1", reason="serve RUN_REAL_TESTS=1 e LM Studio attivo"),
]


def test_tokyo_usa_lo_strumento():
    config = carica_config()
    strumenti = [crea_orologio()]
    grafo = costruisci_grafo(crea_modello(config, strumenti), crea_registro(strumenti), config.max_tool_steps)

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
        grafo = costruisci_grafo(crea_modello(config, strumenti), crea_registro(strumenti), config.max_tool_steps)
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
