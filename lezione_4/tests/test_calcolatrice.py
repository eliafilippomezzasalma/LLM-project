"""Test della calcolatrice sicura: analizzatore, calcolo e messaggi (senza server MCP)."""

import time
from fractions import Fraction
from pathlib import Path

import pytest

import calcolatrice
from calcolatrice import calcola, esegui_calcolo

ARGOMENTO = "serve un'espressione scritta come testo, per esempio '(3,5 + 2) * 4'"


@pytest.mark.parametrize(
    "espressione, atteso",
    [
        ("2 + 3 * 4", 14),
        ("(2 + 3) * 4", 20),
        ("10 - 4 - 3", 3),
        ("8 / 4 / 2", 1),
        ("2 + 3^2", 11),
        ("2^3^2", 512),
        ("-2^2", -4),
        ("(-2)^2", 4),
        ("2^-1", Fraction(1, 2)),
        ("--2", 2),
        ("-(2 + 1)", -3),
        ("+5", 5),
    ],
)
def test_operazioni_e_precedenza(espressione, atteso):
    assert calcola(espressione) == atteso


@pytest.mark.parametrize(
    "espressione, atteso",
    [("3,5 + 2", Fraction(11, 2)), ("3.5 + 2", Fraction(11, 2)), ("1.000", 1)],
)
def test_virgola_e_punto(espressione, atteso):
    assert calcola(espressione) == atteso


@pytest.mark.parametrize("espressione, atteso", [("2**3", 8), ("6 × 7", 42), ("9 ÷ 3", 3)])
def test_sinonimi(espressione, atteso):
    assert calcola(espressione) == atteso


def test_aritmetica_esatta():
    assert esegui_calcolo({"expression": "0,1 + 0,2"}) == ("0,1 + 0,2 = 0.3", False)
    assert esegui_calcolo({"expression": "1 / 3"}) == ("1 / 3 = 0.3333333333", False)


@pytest.mark.parametrize(
    "espressione, atteso",
    [
        ("(3,5 + 2) * 4", "(3,5 + 2) * 4 = 22"),
        ("2^0,5", "2^0,5 = 1.414213562"),
        ("2^100", "2^100 = 1.2676506e+30"),
        ("-0", "-0 = 0"),
        ("2^0,5 * 2^0,5", "2^0,5 * 2^0,5 = 2"),
        ("  2+2 ", "2+2 = 4"),
    ],
)
def test_formato(espressione, atteso):
    assert esegui_calcolo({"expression": espressione}) == (atteso, False)


@pytest.mark.parametrize(
    "espressione, testo",
    [
        ("10 / 0", "divisione per zero"),
        ("5 / (2 - 2)", "divisione per zero"),
        ("0^-1", "divisione per zero"),
        ("0^0", "0^0 è una forma indeterminata"),
        ("(-8)^0,5", "potenza con base negativa ed esponente non intero non supportata"),
        ("(-8)^(1/3)", "potenza con base negativa ed esponente non intero non supportata"),
        ("9^9^9", "risultato troppo grande (oltre 10^100)"),
        ("10^1000", "risultato troppo grande (oltre 10^100)"),
        ("10^-1000", "risultato troppo piccolo (sotto 10^-100)"),
        ("0,5^1000", "risultato troppo piccolo (sotto 10^-100)"),
        ("10^-(9^9)", "risultato troppo piccolo (sotto 10^-100)"),
        ("10^60 * 10^60 / 10^30", "risultato troppo grande (oltre 10^100)"),
        ("10^-60 * 10^-60 * 10^100", "risultato troppo piccolo (sotto 10^-100)"),
    ],
)
def test_rifiuti_matematici(espressione, testo):
    assert esegui_calcolo({"expression": espressione}) == (f"Errore: {testo}", True)


@pytest.mark.parametrize("espressione", ["9^9^9", "10^-(9^9)"])
def test_potenze_enormi_rifiutate_subito(espressione):
    inizio = time.perf_counter()
    _, errore = esegui_calcolo({"expression": espressione})
    assert errore
    assert time.perf_counter() - inizio < 1


CARATTERE = "carattere non consentito '{}' in posizione {}: sono ammessi numeri, + - * / ^ e parentesi"


