"""Divisione delle ricette in chunk con ID stabili (specs.md §20.3)."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from rag.config import ErroreConfigurazioneRag
from rag.corpus import Ricetta

# Costante fissa: cambiarla cambierebbe tutti gli ID dei punti già indicizzati.
NAMESPACE_RAG = uuid.UUID("6f1c2a54-3b7e-4d0a-9c58-2e4f7a1b8d93")

STRATEGIE = ("paragrafi", "finestra")
_SEPARATORE_PARAGRAFI = "\n\n"
_SEPARATORE_OVERLAP = "\n"


@dataclass(frozen=True)
class Chunk:
    """Un pezzo di ricetta, con i metadati della ricetta di origine."""

    ricetta: int
    titolo: str
    capitolo: str
    posizione: int
    testo: str

    @property
    def documento_id(self) -> str:
        return f"ricetta-{self.ricetta:03d}"

    @property
    def id_punto(self) -> str:
        """UUID deterministico: stessa ricetta e posizione, stesso ID a ogni esecuzione."""
        return str(uuid.uuid5(NAMESPACE_RAG, f"{self.documento_id}#{self.posizione}"))


def contenuto_da_incorporare(chunk: Chunk, titolo_nel_testo: bool = False, prefisso: str = "") -> str:
    """Testo che diventa vettore (§21): titolo e capitolo davanti se richiesto, poi il prefisso."""
    testo = f"{chunk.titolo} — {chunk.capitolo}\n\n{chunk.testo}" if titolo_nel_testo else chunk.testo
    return f"{prefisso} {testo}" if prefisso else testo


def _valida(strategia: str, dimensione: int, overlap: int) -> None:
    if strategia not in STRATEGIE:
        raise ErroreConfigurazioneRag(f"Strategia di chunking sconosciuta: {strategia!r} (ammesse: {', '.join(STRATEGIE)})")
    if dimensione < 1:
        raise ErroreConfigurazioneRag(f"La dimensione dei chunk deve essere almeno 1, non {dimensione}")
    if not 0 <= overlap < dimensione:
        raise ErroreConfigurazioneRag(f"L'overlap deve stare tra 0 e dimensione-1 ({dimensione - 1}), non {overlap}")


def _fine_finestra(testo: str, inizio: int, dimensione: int) -> int:
    """Fine (esclusa) della finestra che parte da `inizio`: preferisce fine frase, poi fine parola."""
    fine = inizio + dimensione
    if fine >= len(testo):
        return len(testo)
    frase = testo.rfind(". ", inizio + dimensione // 2, fine + 1)
    if frase != -1:
        return frase + 1  # include il punto
    spazio = max(testo.rfind(" ", inizio + 1, fine + 1), testo.rfind("\n", inizio + 1, fine + 1))
    return spazio if spazio != -1 else fine  # parola più lunga della finestra: taglio netto


def _spezza_a_finestra(testo: str, dimensione: int) -> list[str]:
    """Spezza un testo troppo lungo in pezzi di al massimo `dimensione` caratteri, senza overlap."""
    pezzi = []
    inizio = 0
    while inizio < len(testo):
        fine = _fine_finestra(testo, inizio, dimensione)
        pezzo = testo[inizio:fine].strip()
        if pezzo:
            pezzi.append(pezzo)
        inizio = fine
        while inizio < len(testo) and testo[inizio].isspace():
            inizio += 1
    return pezzi


def _coda_overlap(testo: str, overlap: int) -> str:
    """Ultimi caratteri di `testo` (al massimo `overlap`), iniziando da un confine di parola."""
    if overlap <= 0 or not testo:
        return ""
    if len(testo) <= overlap:
        return testo
    inizio = len(testo) - overlap
    if not testo[inizio - 1].isspace():  # siamo dentro una parola: salta al suo termine
        while inizio < len(testo) and not testo[inizio].isspace():
            inizio += 1
    return testo[inizio:].strip()


def _chunk_per_paragrafi(testo: str, dimensione: int, overlap: int) -> list[str]:
    if len(testo) <= dimensione:
        return [testo]
    unita: list[str] = []
    for paragrafo in testo.split(_SEPARATORE_PARAGRAFI):
        paragrafo = paragrafo.strip()
        if not paragrafo:
            continue
        unita.extend([paragrafo] if len(paragrafo) <= dimensione else _spezza_a_finestra(paragrafo, dimensione))
    corpi: list[str] = []
    corrente = ""
    for pezzo in unita:
        candidato = f"{corrente}{_SEPARATORE_PARAGRAFI}{pezzo}" if corrente else pezzo
        if len(candidato) <= dimensione:
            corrente = candidato
        else:
            corpi.append(corrente)
            corrente = pezzo
    if corrente:
        corpi.append(corrente)
    # L'overlap si somma al corpo: un chunk è lungo al più dimensione + overlap.
    chunk = [corpi[0]]
    for precedente, corpo in zip(corpi, corpi[1:]):
        coda = _coda_overlap(precedente, overlap - len(_SEPARATORE_OVERLAP))
        chunk.append(f"{coda}{_SEPARATORE_OVERLAP}{corpo}" if coda else corpo)
    return chunk


def _inizio_parola(testo: str, posizione: int) -> int:
    """Porta `posizione` indietro fino all'inizio della parola in cui cade."""
    while posizione > 0 and not testo[posizione - 1].isspace() and not testo[posizione].isspace():
        posizione -= 1
    return posizione


def _chunk_a_finestra(testo: str, dimensione: int, overlap: int) -> list[str]:
    passo = dimensione - overlap
    chunk: list[str] = []
    inizio = 0
    while True:
        fine = len(testo) if inizio + dimensione >= len(testo) else inizio + dimensione
        if fine < len(testo) and not testo[fine].isspace():  # la finestra taglia una parola: arretra
            spazio = max(testo.rfind(" ", inizio, fine), testo.rfind("\n", inizio, fine))
            fine = spazio if spazio > inizio else fine
        pezzo = testo[inizio:fine].strip()
        if pezzo:
            chunk.append(pezzo)
        if fine >= len(testo):
            return chunk
        prossimo = _inizio_parola(testo, inizio + passo)
        inizio = prossimo if prossimo > inizio else inizio + passo


def dividi_ricetta(ricetta: Ricetta, strategia: str, dimensione: int, overlap: int) -> list[Chunk]:
    """Divide una ricetta in chunk numerati da 0; un chunk non contiene mai testo di altre ricette."""
    _valida(strategia, dimensione, overlap)
    testo = ricetta.testo.strip()
    if not testo:
        return []
    if strategia == "paragrafi":
        testi = _chunk_per_paragrafi(testo, dimensione, overlap)
    else:
        testi = _chunk_a_finestra(testo, dimensione, overlap)
    return [Chunk(ricetta.numero, ricetta.titolo, ricetta.capitolo, i, t) for i, t in enumerate(testi)]


def dividi_tutte(ricette: Iterable[Ricetta], strategia: str, dimensione: int, overlap: int) -> list[Chunk]:
    """Divide tutte le ricette, nell'ordine dato."""
    return [c for ricetta in ricette for c in dividi_ricetta(ricetta, strategia, dimensione, overlap)]
