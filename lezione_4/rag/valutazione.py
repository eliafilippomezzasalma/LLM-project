"""Valutazione della ricerca su domande con fonte attesa (specs.md §20.8)."""

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from rag.config import carica_config_rag
from rag.embedding import EmbedderLMStudio
from rag.errori import ErroreRag, usa_utf8
from rag.indice import crea_client
from rag.ricerca import K_PREDEFINITO, EsitoRicerca, Risultato, cerca, crea_riscrittore, limita_k

FILE_PREDEFINITO = Path(__file__).parent / "domande_valutazione.json"
ORIGINI = ("aula", "propria")


@dataclass(frozen=True)
class Domanda:
    testo: str
    attese: tuple[int, ...]
    origine: str


@dataclass(frozen=True)
class Riga:
    domanda: Domanda
    posizione: int | None
    score_fonte: float | None
    score_migliore: float
    prima: Risultato | None
    cercata: str = ""  # testo effettivamente cercato (diverso dalla domanda con la riscrittura)


def carica_domande(percorso: Path) -> list[Domanda]:
    """Legge il file JSON delle domande; formato errato → ErroreRag."""
    try:
        dati = json.loads(Path(percorso).read_text(encoding="utf-8"))
    except (OSError, ValueError) as errore:
        raise ErroreRag(f"file delle domande illeggibile ({percorso}): {errore}") from errore
    if not isinstance(dati, list):
        raise ErroreRag("il file delle domande deve contenere una lista")
    domande = []
    for i, voce in enumerate(dati, start=1):
        if not isinstance(voce, dict):
            raise ErroreRag(f"domanda {i}: voce non valida")
        for chiave in ("domanda", "attese", "origine"):
            if chiave not in voce:
                raise ErroreRag(f"domanda {i}: manca il campo «{chiave}»")
        testo, attese, origine = voce["domanda"], voce["attese"], voce["origine"]
        if not isinstance(testo, str) or not testo.strip():
            raise ErroreRag(f"domanda {i}: testo non valido")
        if not isinstance(attese, list) or not all(
            isinstance(n, int) and not isinstance(n, bool) for n in attese
        ):
            raise ErroreRag(f"domanda {i}: «attese» deve essere una lista di numeri interi")
        if origine not in ORIGINI:
            raise ErroreRag(f"domanda {i}: origine {origine!r} non valida (attese: {', '.join(ORIGINI)})")
        domande.append(Domanda(testo, tuple(attese), origine))
    return domande


def valuta(
    domande: list[Domanda], cerca_fn: Callable[[str, int], EsitoRicerca], k: int
) -> list[Riga]:
    """Esegue la ricerca per ogni domanda e cerca la prima fonte attesa tra i risultati."""
    righe = []
    for d in domande:
        esito = cerca_fn(d.testo, k)
        risultati = esito.risultati
        trovato = next((r for r in risultati if r.ricetta in d.attese), None)
        righe.append(Riga(
            domanda=d,
            posizione=trovato.posizione if trovato else None,
            score_fonte=trovato.score if trovato else None,
            score_migliore=max((r.score for r in risultati), default=0.0),
            prima=risultati[0] if risultati else None,
            cercata=esito.domanda_cercata or d.testo,
        ))
    return righe


def _num(valore: float) -> str:
    return f"{valore:.3f}".replace(".", ",")


def _cella(testo: str) -> str:
    return testo.replace("|", "\\|")


def tabella_markdown(righe: list[Riga], k: int) -> str:
    """Tabella Markdown riproducibile con il riepilogo in fondo."""
    linee = [
        "| Domanda | Fonte attesa | Posizione | Score fonte | Score migliore | Primo risultato |",
        "|---|---|---|---|---|---|",
    ]
    for r in righe:
        attese = ", ".join(str(n) for n in r.domanda.attese) or "nessuna (non nel libro)"
        if r.domanda.attese:
            posizione = str(r.posizione) if r.posizione is not None else "assente"
        else:
            posizione = "—"
        score_fonte = _num(r.score_fonte) if r.score_fonte is not None else "—"
        prima = f"{r.prima.ricetta} — {r.prima.titolo}" if r.prima else "—"
        linee.append(
            f"| {_cella(r.domanda.testo)} | {attese} | {posizione} | {score_fonte} | "
            f"{_num(r.score_migliore)} | {_cella(prima)} |"
        )
    con_risposta = [r for r in righe if r.domanda.attese]
    trovate = sum(1 for r in con_risposta if r.posizione is not None)
    senza = [_num(r.score_migliore) for r in righe if not r.domanda.attese]
    linee.append("")
    linee.append(f"Fonte attesa nei primi {k}: {trovate} su {len(con_risposta)}")
    linee.append(
        "Score migliore delle domande senza risposta: " + (", ".join(senza) if senza else "—")
    )
    for origine in ORIGINI:
        gruppo = [r for r in con_risposta if r.domanda.origine == origine]
        if gruppo and len(gruppo) < len(con_risposta):
            n = sum(1 for r in gruppo if r.posizione is not None)
            linee.append(f"Domande «{origine}»: {n} su {len(gruppo)}")
    riscritte = [r for r in righe if r.cercata and r.cercata != r.domanda.testo]
    if riscritte:
        linee += ["", "Domande riscritte (testo cercato = domanda + riscrittura):"]
        linee += [f"- {_cella(r.domanda.testo)} → {r.cercata.split(chr(10), 1)[-1]}" for r in riscritte]
    return "\n".join(linee)


def main(argv: list[str] | None = None) -> int:
    usa_utf8()
    parser = argparse.ArgumentParser(
        prog="python -m rag.valutazione", description="Valutazione della ricerca con fonte attesa."
    )
    parser.add_argument("--k", type=int, default=K_PREDEFINITO)
    parser.add_argument("--domande", type=Path, default=FILE_PREDEFINITO)
    parser.add_argument(
        "--solo-dosi", action="store_true", help="applica a tutte le domande il filtro contiene_dosi"
    )
    args = parser.parse_args(argv)
    try:
        domande = carica_domande(args.domande)
        config = carica_config_rag()
        embedder = EmbedderLMStudio(config.lm_base_url, config.embedding_model)
        client = crea_client(config.qdrant_url)
        k, nota = limita_k(args.k, config.k_max)
        if nota:
            print(f"Nota: {nota}", file=sys.stderr)
        extra = {"riscrittore": crea_riscrittore(config)} if config.riscrittura else {}
        if args.solo_dosi:
            extra["solo_dosi"] = True
        righe = valuta(
            domande, lambda domanda, k: cerca(domanda, client, embedder, config, k=k, **extra), k
        )
    except ErroreRag as errore:
        print(f"Errore: {errore}", file=sys.stderr)
        return 1
    print(tabella_markdown(righe, k))
    return 0


if __name__ == "__main__":
    sys.exit(main())
