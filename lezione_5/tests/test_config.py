import pytest

from assistente.config import Config, ErroreConfigurazione, carica_config

BASE = {"LM_BASE_URL": "http://localhost:1234/v1", "LM_MODEL": "qwen/qwen3.5-9b"}


def test_valori_completi():
    env = {**BASE, "MAX_TOOL_STEPS": "5", "LOG_LEVEL": "DEBUG"}
    assert carica_config(env) == Config(
        lm_base_url="http://localhost:1234/v1",
        lm_model="qwen/qwen3.5-9b",
        max_tool_steps=5,
        log_level="DEBUG",
    )


def test_predefiniti():
    config = carica_config(BASE)
    assert config.max_tool_steps == 3
    assert config.log_level == "INFO"


def test_manca_lm_base_url():
    with pytest.raises(ErroreConfigurazione, match="LM_BASE_URL"):
        carica_config({"LM_MODEL": "qwen/qwen3.5-9b"})


def test_manca_lm_model():
    with pytest.raises(ErroreConfigurazione, match="LM_MODEL"):
        carica_config({"LM_BASE_URL": "http://localhost:1234/v1"})


def test_variabile_vuota_conta_come_mancante():
    with pytest.raises(ErroreConfigurazione, match="LM_MODEL"):
        carica_config({**BASE, "LM_MODEL": "  "})


def test_max_tool_steps_non_intero():
    with pytest.raises(ErroreConfigurazione, match="MAX_TOOL_STEPS"):
        carica_config({**BASE, "MAX_TOOL_STEPS": "tre"})


def test_max_tool_steps_zero():
    with pytest.raises(ErroreConfigurazione, match="MAX_TOOL_STEPS"):
        carica_config({**BASE, "MAX_TOOL_STEPS": "0"})


def test_log_level_non_valido():
    with pytest.raises(ErroreConfigurazione, match="LOG_LEVEL.*'verbose'"):
        carica_config({**BASE, "LOG_LEVEL": "verbose"})


def test_env_letto_dalla_cartella_del_progetto(monkeypatch):
    # Senza percorso load_dotenv risalirebbe le cartelle e troverebbe il .env di un'altra lezione.
    from pathlib import Path

    from assistente import config

    percorsi = []
    monkeypatch.setattr(config, "load_dotenv", lambda percorso=None: percorsi.append(percorso))
    monkeypatch.setenv("LM_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("LM_MODEL", "qwen/qwen3.5-9b")
    carica_config()
    assert percorsi == [Path(config.__file__).resolve().parent.parent / ".env"]
