"""Test di richieste, risultati e rifiuti di `scadenze.py` (senza lo strato MCP)."""

import time

import pytest

from scadenze import (
    MESSAGGIO_INTERVALLO,
    NOMI_STRUMENTI,
    RIGA_NOTA,
    Calendario,
    carica_festivita,
    esegui_strumento,
)

NOTA = "\nNota: calcolo indicativo, non ha valore legale."


@pytest.fixture(scope="module")
def cal():
    return Calendario(carica_festivita())


@pytest.fixture
def esegui(cal):
    def _esegui(nome, **argomenti):
        return esegui_strumento(cal, nome, argomenti)

    return _esegui


def test_nomi_strumenti():
    assert len(NOMI_STRUMENTI) == 6
    assert RIGA_NOTA == "Nota: calcolo indicativo, non ha valore legale."


@pytest.mark.parametrize(
    "args, atteso",
    [
        (("2024-03-15", 4, "years"), "Scadenza: 2028-03-15 (mercoledì), 4 anni dopo il 2024-03-15."),
        (("2026-10-10", 30, "days"), "Scadenza: 2026-11-09 (lunedì), 30 giorni dopo il 2026-10-10."),
        (
            ("2026-12-31", 6, "months", "backward"),
            "Scadenza: 2026-06-30 (martedì), 6 mesi prima del 2026-12-31.",
        ),
        (
            ("2026-11-09", 10, "business_days"),
            "Scadenza: 2026-11-23 (lunedì), 10 giorni lavorativi dopo il 2026-11-09.",
        ),
    ],
)
def test_domande_gruppo_a(esegui, args, atteso):
    parziali = dict(zip(("start_date", "amount", "unit", "direction"), args))
    assert esegui("compute_deadline", **parziali) == (atteso + NOTA, False)


@pytest.mark.parametrize(
    "args, atteso",
    [
        (
            ("2026-03-25", 1, "months"),
            "Scadenza: 2026-04-27 (lunedì), 1 mese dopo il 2026-03-25. La data calcolata "
            "2026-04-25 (sabato) è festiva (Festa della Liberazione): spostata al giorno "
            "lavorativo successivo.",
        ),
        (
            ("2027-06-27", 6, "months", "backward"),
            "Scadenza: 2026-12-24 (giovedì), 6 mesi prima del 2027-06-27. La data calcolata "
            "2026-12-27 (domenica) cade di domenica: spostata al giorno lavorativo precedente.",
        ),
    ],
)
def test_scadenza_spostata(esegui, args, atteso):
    parziali = dict(zip(("start_date", "amount", "unit", "direction"), args))
    assert esegui("compute_deadline", **parziali) == (atteso + NOTA, False)


def test_nota_solo_in_compute_deadline(esegui):
    altri = [
        esegui("add_business_days", start_date="2026-11-09", days=10),
        esegui("count_business_days", start_date="2026-11-01", end_date="2026-11-30"),
        esegui("days_between", from_date="2026-11-09", to_date="2026-12-25"),
        esegui("date_info", date="2026-11-14"),
        esegui("list_holidays", year=2026),
        esegui("date_info", date="2019-01-01"),
        esegui("compute_deadline", start_date="x", amount=1, unit="days"),
        esegui("pippo"),
    ]
    assert all("Nota:" not in testo for testo, _ in altri)
    for unita in ("days", "weeks", "months", "years", "business_days"):
        testo, errore = esegui("compute_deadline", start_date="2026-11-09", amount=3, unit=unita)
        assert not errore and testo.endswith(RIGA_NOTA)


def test_gruppo_b(esegui):
    assert esegui("add_business_days", start_date="2026-11-09", days=10) == (
        "10 giorni lavorativi dopo il 2026-11-09: 2026-11-23 (lunedì).",
        False,
    )
    assert esegui("add_business_days", start_date="2026-11-06", days=1) == (
        "1 giorno lavorativo dopo il 2026-11-06: 2026-11-09 (lunedì).",
        False,
    )
    assert esegui("count_business_days", start_date="2026-11-01", end_date="2026-11-30") == (
        "Dal 2026-11-01 al 2026-11-30: 21 giorni lavorativi.",
        False,
    )


@pytest.mark.parametrize(
    "da, a, atteso",
    [
        ("2026-11-09", "2026-12-25", "Il 2026-12-25 viene 46 giorni dopo il 2026-11-09."),
        ("2026-11-09", "2026-01-01", "Il 2026-01-01 viene 312 giorni prima del 2026-11-09."),
        ("2026-11-09", "2026-11-10", "Il 2026-11-10 viene 1 giorno dopo il 2026-11-09."),
        ("2026-11-09", "2026-11-09", "Le due date coincidono: 2026-11-09 (lunedì)."),
    ],
)
def test_gruppo_c(esegui, da, a, atteso):
    assert esegui("days_between", from_date=da, to_date=a) == (atteso, False)


