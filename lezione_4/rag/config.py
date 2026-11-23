"""Configurazione del RAG dalle variabili d'ambiente (separata da quella dell'assistente)."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from rag.errori import ErroreRag

# Il .env e la cartella del progetto (lezione_4): come in assistente/config.py.
CARTELLA_PROGETTO = Path(__file__).resolve().parent.parent
FILE_ENV = CARTELLA_PROGETTO / ".env"
STRATEGIE = ("paragrafi", "finestra")


class ErroreConfigurazioneRag(ErroreRag):
    """Una variabile d'ambiente del RAG manca o ha un valore non valido."""


@dataclass(frozen=True)
class ConfigRag:
    lm_base_url: str
    embedding_model: str
    qdrant_url: str
    collezione: str
    corpus: Path
    strategia: Literal["paragrafi", "finestra"]
    dimensione: int
    overlap: int
    k_max: int
    # §21: leve del retrieval (predefiniti = comportamento della §20)
    prefisso_documento: str = ""
    prefisso_domanda: str = ""
    titolo_nel_testo: bool = False
    riscrittura: bool = False
    modello_riscrittura: str = ""


def _obbligatoria(env: Mapping[str, str], nome: str) -> str:
    valore = env.get(nome, "").strip()
    if not valore:
        raise ErroreConfigurazioneRag(f"Variabile d'ambiente mancante: {nome} (vedi .env.example)")
    return valore


def _testo(env: Mapping[str, str], nome: str, predefinito: str) -> str:
    return env.get(nome, "").strip() or predefinito


def _intero(env: Mapping[str, str], nome: str, predefinito: int, minimo: int) -> int:
    grezzo = env.get(nome, "").strip() or str(predefinito)
    try:
        valore = int(grezzo)
    except ValueError:
        valore = minimo - 1
    if valore < minimo:
        raise ErroreConfigurazioneRag(
            f"{nome} deve essere un intero maggiore o uguale a {minimo}, trovato: {grezzo!r}"
        )
    return valore


def _strategia(env: Mapping[str, str]) -> Literal["paragrafi", "finestra"]:
    grezzo = env.get("CHUNK_STRATEGIA", "").strip()
    valore = grezzo.lower() or "paragrafi"
    if valore not in STRATEGIE:
        raise ErroreConfigurazioneRag(
            f"CHUNK_STRATEGIA deve essere uno tra {', '.join(STRATEGIE)}, trovato: {grezzo!r}"
        )
    return valore  # type: ignore[return-value]


_SI = ("si", "sì", "true", "1")
_NO = ("no", "false", "0")


def _booleano(env: Mapping[str, str], nome: str) -> bool:
    grezzo = env.get(nome, "").strip()
    valore = grezzo.casefold()
    if not valore or valore in _NO:
        return False
    if valore in _SI:
        return True
    raise ErroreConfigurazioneRag(f"{nome} deve essere si oppure no, trovato: {grezzo!r}")


def _corpus(env: Mapping[str, str]) -> Path:
    percorso = Path(_testo(env, "RAG_CORPUS", "dati/artusi.txt"))
    return percorso if percorso.is_absolute() else CARTELLA_PROGETTO / percorso


def carica_config_rag(env: Mapping[str, str] | None = None) -> ConfigRag:
    """Legge la configurazione del RAG; senza argomenti usa .env e os.environ."""
    if env is None:
        load_dotenv(FILE_ENV)  # le variabili già presenti nell'ambiente hanno precedenza
        env = os.environ
    dimensione = _intero(env, "CHUNK_DIMENSIONE", 1200, 1)
    overlap = _intero(env, "CHUNK_OVERLAP", 200, 0)
    if overlap >= dimensione:
        raise ErroreConfigurazioneRag(
            f"CHUNK_OVERLAP ({overlap}) deve essere minore di CHUNK_DIMENSIONE ({dimensione})"
        )
    riscrittura = _booleano(env, "RICERCA_RISCRITTURA")
    modello_riscrittura = env.get("RISCRITTURA_MODEL", "").strip()
    if riscrittura and not modello_riscrittura:
        raise ErroreConfigurazioneRag(
            "RICERCA_RISCRITTURA=si richiede RISCRITTURA_MODEL (identificativo da GET /v1/models)"
        )
    return ConfigRag(
        lm_base_url=_obbligatoria(env, "LM_BASE_URL"),
        embedding_model=_obbligatoria(env, "EMBEDDING_MODEL"),
        qdrant_url=_testo(env, "QDRANT_URL", "http://localhost:6333"),
        collezione=_testo(env, "QDRANT_COLLECTION", "ricette"),
        corpus=_corpus(env),
        strategia=_strategia(env),
        dimensione=dimensione,
        overlap=overlap,
        k_max=_intero(env, "RICERCA_K_MAX", 10, 1),
        prefisso_documento=env.get("EMBEDDING_PREFISSO_DOCUMENTO", "").strip(),
        prefisso_domanda=env.get("EMBEDDING_PREFISSO_DOMANDA", "").strip(),
        titolo_nel_testo=_booleano(env, "INDICE_CON_TITOLO"),
        riscrittura=riscrittura,
        modello_riscrittura=modello_riscrittura,
    )
