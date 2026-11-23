"""Errore base del RAG: il messaggio è pensato per l'utente."""

import sys


class ErroreRag(Exception):
    """Base di tutti gli errori previsti del RAG."""


def usa_utf8() -> None:
    """Porta stdout e stderr in UTF-8 (il terminale di Windows userebbe la tabella codici locale)."""
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
