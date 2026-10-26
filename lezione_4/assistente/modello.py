"""Collegamento al modello servito da LM Studio tramite l'API compatibile OpenAI."""

import re

from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from assistente.config import Config

# LM Studio non richiede una chiave, ma il client OpenAI vuole un valore: non è una credenziale.
CHIAVE_SEGNAPOSTO = "lm-studio"
TIMEOUT_SECONDI = 300

_BLOCCO_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def crea_modello(config: Config, strumenti: list[BaseTool]) -> Runnable:
    """Crea il client verso LM Studio con gli strumenti collegati."""
    chat = ChatOpenAI(
        base_url=config.lm_base_url,
        model=config.lm_model,
        api_key=CHIAVE_SEGNAPOSTO,
        timeout=TIMEOUT_SECONDI,
    )
    return chat.bind_tools(strumenti)


def pulisci_ragionamento(testo: str) -> str:
    """Rimuove gli eventuali blocchi <think>…</think> dal testo della risposta."""
    return _BLOCCO_THINK.sub("", testo).strip()
