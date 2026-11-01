"""Configurazione dei log: su stderr, così non si mescolano alla conversazione su stdout."""

import logging
import sys

FORMATO = "%(asctime)s %(levelname)s %(name)s: %(message)s"
FORMATO_ORA = "%H:%M:%S"

# Librerie esterne che a INFO o DEBUG scriverebbero righe per ogni richiesta HTTP.
LIBRERIE_ESTERNE = ("httpx", "httpx2", "httpcore", "httpcore2", "openai", "langchain", "langchain_core", "langchain_openai", "langgraph")


def configura_log(livello: str) -> None:
    """Imposta il livello dei log del progetto e silenzia le librerie esterne."""
    gestore = logging.StreamHandler(sys.stderr)
    gestore.setFormatter(logging.Formatter(FORMATO, datefmt=FORMATO_ORA))
    logging.basicConfig(level=livello, handlers=[gestore], force=True)
    for nome in LIBRERIE_ESTERNE:
        logging.getLogger(nome).setLevel(logging.WARNING)
