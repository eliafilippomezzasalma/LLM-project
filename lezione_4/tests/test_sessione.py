import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool

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


def test_prompt_sistema_impone_il_convertitore():
    assert "convert_units" in PROMPT_SISTEMA
    assert "non fare i calcoli a mente" in PROMPT_SISTEMA
    assert "senza inventare un risultato" in PROMPT_SISTEMA
    assert "anche quando pensi che la " in PROMPT_SISTEMA


def test_prompt_sistema_ha_esempi_di_errore():
    # Prova reale: con «anni luce» o «-300 °C» il modello rifiutava da solo senza chiamare
    # lo strumento; gli esempi espliciti gli dicono di chiamarlo comunque.
    assert "anni luce" in PROMPT_SISTEMA
    assert "-300 °C" in PROMPT_SISTEMA


def _converti(value, from_unit, to_unit):
    return f"{value:g} {from_unit} = ? {to_unit}"


CONVERTITORE_FINTO = StructuredTool.from_function(_converti, name="convert_units", description="finto")
REGISTRO_CON_CONVERTITORE = crea_registro([crea_orologio(), CONVERTITORE_FINTO])


def _chiede(*chiamate) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": n, "args": a, "id": i, "type": "tool_call"} for n, a, i in chiamate],
    )


KM_MI = ("convert_units", {"value": 10, "from_unit": "km", "to_unit": "mi"}, "k1")


def test_cronologia_conserva_le_chiamate_al_convertitore():
    # Prova reale: senza esempi nella cronologia, dopo una dozzina di domande il modello
    # smetteva di chiamare il convertitore e rispondeva a mente.
    modello = ModelloFinto([_chiede(KM_MI), AIMessage("Sono 6,21 miglia.")])
    sessione = Sessione(costruisci_grafo(modello, REGISTRO_CON_CONVERTITORE, max_passi=3))
    assert sessione.chiedi("Converti 10 km in miglia") == "Sono 6,21 miglia."
    tipi = [type(m) for m in sessione.cronologia]
    assert tipi == [SystemMessage, HumanMessage, AIMessage, ToolMessage, AIMessage]
    assert [c["name"] for c in sessione.cronologia[2].tool_calls] == ["convert_units"]
    assert sessione.cronologia[3].content == "10 km = ? mi"
    assert sessione.cronologia[3].tool_call_id == "k1"


def test_cronologia_toglie_l_orologio_da_una_chiamata_mista():
    ora = ("get_current_time", {"timezone": "Asia/Tokyo"}, "o1")
    modello = ModelloFinto([_chiede(ora, KM_MI), AIMessage("Fatto.")])
    sessione = Sessione(costruisci_grafo(modello, REGISTRO_CON_CONVERTITORE, max_passi=3))
    sessione.chiedi("Che ore sono a Tokyo e quanto fanno 10 km in miglia?")
    chiamate = [c["name"] for m in sessione.cronologia if isinstance(m, AIMessage) for c in m.tool_calls]
    risposte = [m.name for m in sessione.cronologia if isinstance(m, ToolMessage)]
    assert chiamate == ["convert_units"]
    assert risposte == ["convert_units"]


def test_secondo_turno_vede_la_chiamata_al_convertitore():
    modello = ModelloFinto([_chiede(KM_MI), AIMessage("Sono 6,21 miglia."), AIMessage("Prego.")])
    sessione = Sessione(costruisci_grafo(modello, REGISTRO_CON_CONVERTITORE, max_passi=3))
    sessione.chiedi("Converti 10 km in miglia")
    sessione.chiedi("Grazie")
    assert any(isinstance(m, ToolMessage) and m.name == "convert_units" for m in modello.chiamate[-1])


def test_prompt_sistema_impone_la_calcolatrice():
    assert "calculate" in PROMPT_SISTEMA
    assert "a mente" in PROMPT_SISTEMA
    assert "'10 / 0'" in PROMPT_SISTEMA
    assert "convert_units, non calculate" in PROMPT_SISTEMA
    assert "parsec" in PROMPT_SISTEMA  # unità fuori elenco: niente conversioni fatte con calculate


def test_cronologia_conserva_le_chiamate_alla_calcolatrice():
    calcolatrice = StructuredTool.from_function(
        lambda expression: f"{expression} = 22", name="calculate", description="finto"
    )
    registro = crea_registro([crea_orologio(), calcolatrice])
    chiamata = ("calculate", {"expression": "(3.5 + 2) * 4"}, "c1")
    modello = ModelloFinto([_chiede(chiamata), AIMessage("Fa 22.")])
    sessione = Sessione(costruisci_grafo(modello, registro, max_passi=3))
    assert sessione.chiedi("Quanto fa (3,5 + 2) * 4?") == "Fa 22."
    tipi = [type(m) for m in sessione.cronologia]
    assert tipi == [SystemMessage, HumanMessage, AIMessage, ToolMessage, AIMessage]
    assert [c["name"] for c in sessione.cronologia[2].tool_calls] == ["calculate"]
    assert sessione.cronologia[3].tool_call_id == "c1"