@pytest.mark.parametrize(
    "espressione, testo",
    [
        ("", "espressione vuota"),
        ("   ", "espressione vuota"),
        ("2 + x", CARATTERE.format("x", 5)),
        ("3,5,2", "numero scritto male '3,5,2' in posizione 1"),
        ("1.000,5", "numero scritto male '1.000,5' in posizione 1"),
        ("3,", "numero scritto male '3,' in posizione 1"),
        (",5 + 1", "numero scritto male ',5' in posizione 1"),
        ("3 + * 2", "manca un numero in posizione 5"),
        ("4 /", "manca un numero in posizione 4"),
        ("()", "manca un numero in posizione 2"),
        ("2 3", "manca un operatore prima di '3' in posizione 3"),
        ("2(3)", "manca un operatore prima di '(' in posizione 2"),
        ("(1)(2)", "manca un operatore prima di '(' in posizione 4"),
        ("(1 + 2", "parentesi aperta in posizione 1 non chiusa"),
        ("1 + 2)", "parentesi chiusa in posizione 6 senza apertura"),
    ],
)
def test_rifiuti_di_forma(espressione, testo):
    assert esegui_calcolo({"expression": espressione}) == (f"Errore: {testo}", True)


@pytest.mark.parametrize(
    "espressione, carattere, posizione",
    [
        ("5 − 2", "−", 3),
        ("3 x 4", "x", 3),
        ("8 : 2", ":", 3),
        ("10 % 3", "%", 4),
        ("sqrt(4)", "s", 1),
        ("2 = 2", "=", 3),
    ],
)
def test_simboli_quasi_giusti(espressione, carattere, posizione):
    assert esegui_calcolo({"expression": espressione}) == (
        "Errore: " + CARATTERE.format(carattere, posizione),
        True,
    )


def test_limiti_di_lunghezza_e_profondita():
    assert calcola("1+" * 99 + "1") == 100
    with pytest.raises(calcolatrice.ErroreCalcolo, match="espressione troppo lunga"):
        calcola("1+" * 100 + "1")
    assert calcola("(" * 30 + "1" + ")" * 30) == 1
    with pytest.raises(calcolatrice.ErroreCalcolo, match="troppe parentesi annidate"):
        calcola("(" * 31 + "1" + ")" * 31)
    assert calcola("-" * 150 + "2") == 2


def test_messaggi_dei_limiti():
    assert esegui_calcolo({"expression": "1+" * 100 + "1"}) == (
        "Errore: espressione troppo lunga (massimo 200 caratteri)",
        True,
    )
    assert esegui_calcolo({"expression": "(" * 31 + "1" + ")" * 31}) == (
        "Errore: troppe parentesi annidate (massimo 30 livelli)",
        True,
    )


@pytest.mark.parametrize("argomenti", [{}, {"expression": None}, {"expression": 5},
                                        {"expression": True}, {"expression": ["1"]}])
def test_argomento_non_testuale(argomenti):
    assert esegui_calcolo(argomenti) == (f"Errore: {ARGOMENTO}", True)


def test_nessun_eval_nel_sorgente():
    sorgente = (Path(calcolatrice.__file__)).read_text(encoding="utf-8")
    for vietato in ("eval(", "exec(", "compile(", "literal_eval", "import ast"):
        assert vietato not in sorgente


@pytest.mark.parametrize("esponente", ["1000000", "100000000"])
def test_base_vicina_a_uno_non_blocca(esponente):
    espressione = f"1,0000000000000000000000001^{esponente}"
    inizio = time.perf_counter()
    testo, errore = esegui_calcolo({"expression": espressione})
    assert time.perf_counter() - inizio < 1
    assert not errore
    assert testo.startswith(espressione)


def _con_tempo(espressione):
    inizio = time.perf_counter()
    risultato = esegui_calcolo({"expression": espressione})
    assert time.perf_counter() - inizio < 1
    return risultato


def test_base_vicinissima_a_uno_con_esponente_enorme():
    assert _con_tempo("1,0000000000000000000000001^10000000000000000000000000") == (
        "1,0000000000000000000000001^10000000000000000000000000 = 2.718281828", False)
    assert _con_tempo("1,0000000000000000000000001^(10^30)") == (
        "Errore: risultato troppo grande (oltre 10^100)", True)


def test_base_meno_uno_segue_la_parita_esatta():
    assert _con_tempo("(-1)^(2^60+1)")[0].endswith("= -1")
    assert _con_tempo("(-1)^(9*10^99+1)")[0].endswith("= -1")
    assert _con_tempo("(-1)^(2^60)")[0].endswith("= 1")


def test_potenze_intere_esatte_restano_esatte():
    assert esegui_calcolo({"expression": "2^300"}) == ("2^300 = 2.037035976e+90", False)
    assert esegui_calcolo({"expression": "(1/3)^50"})[1] is False
