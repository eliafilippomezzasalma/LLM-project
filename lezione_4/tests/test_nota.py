from langchain_core.tools import StructuredTool

import scadenze
from assistente import nota
from assistente.nota import NotaNonNormativa, con_nota

RIGA = f"Nota: {nota.FRASE_NOTA}"
CON_RIGA = f"Scadenza: X.\n{RIGA}"


def test_filtra():
    prima = NotaNonNormativa()
    assert prima.filtra(CON_RIGA) == CON_RIGA
    gia = NotaNonNormativa(consegnata=True)
    assert gia.filtra(CON_RIGA) == "Scadenza: X."
    for n in (prima, gia):
        assert n.filtra("Scadenza: X.") == "Scadenza: X."


def test_registra_risposta():
    n = NotaNonNormativa()
    n.registra_risposta("Scade il 2026-01-02. Nota: assenza della frase")
    assert n.consegnata is False
    n.registra_risposta(f"Scade il 2026-01-02.\n{RIGA}")
    assert n.consegnata is True
    n.registra_risposta("Altra risposta senza la frase")
    assert n.consegnata is True


def _scadenza(giorni: int) -> str:
    return f"Scadenza: X.\n{RIGA}"


def _info(a: str) -> str:
    return "info"


def test_con_nota_tocca_solo_compute_deadline():
    scad = StructuredTool.from_function(_scadenza, name="compute_deadline", description="descrizione")
    info = StructuredTool.from_function(_info, name="date_info", description="altro")
    n = NotaNonNormativa()
    nuovi = con_nota([scad, info], n)
    assert nuovi[1] is info
    assert nuovi[0].name == "compute_deadline"
    assert nuovi[0].description == "descrizione"
    assert nuovi[0].invoke({"giorni": 3}) == CON_RIGA
    n.consegnata = True
    assert nuovi[0].invoke({"giorni": 3}) == "Scadenza: X."


def test_frase_uguale_al_server():
    assert nota.FRASE_NOTA == scadenze.FRASE_NOTA
    assert nota.RIGA_NOTA == scadenze.RIGA_NOTA


def test_completa():
    n = NotaNonNormativa()
    assert n.completa("Scade il 2026-01-02.", [CON_RIGA]) == f"Scade il 2026-01-02.\n\n{RIGA}"
    riformulata = "Scade il 2026-01-02. *Nota: questo è un calcolo indicativo e non ha valore legale.*"
    assert n.completa(riformulata, [CON_RIGA]) == riformulata
    assert n.completa("Errore.", ["Errore: data non valida"]) == "Errore."
    assert n.completa("Ok.", []) == "Ok."
    assert NotaNonNormativa(consegnata=True).completa("Ok.", [CON_RIGA]) == "Ok."
    assert n.consegnata is False
