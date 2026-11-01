"""Prova con il modello vero in LM Studio: attivarla con RUN_REAL_TESTS=1."""

import os

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
