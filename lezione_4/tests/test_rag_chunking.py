import re

import pytest

from rag.chunking import Chunk, dividi_ricetta, dividi_tutte
from rag.config import ErroreConfigurazioneRag
from rag.corpus import Ricetta


def _ricetta(testo, numero=1):
    return Ricetta(numero=numero, titolo=f"Titolo {numero}", capitolo="Capitolo", testo=testo)


def _parole(n, prefisso="parola"):
    return " ".join(f"{prefisso}{i}" for i in range(n))


def _paragrafo(lunghezza, tag):
    testo = ""
    i = 0
    while len(testo) < lunghezza:
        testo += f"{tag}{i} "
        i += 1
    return testo[:lunghezza].rstrip()


def test_ricetta_breve_un_chunk():
    testo = _paragrafo(300, "a")
    chunk = dividi_ricetta(_ricetta(testo), "paragrafi", 1200, 200)
    assert len(chunk) == 1
    assert chunk[0].posizione == 0
    assert chunk[0].testo == testo


def test_ricetta_lunga_piu_chunk():
    paragrafi = [_paragrafo(400, f"p{k}x") for k in range(6)]
    chunk = dividi_ricetta(_ricetta("\n\n".join(paragrafi)), "paragrafi", 1200, 200)
    assert len(chunk) >= 2
    assert [c.posizione for c in chunk] == list(range(len(chunk)))
    assert all(len(c.testo) <= 1400 for c in chunk)
    for prec, succ in zip(chunk, chunk[1:]):
        assert succ.testo[:100] in prec.testo
        # la sovrapposizione sta alla fine del precedente
        inizio = succ.testo[:100]
        assert prec.testo.rfind(inizio) >= len(prec.testo) - 200
    unione = "\n".join(c.testo for c in chunk)
    assert all(p in unione for p in paragrafi)


def test_paragrafo_gigante():
    testo = ". ".join(_parole(8) for _ in range(120))[:5000]
    # taglia a fine parola per avere un testo pulito
    testo = testo[: testo.rfind(" ")]
    chunk = dividi_ricetta(_ricetta(testo), "paragrafi", 1200, 200)
    assert len(chunk) > 1
    assert all(len(c.testo) <= 1400 for c in chunk)
    parole_originali = set(re.findall(r"\S+", testo))
    for c in chunk:
        assert set(re.findall(r"\S+", c.testo)) <= parole_originali


def test_strategia_finestra():
    testo = _parole(500)[:3000]
    testo = testo[: testo.rfind(" ")]
    testo = testo + " ultimaparola"
    chunk = dividi_ricetta(_ricetta(testo), "finestra", 1000, 200)
    assert len(chunk) == 4
    assert all(len(c.testo) <= 1000 for c in chunk)
    for prec, succ in zip(chunk, chunk[1:]):
        assert succ.testo[:100] in prec.testo
    assert chunk[-1].testo.endswith("ultimaparola")


def test_finestra_non_spezza_parole():
    testo = _parole(500)
    chunk = dividi_ricetta(_ricetta(testo), "finestra", 1000, 200)
    parole = set(testo.split())
    for c in chunk:
        assert set(c.testo.split()) <= parole


def test_nessun_testo_di_altre_ricette():
    a = _ricetta("\n\n".join(_paragrafo(500, "alfa") for _ in range(4)), 1)
    b = _ricetta("\n\n".join(_paragrafo(500, "beta") for _ in range(4)), 2)
    chunk = dividi_tutte([a, b], "paragrafi", 1200, 200)
    assert {c.ricetta for c in chunk} == {1, 2}
    for c in chunk:
        assert ("beta" not in c.testo) if c.ricetta == 1 else ("alfa" not in c.testo)


def test_id_stabili():
    r = _ricetta(_paragrafo(3000, "w"))
    primo = [c.id_punto for c in dividi_ricetta(r, "paragrafi", 1200, 200)]
    secondo = [c.id_punto for c in dividi_ricetta(r, "paragrafi", 1200, 200)]
    assert primo == secondo
    ids = {
        Chunk(1, "t", "c", 0, "x").id_punto,
        Chunk(1, "t", "c", 1, "x").id_punto,
        Chunk(2, "t", "c", 0, "x").id_punto,
    }
    assert len(ids) == 3
    assert Chunk(89, "t", "c", 0, "x").documento_id == "ricetta-089"


def test_metadati_copiati():
    r = _ricetta(_paragrafo(3000, "w"), 7)
    chunk = dividi_ricetta(r, "paragrafi", 1200, 200)
    assert len(chunk) > 1
    assert all((c.ricetta, c.titolo, c.capitolo) == (7, "Titolo 7", "Capitolo") for c in chunk)


def test_parametri_non_validi():
    r = _ricetta("testo")
    with pytest.raises(ErroreConfigurazioneRag):
        dividi_ricetta(r, "sconosciuta", 1200, 200)
    with pytest.raises(ErroreConfigurazioneRag):
        dividi_ricetta(r, "paragrafi", 0, 0)
    with pytest.raises(ErroreConfigurazioneRag):
        dividi_ricetta(r, "paragrafi", 100, 100)
