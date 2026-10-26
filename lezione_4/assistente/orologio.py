"""Strumento orologio: data e ora attuali in un fuso orario IANA, in italiano leggibile."""

from collections.abc import Callable
from datetime import UTC, datetime
from functools import cache
from zoneinfo import ZoneInfo, available_timezones

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

# Nomi italiani da tabelle fisse: non dipendono dal locale del sistema
# (l'immagine Docker slim non ha il locale italiano).
GIORNI = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
MESI = (
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)

DESCRIZIONE = (
    "Restituisce data e ora attuali nel fuso orario indicato. "
    "Usalo sempre quando serve sapere che ore sono o che giorno è. "
    "Se l'utente non indica un luogo, usa 'Europe/Rome'."
)


class FusoNonValido(ValueError):
    """Il nome non corrisponde a un fuso orario IANA."""


class ArgomentiOrologio(BaseModel):
    timezone: str = Field(description="Nome IANA del fuso orario, ad esempio 'Asia/Tokyo'")


@cache
def _fusi_validi() -> frozenset[str]:
    # Confronto esatto sull'elenco IANA: su Windows ZoneInfo ignora le maiuscole,
    # su Linux no; così il comportamento è lo stesso ovunque.
    return frozenset(available_timezones())


def _scostamento(locale: datetime) -> str:
    minuti = int(locale.utcoffset().total_seconds() // 60)
    segno = "+" if minuti >= 0 else "-"
    ore, resto = divmod(abs(minuti), 60)
    return f"UTC{segno}{ore:02d}:{resto:02d}"


def formatta_ora(istante: datetime, fuso: str) -> str:
    """Formatta un istante (con fuso) nell'ora locale del fuso IANA indicato."""
    if fuso not in _fusi_validi():
        raise FusoNonValido(fuso)
    locale = istante.astimezone(ZoneInfo(fuso))
    return (
        f"{GIORNI[locale.weekday()]} {locale.day} {MESI[locale.month - 1]} {locale.year}, "
        f"{locale:%H:%M:%S} — {fuso} ({_scostamento(locale)})"
    )


def _adesso() -> datetime:
    return datetime.now(UTC)


def crea_orologio(adesso: Callable[[], datetime] = _adesso) -> BaseTool:
    """Crea lo strumento get_current_time; `adesso` è iniettabile per i test."""

    @tool("get_current_time", description=DESCRIZIONE, args_schema=ArgomentiOrologio)
    def get_current_time(timezone: str) -> str:
        fuso = timezone.strip()
        try:
            return formatta_ora(adesso(), fuso)
        except FusoNonValido:
            return f"Errore: fuso orario '{fuso}' non valido, usa un nome IANA come 'Asia/Tokyo'"

    return get_current_time
