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
    """Pone la domanda all'assistente completo (orologio + convertitore + calcolatrice).

    Restituisce i risultati degli strumenti raggruppati per nome e la risposta finale.
    """
    from assistente.terminale import collega_calcolatrice, collega_convertitore

    config = carica_config()
    remoti = [collega_convertitore(), collega_calcolatrice()]
    try:
        assert all(remoti), "un server MCP non si è avviato"
        strumenti = [crea_orologio(), *(s for r in remoti for s in r.strumenti())]
        grafo = costruisci_grafo(crea_modello(config, strumenti), crea_registro(strumenti), config.max_tool_steps)
        stato = grafo.invoke({
            "messages": [SystemMessage(PROMPT_SISTEMA), HumanMessage(domanda)],
            "passi_strumento": 0,
        })
    finally:
        for remoto in remoti:
            if remoto:
                remoto.chiudi()
    risultati: dict[str, list[str]] = {}
    for m in stato["messages"]:
        if isinstance(m, ToolMessage):
            risultati.setdefault(m.name, []).append(m.content)
    finale = pulisci_ragionamento(stato["messages"][-1].text)
    print("\nStrumenti:", risultati, "\nRisposta:", finale)
    return risultati, finale


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
