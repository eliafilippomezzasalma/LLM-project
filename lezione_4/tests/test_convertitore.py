"""Logica e schema del convertitore di unità (senza MCP)."""

import pytest

from convertitore import GRANDEZZE, UNITA, RichiestaConversione, esegui_conversione

ELENCO = (
    "mm, cm, m, km, in, ft, mi, g, kg, lb, oz, s, min, h, °C, °F, K, ml, l, gal, m/s, km/h, mph"
)


def test_unita_sono_23_in_6_grandezze():
    assert len(UNITA) == 23
    assert set(GRANDEZZE) == set(UNITA)
    assert set(GRANDEZZE.values()) == {
        "lunghezza", "massa", "tempo", "temperatura", "volume", "velocità",
    }


def test_schema_elenca_unita_chiuse():
    schema = RichiestaConversione.model_json_schema()
    assert schema["properties"]["from_unit"]["enum"] == list(UNITA)
    assert schema["properties"]["to_unit"]["enum"] == list(UNITA)
    assert schema["required"] == ["value", "from_unit", "to_unit"]


@pytest.mark.parametrize(
    ("valore", "da", "a", "atteso"),
    [
        (10, "km", "mi", 6.213711922373339),
        (1, "mi", "m", 1609.344),
        (1, "lb", "g", 453.59237),
        (16, "oz", "lb", 1),
        (90, "min", "h", 1.5),
        (100, "°C", "°F", 212),
        (32, "°F", "°C", 0),
        (0, "K", "°C", -273.15),
        (1, "gal", "l", 3.785411784),
        (1000, "ml", "l", 1),
        (36, "km/h", "m/s", 10),
        (60, "mph", "km/h", 96.56064),
        (5, "km", "km", 5),
        (-10, "m", "ft", -32.808398950131235),
    ],
)
def test_conversioni(valore, da, a, atteso):
    from convertitore import converti

    richiesta = RichiestaConversione(value=valore, from_unit=da, to_unit=a)
    assert converti(richiesta) == pytest.approx(atteso, rel=1e-9, abs=1e-9)


def test_formatta_risultato():
    assert esegui_conversione({"value": 10, "from_unit": "km", "to_unit": "mi"}) == (
        "10 km = 6.21371 mi",
        False,
    )


@pytest.mark.parametrize(
    ("scritto", "simbolo"),
    [
        ("KM", "km"), ("miglia", "mi"), ("celsius", "°C"), ("C", "°C"), ("kph", "km/h"),
        ("L", "l"), ("MPH", "mph"), ("M", "m"), ("MIN", "min"), ("MI", "mi"), ("K", "K"),
        (" kg ", "kg"), ("gradi Fahrenheit", "°F"), ("Litri", "l"),
    ],
)
def test_sinonimi(scritto, simbolo):
    richiesta = RichiestaConversione(value=1, from_unit=scritto, to_unit=simbolo)
    assert richiesta.from_unit == simbolo


def test_unita_sconosciuta():
    testo, errore = esegui_conversione({"value": 1, "from_unit": "anni luce", "to_unit": "km"})
    assert errore
    assert testo == f"Errore: unità 'anni luce' non ammessa. Unità ammesse: {ELENCO}"


def test_grandezze_incompatibili():
    assert esegui_conversione({"value": 5, "from_unit": "kg", "to_unit": "m"}) == (
        "Errore: impossibile convertire 'kg' (massa) in 'm' (lunghezza): grandezze diverse",
        True,
    )


def test_sotto_zero_assoluto():
    assert esegui_conversione({"value": -300, "from_unit": "°C", "to_unit": "K"}) == (
        "Errore: -300 °C è sotto lo zero assoluto (-273.15 °C)",
        True,
    )
    assert esegui_conversione({"value": -1, "from_unit": "K", "to_unit": "°C"})[1]
    assert esegui_conversione({"value": -460, "from_unit": "°F", "to_unit": "K"})[1]
    assert not esegui_conversione({"value": -273.15, "from_unit": "°C", "to_unit": "K"})[1]


@pytest.mark.parametrize("valore", ["dieci", float("nan"), float("inf"), True, None])
def test_valore_non_valido(valore):
    assert esegui_conversione({"value": valore, "from_unit": "km", "to_unit": "m"}) == (
        "Errore: il valore deve essere un numero finito",
        True,
    )


def test_valore_come_stringa_numerica_accettato():
    assert esegui_conversione({"value": "10", "from_unit": "km", "to_unit": "m"}) == (
        "10 km = 10000 m",
        False,
    )


def test_argomento_mancante():
    assert esegui_conversione({"value": 5, "from_unit": "km"}) == (
        "Errore: argomento 'to_unit' mancante",
        True,
    )


def test_piu_errori():
    testo, errore = esegui_conversione({"value": "x", "from_unit": "ly"})
    assert errore
    assert testo.count("Errore:") == 1
    assert testo.startswith("Errore: ")
    assert len(testo.removeprefix("Errore: ").split("; ")) == 3
