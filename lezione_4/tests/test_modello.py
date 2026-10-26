from assistente.config import Config
from assistente.modello import crea_modello, pulisci_ragionamento
from assistente.orologio import crea_orologio

CONFIG = Config(
    lm_base_url="http://localhost:1234/v1",
    lm_model="qwen/qwen3.5-9b",
    max_tool_steps=3,
    log_level="INFO",
)


def test_pulisce_think():
    testo = "<think>\nDevo usare lo strumento.\nOk.\n</think>\n\nA Tokyo sono le 20:30."
    assert pulisci_ragionamento(testo) == "A Tokyo sono le 20:30."


def test_pulisce_piu_blocchi_think():
    assert pulisci_ragionamento("<think>a</think>Ciao <think>b</think>Elia") == "Ciao Elia"


def test_testo_senza_think_invariato():
    assert pulisci_ragionamento("Ciao Elia!") == "Ciao Elia!"


def test_solo_think_diventa_vuoto():
    assert pulisci_ragionamento("<think>solo ragionamento</think>") == ""


def test_crea_modello_usa_config():
    modello = crea_modello(CONFIG, [crea_orologio()])
    chat = modello.bound
    assert chat.openai_api_base == "http://localhost:1234/v1"
    assert chat.model_name == "qwen/qwen3.5-9b"
    assert chat.request_timeout == 300


def test_crea_modello_collega_gli_strumenti():
    modello = crea_modello(CONFIG, [crea_orologio()])
    nomi = [t["function"]["name"] for t in modello.kwargs["tools"]]
    assert nomi == ["get_current_time"]
