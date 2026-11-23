"""Lettura e pulizia del ricettario dell'Artusi: le 790 ricette numerate come documenti (specs.md §20.2)."""

import re
from dataclasses import dataclass
from pathlib import Path

from rag.errori import ErroreRag

# Intestazioni dei capitoli come compaiono nel libro (maiuscolo), in ordine di libro.
_INTESTAZIONI = (
    "BRODI, GELATINA E SUGHI",
    "MINESTRE IN BRODO",
    "MINESTRE ASCIUTTE E DI MAGRO",
    "PRINCIPII",
    "SALSE",
    "UOVA",
    "PASTE E PASTELLE",
    "RIPIENI",
    "FRITTI",
    "LESSO",
    "TRAMESSI",
    "UMIDI",
    "RIFREDDI",
    "ERBAGGI E LEGUMI",
    "PIATTI DI PESCE",
    "ARROSTI",
    "PASTICCERIA",
    "TORTE E DOLCI AL CUCCHIAIO",
    "SIROPPI",
    "CONSERVE",
    "LIQUORI",
    "GELATI",
    "COSE DIVERSE",
)
# Sovra-intestazioni: non sono capitoli, ma chiudono la ricetta precedente (inizia un'introduzione).
_SOVRA_INTESTAZIONI = ("MINESTRE",)
_PER_INTESTAZIONE = {i: i.capitalize() for i in _INTESTAZIONI}
CAPITOLI = tuple(_PER_INTESTAZIONE.values())

_TITOLO = re.compile(r"^(\d+)\. (.+)$")
_CORSIVO = re.compile(r"_([^_]+)_")


class ErroreCorpus(ErroreRag):
    """Il file del ricettario manca o non contiene le ricette attese."""


@dataclass(frozen=True)
class Ricetta:
    numero: int
    titolo: str
    capitolo: str
    testo: str


def _pulisci(righe: list[str]) -> str:
    """Righe grezze di una ricetta -> testo pulito (paragrafi e ingredienti)."""
    testo = _CORSIVO.sub(r"\1", "\n".join(righe))
    blocchi: list[list[str]] = []  # ogni blocco e un paragrafo (1 riga) o un elenco rientrato
    tipo = ""  # "paragrafo" | "elenco" | "" (nessun blocco aperto)
    rientro_prec = 0
    for riga in testo.split("\n"):
        if not riga.strip():
            tipo = ""
            continue
        rientro = len(riga) - len(riga.lstrip(" "))
        pulita = re.sub(r" +", " ", riga.strip())
        if rientro == 0:
            if tipo == "paragrafo":
                blocchi[-1][0] += " " + pulita
            else:
                blocchi.append([pulita])
                tipo = "paragrafo"
        else:
            if tipo != "elenco":
                blocchi.append([pulita])
                tipo = "elenco"
            elif rientro > rientro_prec:  # continuazione dell'ingrediente precedente
                blocchi[-1][-1] += " " + pulita
            else:
                blocchi[-1].append(pulita)
            rientro_prec = rientro
    return "\n\n".join("\n".join(b) for b in blocchi).strip()


def leggi_ricette(testo: str) -> list[Ricetta]:
    """Testo grezzo del libro -> ricette pulite, in ordine (solo le numerate, fino a APPENDICE)."""
    righe = testo.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    inizio = next((i for i, r in enumerate(righe) if r.startswith("*** START OF THE PROJECT GUTENBERG")), -1)
    righe = righe[inizio + 1 :]
    ricette_inizio = next((i for i, r in enumerate(righe) if r.strip() == "RICETTE"), None)
    if ricette_inizio is None:
        return []

    grezze: list[tuple[int, str, str, list[str]]] = []  # numero, titolo, capitolo, righe del corpo
    capitolo = ""
    attuale: list[str] | None = None  # corpo della ricetta in corso (None = introduzione)
    precedente_vuota = True
    for riga in righe[ricette_inizio + 1 :]:
        pulita = riga.strip()
        if grezze and pulita == "APPENDICE":
            break
        intestazione = _PER_INTESTAZIONE.get(pulita)
        if intestazione and precedente_vuota:
            capitolo = intestazione
            attuale = None
        elif pulita in _SOVRA_INTESTAZIONI and precedente_vuota:
            attuale = None
        else:
            m = _TITOLO.match(riga)
            if m and precedente_vuota and int(m.group(1)) == len(grezze) + 1 and capitolo:
                attuale = []
                grezze.append((int(m.group(1)), m.group(2).strip(), capitolo, attuale))
            elif attuale is not None:
                attuale.append(riga)
        precedente_vuota = not pulita
    return [Ricetta(n, t, c, _pulisci(corpo)) for n, t, c, corpo in grezze]


def verifica_ricette(ricette: list[Ricetta], attese: int = 790) -> None:
    """Solleva ErroreCorpus al primo problema: numerazione, campi vuoti, conteggio."""
    for posizione, r in enumerate(ricette, start=1):
        if r.numero > posizione:
            raise ErroreCorpus(f"Corpus incoerente: manca la ricetta {posizione}")
        if r.numero < posizione:
            raise ErroreCorpus(f"Corpus incoerente: la ricetta {r.numero} compare due volte")
        for campo in ("titolo", "capitolo", "testo"):
            if not getattr(r, campo).strip():
                raise ErroreCorpus(f"Corpus incoerente: la ricetta {r.numero} ha il {campo} vuoto")
    if len(ricette) != attese:
        raise ErroreCorpus(f"Corpus incoerente: trovate {len(ricette)} ricette, attese {attese}")


def carica_corpus(percorso: Path, attese: int = 790) -> list[Ricetta]:
    """Legge il file (UTF-8, BOM ignorato), estrae le ricette e le verifica."""
    try:
        testo = Path(percorso).read_text(encoding="utf-8-sig")
    except OSError as errore:
        raise ErroreCorpus(f"Impossibile leggere il corpus {percorso}: {errore.strerror or errore}") from errore
    ricette = leggi_ricette(testo)
    verifica_ricette(ricette, attese)
    return ricette
