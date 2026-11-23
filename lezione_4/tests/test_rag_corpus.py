from pathlib import Path

import pytest

from rag.corpus import CAPITOLI, ErroreCorpus, Ricetta, carica_corpus, leggi_ricette, verifica_ricette

CARTELLA = Path(__file__).resolve().parent
ESTRATTO = CARTELLA / "dati_rag" / "estratto.txt"
ARTUSI = CARTELLA.parent / "dati" / "artusi.txt"


@pytest.fixture(scope="module")
def ricette():
    return leggi_ricette(ESTRATTO.read_text(encoding="utf-8"))


def test_estratto_quattro_ricette(ricette):
    assert [r.numero for r in ricette] == [1, 2, 3, 4]
    assert [r.capitolo for r in ricette] == ["Brodi, gelatina e sughi"] * 3 + ["Minestre in brodo"]
    assert ricette[0].titolo == "Brodo"


def test_riga_del_corpo_con_numero_non_e_titolo(ricette):
    assert "5. Mettete" in ricette[3].testo
    assert all(r.numero != 5 for r in ricette)


def test_appendice_esclusa(ricette):
    assert all("Falso titolo" not in r.testo and "Falso titolo" not in r.titolo for r in ricette)


def test_introduzione_del_capitolo_esclusa(ricette):
    assert all("introduzione" not in r.testo for r in ricette)


def test_pulizia(ricette):
    for r in ricette:
        assert "\r" not in r.testo
        assert "_" not in r.testo
        assert r.testo == r.testo.strip()
    assert "parmigiano grattato" in ricette[3].testo
    primo = ricette[0].testo
    assert "per ottenere il brodo buono bisogna mettere la carne" in primo
    assert "\n\n" in primo
    ingredienti = [r for r in ricette[3].testo.split("\n") if r.startswith(("Burro", "Farina", "Brodo,"))]
    assert ingredienti == [
        "Burro, grammi 50.",
        "Farina bianca finissima, due cucchiaiate colme, ossia circa grammi 30.",
        "Brodo, mezzo litro.",
    ]


def test_bom_ignorato(tmp_path):
    file = tmp_path / "con_bom.txt"
    file.write_bytes(b"\xef\xbb\xbf" + ESTRATTO.read_bytes())
    ricette = carica_corpus(file, attese=4)
    assert len(ricette) == 4
    assert ricette[0].titolo == "Brodo"
    assert "\ufeff" not in ricette[0].titolo


def _r(n):
    return Ricetta(n, f"T{n}", "Uova", "testo")


def test_verifica_buco():
    with pytest.raises(ErroreCorpus, match="2"):
        verifica_ricette([_r(1), _r(3), _r(4)], attese=3)


def test_verifica_conteggio(ricette):
    with pytest.raises(ErroreCorpus, match="790"):
        verifica_ricette(ricette, attese=790)


def test_verifica_vuoti():
    with pytest.raises(ErroreCorpus, match="titolo"):
        verifica_ricette([Ricetta(1, "", "Uova", "x")], attese=1)


def test_file_assente(tmp_path):
    percorso = tmp_path / "no.txt"
    with pytest.raises(ErroreCorpus, match="no.txt"):
        carica_corpus(percorso)


def test_capitoli_sono_23():
    assert len(CAPITOLI) == 23
    assert CAPITOLI[5] == "Uova"


@pytest.mark.skipif(not ARTUSI.exists(), reason="dati/artusi.txt manca")
def test_file_vero():
    ricette = carica_corpus(ARTUSI)
    assert len(ricette) == 790
    per_numero = {r.numero: r for r in ricette}
    titoli = {7: "Cappelletti all'uso di Romagna", 89: "Gnocchi di patate", 208: "Pollo alla cacciatora",
              455: "Cacciucco I", 790: "Spezie fini"}
    for numero, titolo in titoli.items():
        assert per_numero[numero].titolo == titolo
    capitoli = {1: "Brodi, gelatina e sughi", 7: "Minestre in brodo", 89: "Minestre asciutte e di magro",
                139: "Uova", 208: "Fritti", 455: "Piatti di pesce", 790: "Cose diverse"}
    for numero, capitolo in capitoli.items():
        assert per_numero[numero].capitolo == capitolo
    assert all(r.capitolo in CAPITOLI for r in ricette)
    assert {r.capitolo for r in ricette} == set(CAPITOLI)
    assert all("Project Gutenberg" not in r.testo for r in ricette)
