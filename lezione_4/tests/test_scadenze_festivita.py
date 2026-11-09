"""Test del file delle festività di `scadenze.py`: lettura e controlli (senza server MCP)."""

import json
from datetime import date, timedelta

import pytest

from scadenze import ErroreFestivita, carica_festivita


def _pasqua(anno):
    """Pasqua gregoriana (algoritmo anonimo «Meeus/Jones/Butcher»), solo per il test."""
    a = anno % 19
    b, c = divmod(anno, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese, giorno = divmod(h + l - 7 * m + 114, 31)
    return date(anno, mese, giorno + 1)


def _valido():
    """Dizionario valido (11 festività fino al 2025, 12 dal 2026), nella forma del file."""
    fisse = [
        ("01-01", "Capodanno"),
        ("01-06", "Epifania"),
        ("04-25", "Festa della Liberazione"),
        ("05-01", "Festa del Lavoro"),
        ("06-02", "Festa della Repubblica"),
        ("08-15", "Assunzione"),
        ("11-01", "Ognissanti"),
        ("12-08", "Immacolata Concezione"),
        ("12-25", "Natale"),
        ("12-26", "Santo Stefano"),
    ]
    dati = {}
    for anno in range(2020, 2041):
        voci = [(f"{anno}-{md}", nome) for md, nome in fisse]
        voci.append(((_pasqua(anno) + timedelta(days=1)).isoformat(), "Lunedì dell'Angelo"))
        if anno >= 2026:
            voci.append((f"{anno}-10-04", "San Francesco d'Assisi"))
        dati[str(anno)] = [{"data": d, "nome": n} for d, n in sorted(voci)]
    return dati


def test_file_vero_si_carica():
    assert len(carica_festivita()) == 6 * 11 + 15 * 12


def test_pasquetta_come_algoritmo():
    festivita = carica_festivita()
    for anno in range(2020, 2041):
        pasquette = [d for d, n in festivita.items() if n == "Lunedì dell'Angelo" and d.year == anno]
        assert pasquette == [_pasqua(anno) + timedelta(days=1)]
    assert _pasqua(2024) + timedelta(days=1) == date(2024, 4, 1)
    assert _pasqua(2026) + timedelta(days=1) == date(2026, 4, 6)
    assert _pasqua(2038) + timedelta(days=1) == date(2038, 4, 26)
    assert festivita[date(2024, 4, 1)] == "Lunedì dell'Angelo"
    assert festivita[date(2026, 4, 6)] == "Lunedì dell'Angelo"
    assert festivita[date(2038, 4, 26)] == "Lunedì dell'Angelo"


def test_san_francesco_dal_2026():
    festivita = carica_festivita()
    assert date(2025, 10, 4) not in festivita
    assert festivita[date(2026, 10, 4)] == "San Francesco d'Assisi"
    assert festivita[date(2040, 10, 4)] == "San Francesco d'Assisi"


def test_date_fisse():
    festivita = carica_festivita()
    attese = {
        (1, 1): "Capodanno",
        (1, 6): "Epifania",
        (4, 25): "Festa della Liberazione",
        (5, 1): "Festa del Lavoro",
        (6, 2): "Festa della Repubblica",
        (8, 15): "Assunzione",
        (11, 1): "Ognissanti",
        (12, 8): "Immacolata Concezione",
        (12, 25): "Natale",
        (12, 26): "Santo Stefano",
    }
    for anno in (2020, 2040):
        for (mese, giorno), nome in attese.items():
            assert festivita[date(anno, mese, giorno)] == nome


def _mancante(tmp_path):
    return tmp_path / "non_esiste.json"


def _non_json(tmp_path):
    p = tmp_path / "f.json"
    p.write_text("{non è json", encoding="utf-8")
    return p


def _scrivi(tmp_path, dati):
    p = tmp_path / "f.json"
    p.write_text(json.dumps(dati, ensure_ascii=False), encoding="utf-8")
    return p


def _senza_2033(tmp_path):
    dati = _valido()
    del dati["2033"]
    return _scrivi(tmp_path, dati)


def _con_2041(tmp_path):
    dati = _valido()
    dati["2041"] = [{"data": "2041-01-01", "nome": "Capodanno"}]
    return _scrivi(tmp_path, dati)


def _data_impossibile(tmp_path):
    dati = _valido()
    dati["2026"][1]["data"] = "2026-02-30"
    return _scrivi(tmp_path, dati)


def _anno_sbagliato(tmp_path):
    dati = _valido()
    dati["2026"][0]["data"] = "2027-01-01"
    return _scrivi(tmp_path, dati)


def _nome_vuoto(tmp_path):
    dati = _valido()
    dati["2026"][0]["nome"] = "  "
    return _scrivi(tmp_path, dati)


def _una_in_meno(tmp_path):
    dati = _valido()
    dati["2030"].pop()
    return _scrivi(tmp_path, dati)


def _data_ripetuta(tmp_path):
    dati = _valido()
    dati["2030"][1]["data"] = dati["2030"][0]["data"]
    return _scrivi(tmp_path, dati)


@pytest.mark.parametrize(
    "prepara",
    [
        _mancante,
        _non_json,
        _senza_2033,
        _con_2041,
        _data_impossibile,
        _anno_sbagliato,
        _nome_vuoto,
        _una_in_meno,
        _data_ripetuta,
    ],
)
def test_file_rovinati(tmp_path, prepara):
    with pytest.raises(ErroreFestivita):
        carica_festivita(prepara(tmp_path))


def test_file_valido_in_tmp_si_carica(tmp_path):
    assert len(carica_festivita(_scrivi(tmp_path, _valido()))) == 246
