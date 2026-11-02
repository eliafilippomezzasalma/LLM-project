from datetime import datetime, timezone

import pytest

from assistente.orologio import FusoNonValido, crea_orologio, formatta_ora

ISTANTE = datetime(2026, 10, 26, 11, 30, 41, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("istante", "fuso", "atteso"),
    [
        (ISTANTE, "Asia/Tokyo", "lunedì 26 ottobre 2026, 20:30:41 — Asia/Tokyo (UTC+09:00)"),
        (ISTANTE, "Europe/Rome", "lunedì 26 ottobre 2026, 12:30:41 — Europe/Rome (UTC+01:00)"),
        (
            ISTANTE,
            "America/Los_Angeles",
            "lunedì 26 ottobre 2026, 04:30:41 — America/Los_Angeles (UTC-07:00)",
        ),
        (
            datetime(2026, 10, 26, 2, 0, 0, tzinfo=timezone.utc),
            "America/Los_Angeles",
            "domenica 25 ottobre 2026, 19:00:00 — America/Los_Angeles (UTC-07:00)",
        ),
        (
            datetime(2026, 7, 15, 10, 0, 0, tzinfo=timezone.utc),
            "Europe/Rome",
            "mercoledì 15 luglio 2026, 12:00:00 — Europe/Rome (UTC+02:00)",
        ),
        (
            datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
            "Asia/Kolkata",
            "domenica 1 marzo 2026, 05:30:00 — Asia/Kolkata (UTC+05:30)",
        ),
    ],
)
def test_formatta_ora(istante, fuso, atteso):
    assert formatta_ora(istante, fuso) == atteso


def test_formatta_ora_fuso_non_valido():
    with pytest.raises(FusoNonValido):
        formatta_ora(ISTANTE, "JST")


def _orologio():
    return crea_orologio(adesso=lambda: ISTANTE)


def test_strumento_restituisce_ora():
    risultato = _orologio().invoke({"timezone": "Asia/Tokyo"})
    assert risultato == "lunedì 26 ottobre 2026, 20:30:41 — Asia/Tokyo (UTC+09:00)"


def test_fuso_non_valido():
    risultato = _orologio().invoke({"timezone": "JST"})
    assert risultato == "Errore: fuso orario 'JST' non valido, usa un nome IANA come 'Asia/Tokyo'"


def test_fuso_minuscolo_non_valido():
    risultato = _orologio().invoke({"timezone": "asia/tokyo"})
    assert risultato == (
        "Errore: fuso orario 'asia/tokyo' non valido, usa un nome IANA come 'Asia/Tokyo'"
    )


def test_spazi_rimossi():
    risultato = _orologio().invoke({"timezone": " Asia/Tokyo "})
    assert risultato.endswith("— Asia/Tokyo (UTC+09:00)")


def test_schema_strumento():
    orologio = _orologio()
    assert orologio.name == "get_current_time"
    assert "timezone" in orologio.args
    assert "Europe/Rome" in orologio.description
