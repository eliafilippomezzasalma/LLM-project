"""Valutazione con fonte attesa: cerca_fn finta, nessun Qdrant."""

import json
from pathlib import Path

import pytest

from rag.errori import ErroreRag
from rag.ricerca import EsitoRicerca, Risultato
from rag.valutazione import Domanda, carica_domande, tabella_markdown, valuta

FILE_AULA = Path(__file__).parent.parent / "rag" / "domande_valutazione.json"


def _ris(posizione, ricetta, score):
    return Risultato(posizione, score, ricetta, f"Ricetta {ricetta}", "Cap", 1, "testo")


def _finta(per_domanda):
    def cerca_fn(domanda, k):
        return EsitoRicerca(per_domanda[domanda][:k], k, None, None)
    return cerca_fn


def test_posizione_della_fonte():
    d = Domanda("q", (89,), "aula")
    cerca_fn = _finta({"q": [_ris(1, 5, 0.9), _ris(2, 6, 0.8), _ris(3, 89, 0.777)]})
    riga = valuta([d], cerca_fn, 5)[0]
    assert riga.posizione == 3
    assert riga.score_fonte == 0.777
    assert riga.score_migliore == 0.9
    assert riga.prima.ricetta == 5
    assert "0,777" in tabella_markdown([riga], 5)


def test_fonte_assente():
    d = Domanda("q", (89,), "aula")
    riga = valuta([d], _finta({"q": [_ris(1, 5, 0.9)]}), 5)[0]
    assert riga.posizione is None and riga.score_fonte is None
    assert "assente" in tabella_markdown([riga], 5)


def test_piu_ricette_attese():
    d = Domanda("q", (455, 456), "aula")
    riga = valuta([d], _finta({"q": [_ris(1, 1, 0.9), _ris(2, 456, 0.8)]}), 5)[0]
    assert riga.posizione == 2


def test_senza_risposta():
    righe = valuta(
        [Domanda("a", (1,), "aula"), Domanda("t", (), "aula")],
        _finta({"a": [_ris(1, 1, 0.9)], "t": [_ris(1, 7, 0.512)]}), 5,
    )
    t = tabella_markdown(righe, 5)
    assert "nessuna (non nel libro)" in t
    assert "Fonte attesa nei primi 5: 1 su 1" in t
    assert "Score migliore delle domande senza risposta: 0,512" in t


def test_riepilogo():
    ds = [Domanda(str(i), (i,), "aula") for i in (1, 2, 3)]
    per = {"1": [_ris(1, 1, 0.9)], "2": [_ris(1, 2, 0.8)], "3": [_ris(1, 9, 0.7)]}
    t = tabella_markdown(valuta(ds, _finta(per), 5), 5)
    assert "2 su 3" in t


def test_file_domande_aula():
    ds = carica_domande(FILE_AULA)
    aula = [d for d in ds if d.origine == "aula"]
    proprie = [d for d in ds if d.origine == "propria"]
    assert len(aula) == 6 and len(proprie) == 13
    assert aula[-1].attese == () and "tiramisù" in aula[-1].testo
    assert aula[2].attese == (455, 456)
    assert [d.attese for d in proprie[:5]] == [(731,), (591,), (434,), (760,), ()]
    assert proprie[6].attese == (119, 120)


def test_file_malformato(tmp_path):
    p = tmp_path / "d.json"
    p.write_text(json.dumps([{"domanda": "x", "origine": "aula"}]), encoding="utf-8")
    with pytest.raises(ErroreRag):
        carica_domande(p)


def test_main_k_limitato_come_la_ricerca(capsys, monkeypatch):
    from rag import valutazione
    from rag.config import ConfigRag

    config = ConfigRag(
        lm_base_url="http://x/v1", embedding_model="finto", qdrant_url="http://localhost:6333",
        collezione="c", corpus=FILE_AULA, strategia="paragrafi", dimensione=200, overlap=50, k_max=10,
    )
    ricevuti = []

    def cerca_finta(domanda, client, embedder, config, k):
        ricevuti.append(k)
        return EsitoRicerca([], k, None, None)

    monkeypatch.setattr(valutazione, "carica_config_rag", lambda: config)
    monkeypatch.setattr(valutazione, "crea_client", lambda url: None)
    monkeypatch.setattr(valutazione, "cerca", cerca_finta)
    assert valutazione.main(["--k", "20"]) == 0
    fuori = capsys.readouterr()
    assert "primi 10" in fuori.out
    assert "k ridotto a 10" in fuori.err
    assert set(ricevuti) == {10}
