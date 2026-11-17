"""Configurazione letta dalle variabili d'ambiente (e dal file .env in locale)."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Il .env della cartella del progetto: senza percorso load_dotenv risalirebbe le cartelle
# e potrebbe leggere il .env di un'altra lezione.
FILE_ENV = Path(__file__).resolve().parent.parent / ".env"
LIVELLI_LOG = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class ErroreConfigurazione(Exception):
    """Una variabile d'ambiente manca o ha un valore non valido."""


@dataclass(frozen=True)
class SogliaRiassunto:
    """Quando riassumere la cronologia e quanti turni recenti lasciare intatti."""

    tipo: Literal["messaggi", "token"] = "token"
    valore: int = 5000
    turni_da_tenere: int = 3


@dataclass(frozen=True)
class Config:
    lm_base_url: str
    lm_model: str
    max_tool_steps: int
    log_level: str
    ambito_assistente: str
    messaggio_rifiuto: str
    max_revisioni: int = 3
    riassunto: SogliaRiassunto = SogliaRiassunto()


def _obbligatoria(env: Mapping[str, str], nome: str) -> str:
    valore = env.get(nome, "").strip()
    if not valore:
        raise ErroreConfigurazione(f"Variabile d'ambiente mancante: {nome} (vedi .env.example)")
    return valore


def _max_tool_steps(env: Mapping[str, str]) -> int:
    grezzo = env.get("MAX_TOOL_STEPS", "3").strip()
    try:
        valore = int(grezzo)
    except ValueError:
        valore = 0
    if valore < 1:
        raise ErroreConfigurazione(
            f"MAX_TOOL_STEPS deve essere un intero maggiore o uguale a 1, trovato: {grezzo!r}"
        )
    return valore


def _max_revisioni(env: Mapping[str, str]) -> int:
    grezzo = env.get("MAX_REVISIONI", "3").strip()
    try:
        valore = int(grezzo)
    except ValueError:
        valore = -1
    if valore < 0:
        raise ErroreConfigurazione(
            f"MAX_REVISIONI deve essere un intero maggiore o uguale a 0, trovato: {grezzo!r}"
        )
    return valore


def _intero_positivo(env: Mapping[str, str], nome: str, predefinito: int) -> int:
    grezzo = env.get(nome, str(predefinito)).strip()
    try:
        valore = int(grezzo)
    except ValueError:
        valore = 0
    if valore < 1:
        raise ErroreConfigurazione(f"{nome} deve essere un intero maggiore o uguale a 1, trovato: {grezzo!r}")
    return valore


def _riassunto(env: Mapping[str, str]) -> SogliaRiassunto:
    grezzo = env.get("RIASSUNTO_SOGLIA_TIPO", "token").strip()
    tipo = grezzo.lower() or "token"
    if tipo not in ("messaggi", "token"):
        raise ErroreConfigurazione(
            f"RIASSUNTO_SOGLIA_TIPO deve essere uno tra messaggi, token, trovato: {grezzo!r}"
        )
    return SogliaRiassunto(
        tipo=tipo,
        valore=_intero_positivo(env, "RIASSUNTO_SOGLIA", 5000),
        turni_da_tenere=_intero_positivo(env, "RIASSUNTO_TURNI_DA_TENERE", 3),
    )


def _log_level(env: Mapping[str, str]) -> str:
    grezzo = env.get("LOG_LEVEL", "INFO").strip()
    valore = grezzo.upper() or "INFO"
    if valore not in LIVELLI_LOG:
        raise ErroreConfigurazione(f"LOG_LEVEL deve essere uno tra {', '.join(LIVELLI_LOG)}, trovato: {grezzo!r}")
    return valore


def carica_config(env: Mapping[str, str] | None = None) -> Config:
    """Legge la configurazione; senza argomenti usa .env e os.environ."""
    if env is None:
        load_dotenv(FILE_ENV)  # le variabili già presenti nell'ambiente hanno precedenza
        env = os.environ
    return Config(
        lm_base_url=_obbligatoria(env, "LM_BASE_URL"),
        lm_model=_obbligatoria(env, "LM_MODEL"),
        max_tool_steps=_max_tool_steps(env),
        log_level=_log_level(env),
        ambito_assistente=_obbligatoria(env, "AMBITO_ASSISTENTE"),
        messaggio_rifiuto=_obbligatoria(env, "MESSAGGIO_RIFIUTO"),
        max_revisioni=_max_revisioni(env),
        riassunto=_riassunto(env),
    )
