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


def _chiedi_con_convertitore(domanda):
    from assistente.terminale import collega_convertitore

    config = carica_config()
    remoto = collega_convertitore()
    assert remoto is not None, "il convertitore MCP non si è avviato"
    try:
        strumenti = [crea_orologio(), *remoto.strumenti()]
        grafo = costruisci_grafo(crea_modello(config, strumenti), crea_registro(strumenti), config.max_tool_steps)
        stato = grafo.invoke({
            "messages": [SystemMessage(PROMPT_SISTEMA), HumanMessage(domanda)],
            "passi_strumento": 0,
        })
    finally:
        remoto.chiudi()
    chiamate = [m.content for m in stato["messages"] if isinstance(m, ToolMessage) and m.name == "convert_units"]
    finale = pulisci_ragionamento(stato["messages"][-1].text)
    print("\nStrumento:", chiamate, "\nRisposta:", finale)
    return chiamate, finale


def test_km_in_miglia_usa_il_convertitore():
    chiamate, finale = _chiedi_con_convertitore("Converti 10 km in miglia")
    assert any(c.startswith("10 km = 6.21371 mi") for c in chiamate), chiamate
    assert "6,2" in finale or "6.2" in finale


def test_kg_in_metri_nessun_risultato_inventato():
    # Il modello di solito chiama lo strumento (11 volte su 12 nelle prove del 2026-11-03),
    # ma non sempre; in ogni caso non deve inventare un numero.
    chiamate, finale = _chiedi_con_convertitore("Converti 5 kg in metri")
    assert all(c.startswith("Errore:") for c in chiamate), chiamate
    assert finale
    assert not re.search(r"\d+(?:[.,]\d+)?\s*(?:m|metri)\b", finale), finale
    print("Strumento usato:", bool(chiamate))
