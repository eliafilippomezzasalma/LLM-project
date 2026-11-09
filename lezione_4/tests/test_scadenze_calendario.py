"""Test del calendario di `scadenze.py`: funzioni pure su date e giorni lavorativi."""

from datetime import date

import pytest

from scadenze import (
    MESSAGGIO_INTERVALLO,
    Calendario,
    ErroreDate,
    aggiungi_mesi,
    carica_festivita,
)


@pytest.fixture(scope="module")
def cal():
    return Calendario(carica_festivita())


def d(testo):
    return date.fromisoformat(testo)


@pytest.mark.parametrize(
    "partenza, mesi, atteso",
    [
        ("2025-01-31", 1, "2025-02-28"),
        ("2024-01-31", 1, "2024-02-29"),
        ("2024-02-29", 12, "2025-02-28"),
        ("2024-02-29", 48, "2028-02-29"),
        ("2026-03-31", -1, "2026-02-28"),
        ("2026-12-31", -6, "2026-06-30"),
    ],
)
def test_fine_mese_e_bisestili(partenza, mesi, atteso):
    assert aggiungi_mesi(d(partenza), mesi) == d(atteso)


def test_lavorativo_e_motivo(cal):
    assert cal.lavorativo(d("2026-11-09")) is True
    assert cal.motivo(d("2026-11-09")) is None
    assert cal.motivo(d("2026-11-14")) == "cade di sabato"
    assert cal.motivo(d("2026-11-15")) == "cade di domenica"
    assert cal.motivo(d("2026-04-25")) == "è festiva (Festa della Liberazione)"
    assert cal.motivo(d("2026-04-06")) == "è festiva (Lunedì dell'Angelo)"


def test_sposta(cal):
    assert cal.sposta(d("2028-03-12"), True) == d("2028-03-13")
    assert cal.sposta(d("2026-12-25"), True) == d("2026-12-28")
    assert cal.sposta(d("2026-12-27"), False) == d("2026-12-24")
    assert cal.sposta(d("2026-11-09"), True) == d("2026-11-09")


@pytest.mark.parametrize(
    "partenza, quantita, unita, avanti, atteso",
    [
        ("2024-03-15", 4, "years", True, "2028-03-15"),
        ("2026-10-10", 30, "days", True, "2026-11-09"),
        ("2026-12-31", 6, "months", False, "2026-06-30"),
        ("2026-11-09", 2, "weeks", True, "2026-11-23"),
        ("2026-11-09", 10, "business_days", True, "2026-11-23"),
    ],
)
def test_aggiungi(cal, partenza, quantita, unita, avanti, atteso):
    assert cal.aggiungi(d(partenza), quantita, unita, avanti) == d(atteso)


def test_aggiungi_fuori_intervallo(cal):
    with pytest.raises(ErroreDate, match=MESSAGGIO_INTERVALLO):
        cal.aggiungi(d("2040-12-31"), 1, "days", True)


@pytest.mark.parametrize(
    "partenza, n, avanti, atteso",
    [
        ("2026-11-06", 1, True, "2026-11-09"),
        ("2026-11-09", 10, True, "2026-11-23"),
        ("2026-11-23", 10, False, "2026-11-09"),
        ("2026-12-23", 2, True, "2026-12-28"),
    ],
)
def test_aggiungi_lavorativi(cal, partenza, n, avanti, atteso):
    assert cal.aggiungi_lavorativi(d(partenza), n, avanti) == d(atteso)


@pytest.mark.parametrize(
    "inizio, fine, atteso",
    [
        ("2026-11-02", "2026-11-06", 5),
        ("2026-11-01", "2026-11-30", 21),
        ("2026-11-14", "2026-11-15", 0),
        ("2026-11-09", "2026-11-09", 1),
    ],
)
def test_conta_lavorativi(cal, inizio, fine, atteso):
    assert cal.conta_lavorativi(d(inizio), d(fine)) == atteso


def test_spostamento_fuori_intervallo(cal):
    with pytest.raises(ErroreDate, match=MESSAGGIO_INTERVALLO):
        cal.sposta(d("2020-01-01"), False)


def test_festivita_di(cal):
    assert cal.festivita_di(2026, 12) == [
        (d("2026-12-08"), "Immacolata Concezione"),
        (d("2026-12-25"), "Natale"),
        (d("2026-12-26"), "Santo Stefano"),
    ]
    assert cal.festivita_di(2026, 7) == []
    assert len(cal.festivita_di(2026, None)) == 12
