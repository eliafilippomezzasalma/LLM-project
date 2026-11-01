import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from assistente.grafo import costruisci_grafo
from assistente.orologio import crea_orologio
from assistente.sessione import PROMPT_SISTEMA, LimitePassaggiRaggiunto, Sessione
from assistente.strumenti import crea_registro
from finti import ModelloCheFallisce, ModelloFinto, chiede_ora

REGISTRO = crea_registro([crea_orologio()])


def _contenuto(cronologia):
    return [(type(m), m.content) for m in cronologia]


SOLO_PROMPT = [(SystemMessage, PROMPT_SISTEMA)]


def _sessione(modello):
    return Sessione(costruisci_grafo(modello, REGISTRO, max_passi=3))


def test_cronologia_iniziale_solo_prompt_di_sistema():
    sessione = _sessione(ModelloFinto([AIMessage("x")]))
    assert _contenuto(sessione.cronologia) == SOLO_PROMPT


def test_prompt_sistema_impone_lo_strumento():
    assert "get_current_time" in PROMPT_SISTEMA


def test_prompt_sistema_vieta_di_calcolare_tra_fusi():
    # Prova reale: a «e a Roma?» dopo Tokyo, Qwen ricavava spesso l'ora sottraendo il fuso
    # dalla risposta precedente invece di chiamare lo strumento, a volte sbagliando.
    assert "non calcolare l'ora partendo da un altro fuso" in PROMPT_SISTEMA


def test_cronologia_solo_domanda_e_risposta():
    sessione = _sessione(ModelloFinto([chiede_ora("Asia/Tokyo"), AIMessage("A Tokyo sono le 20:30.")]))
    assert sessione.chiedi("Che ore sono a Tokyo?") == "A Tokyo sono le 20:30."
    assert [type(m) for m in sessione.cronologia] == [SystemMessage, HumanMessage, AIMessage]
    assert not any(isinstance(m, ToolMessage) for m in sessione.cronologia)
    assert not sessione.cronologia[-1].tool_calls


def test_secondo_turno_riceve_il_primo():
    modello = ModelloFinto([AIMessage("Ciao Elia!"), AIMessage("Ti chiami Elia.")])
    sessione = _sessione(modello)
    sessione.chiedi("Mi chiamo Elia")
    assert sessione.chiedi("Come mi chiamo?") == "Ti chiami Elia."
    assert [m.content for m in modello.chiamate[1]] == [
        PROMPT_SISTEMA, "Mi chiamo Elia", "Ciao Elia!", "Come mi chiamo?",
    ]


def test_limite_non_sporca_cronologia():
    sessione = _sessione(ModelloFinto([chiede_ora("Asia/Tokyo")]))  # chiede sempre lo strumento
    with pytest.raises(LimitePassaggiRaggiunto):
        sessione.chiedi("Che ore sono a Tokyo?")
    assert _contenuto(sessione.cronologia) == SOLO_PROMPT


def test_errore_modello_non_sporca_cronologia():
    sessione = _sessione(ModelloCheFallisce(ConnectionError("LM Studio spento")))
    with pytest.raises(ConnectionError):
        sessione.chiedi("Ciao")
    assert _contenuto(sessione.cronologia) == SOLO_PROMPT


def test_risposta_vuota_segnaposto():
    sessione = _sessione(ModelloFinto([AIMessage("")]))
    assert sessione.chiedi("Ciao") == "(nessuna risposta dal modello)"
    assert sessione.cronologia[-1].content == "(nessuna risposta dal modello)"


def test_think_rimosso_da_cronologia():
    sessione = _sessione(ModelloFinto([AIMessage("<think>ragiono</think>Ciao!")]))
    assert sessione.chiedi("Ciao") == "Ciao!"
    assert sessione.cronologia[-1].content == "Ciao!"