def test_gruppo_d(esegui):
    assert esegui("date_info", date="2027-06-02") == (
        "2027-06-02 (mercoledì): festivo, Festa della Repubblica.",
        False,
    )
    assert esegui("date_info", date="2028-03-15") == ("2028-03-15 (mercoledì): giorno lavorativo.", False)
    assert esegui("date_info", date="2026-11-14") == (
        "2026-11-14 (sabato): non lavorativo, sabato.",
        False,
    )
    assert esegui("list_holidays", year=2026, month=12) == (
        "Festività di dicembre 2026:\n- 2026-12-08 (martedì) Immacolata Concezione"
        "\n- 2026-12-25 (venerdì) Natale\n- 2026-12-26 (sabato) Santo Stefano",
        False,
    )
    assert esegui("list_holidays", year=2026, month=7) == (
        "Nessuna festività nazionale a luglio 2026.",
        False,
    )
    testo, errore = esegui("list_holidays", year=2026)
    assert not errore and testo.startswith("Festività del 2026:")
    assert sum(riga.startswith("- ") for riga in testo.splitlines()) == 12


FORMATO = "Errore: data '{}' non valida: usa il formato AAAA-MM-GG, es. 2024-03-15"


@pytest.mark.parametrize(
    "valore",
    ["15/03/2024", "2024-3-15", "15 marzo 2024", "2026-11-09T10:00:00", "20240315", 20240315],
)
def test_formati_rifiutati(esegui, valore):
    assert esegui("date_info", date=valore) == (FORMATO.format(valore), True)


def test_data_con_spazi_accettata(esegui):
    assert esegui("date_info", date=" 2026-11-09 ") == ("2026-11-09 (lunedì): giorno lavorativo.", False)


@pytest.mark.parametrize("valore", ["2026-02-30", "2025-02-29", "2026-13-01"])
def test_date_impossibili(esegui, valore):
    assert esegui("date_info", date=valore) == (f"Errore: la data '{valore}' non esiste", True)


@pytest.mark.parametrize(
    "nome, argomenti",
    [
        ("date_info", {"date": "2019-12-31"}),
        ("date_info", {"date": "2045-01-01"}),
        ("compute_deadline", {"start_date": "2040-12-31", "amount": 1, "unit": "days"}),
        (
            "compute_deadline",
            {"start_date": "2020-01-02", "amount": 1, "unit": "days", "direction": "backward"},
        ),
    ],
)
def test_fuori_intervallo(esegui, nome, argomenti):
    testo, errore = esegui(nome, **argomenti)
    assert errore and testo.startswith("Errore: ") and MESSAGGIO_INTERVALLO in testo


@pytest.mark.parametrize("unita", ["days", "years"])
def test_quantita_enormi(esegui, unita):
    testo, errore = esegui("compute_deadline", start_date="2026-11-09", amount=10**9, unit=unita)
    assert errore is True and MESSAGGIO_INTERVALLO in testo


@pytest.mark.parametrize("quantita", [0, -3, 1.5, 30.0, "30", True])
def test_quantita_non_valide(esegui, quantita):
    atteso = ("Errore: la quantità deve essere un numero intero da 1 in su", True)
    assert esegui("compute_deadline", start_date="2026-11-09", amount=quantita, unit="days") == atteso


def test_giorni_non_validi(esegui):
    assert esegui("add_business_days", start_date="2026-11-09", days=0) == (
        "Errore: la quantità deve essere un numero intero da 1 in su",
        True,
    )


def test_unita_e_direzione_non_valide(esegui):
    assert esegui("compute_deadline", start_date="2026-11-09", amount=1, unit="mesi") == (
        "Errore: unità non valida: usa days, business_days, weeks, months o years",
        True,
    )
    assert esegui(
        "compute_deadline", start_date="2026-11-09", amount=1, unit="days", direction="indietro"
    ) == ("Errore: direzione non valida: usa forward o backward", True)


def test_argomenti_mancanti(esegui):
    assert esegui("compute_deadline", amount=1, unit="days") == (
        "Errore: argomento 'start_date' mancante",
        True,
    )
    assert esegui("days_between") == (
        "Errore: argomento 'from_date' mancante; argomento 'to_date' mancante",
        True,
    )


def test_intervallo_rovesciato(esegui):
    assert esegui("count_business_days", start_date="2026-11-30", end_date="2026-11-01") == (
        "Errore: la data finale 2026-11-01 viene prima di quella iniziale 2026-11-30",
        True,
    )


def test_anno_e_mese_non_validi(esegui):
    anno = "Errore: anno non valido: posso calcolare solo date tra il 2020-01-01 e il 2040-12-31"
    mese = "Errore: mese non valido: usa un numero da 1 a 12"
    assert esegui("list_holidays", year=2041) == (anno, True)
    assert esegui("list_holidays", year=2019) == (anno, True)
    assert esegui("list_holidays", year="2026") == (anno, True)
    assert esegui("list_holidays", year=2026, month=13) == (mese, True)
    assert esegui("list_holidays", year=2026, month=0) == (mese, True)


def test_festivita_nel_weekend_contata_una_volta(esegui):
    assert esegui("count_business_days", start_date="2026-04-20", end_date="2026-04-30") == (
        "Dal 2026-04-20 al 2026-04-30: 9 giorni lavorativi.",
        False,
    )


def test_conteggi_lunghi_veloci(esegui):
    inizio = time.perf_counter()
    testo, errore = esegui("count_business_days", start_date="2020-01-01", end_date="2040-12-31")
    assert not errore
    assert time.perf_counter() - inizio < 1
    inizio = time.perf_counter()
    testo, errore = esegui("add_business_days", start_date="2020-01-02", days=6000)
    assert errore and MESSAGGIO_INTERVALLO in testo
    assert time.perf_counter() - inizio < 1


def test_strumento_sconosciuto(cal):
    assert esegui_strumento(cal, "pippo", {}) == ("Errore: strumento 'pippo' non disponibile", True)
