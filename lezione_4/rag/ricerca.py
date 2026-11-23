"""Ricerca semantica top-k con filtri per capitolo e per dosi applicati da Qdrant (specs.md §20.7, §22.2)."""

import argparse
import sys
from dataclasses import dataclass

from qdrant_client import models

from rag.config import ConfigRag, carica_config_rag
from rag.corpus import CAPITOLI
from rag.embedding import Embedder, EmbedderLMStudio
from rag.errori import ErroreRag, usa_utf8
from rag.indice import connessione, crea_client, impostazioni_indice, verifica_modello
from rag.riscrittura import Riscrittore, RiscrittoreLMStudio

K_PREDEFINITO = 5


class ErroreCapitolo(ErroreRag):
    """Il capitolo richiesto non è nell'elenco chiuso dei capitoli."""


@dataclass(frozen=True)
class Risultato:
    posizione: int
    score: float
    ricetta: int
    titolo: str
    capitolo: str
    posizione_chunk: int
    testo: str
    contiene_dosi: bool | None = None  # §22: None se la collezione non ha ancora il campo


@dataclass(frozen=True)
class EsitoRicerca:
    risultati: list[Risultato]
    k: int
    capitolo: str | None
    nota: str | None
    domanda_cercata: str = ""  # §21: domanda + riscrittura, se la riscrittura è attiva


def _chiave(nome: str) -> str:
    return " ".join(nome.split()).casefold()


def normalizza_capitolo(nome: str) -> str:
    """Nome canonico del capitolo (senza badare a maiuscole e spazi); sconosciuto → ErroreCapitolo."""
    for canonico in CAPITOLI:
        if _chiave(canonico) == _chiave(nome):
            return canonico
    raise ErroreCapitolo(f"capitolo {nome!r} sconosciuto; capitoli validi: " + ", ".join(CAPITOLI))


def limita_k(k: int, k_max: int) -> tuple[int, str | None]:
    if k > k_max:
        return k_max, f"k ridotto a {k_max}, il massimo consentito"
    if k < 1:
        return 1, "k portato a 1"
    return k, None


def cerca(
    domanda: str, client, embedder: Embedder, config: ConfigRag,
    k: int = K_PREDEFINITO, capitolo: str | None = None, riscrittore: Riscrittore | None = None,
    solo_dosi: bool = False,
) -> EsitoRicerca:
    """I k chunk più vicini alla domanda; il filtro per capitolo è inviato a Qdrant.

    Con un riscrittore si cerca «domanda + riscrittura» (§21.3); il prefisso della domanda e le
    impostazioni registrate nella collezione devono coincidere con la configurazione (§21.5).
    """
    if not domanda.strip():
        raise ErroreRag("la domanda è vuota: scrivi cosa vuoi cercare")
    canonico = normalizza_capitolo(capitolo) if capitolo is not None else None
    k, nota = limita_k(k, config.k_max)
    condizioni = []
    if canonico is not None:
        condizioni.append(models.FieldCondition(key="capitolo", match=models.MatchValue(value=canonico)))
    if solo_dosi:
        condizioni.append(models.FieldCondition(key="contiene_dosi", match=models.MatchValue(value=True)))
    filtro = models.Filter(must=condizioni) if condizioni else None
    cercata = domanda
    if riscrittore is not None:
        riscritta = riscrittore.riscrivi(domanda)
        if riscritta:
            cercata = f"{domanda}\n{riscritta}"
    prefisso = config.prefisso_domanda
    vettore = embedder.incorpora([f"{prefisso} {cercata}" if prefisso else cercata])[0]
    with connessione(config.qdrant_url):
        verifica_modello(
            client, config.collezione, embedder.modello, len(vettore), impostazioni_indice(config)
        )
        if solo_dosi:
            verifica_campo_dosi(client, config.collezione)
        risposta = client.query_points(
            config.collezione, query=vettore, query_filter=filtro, limit=k, with_payload=True
        )
    risultati = [
        Risultato(
            posizione=i, score=p.score, ricetta=p.payload["ricetta"], titolo=p.payload["titolo"],
            capitolo=p.payload["capitolo"], posizione_chunk=p.payload["posizione"],
            testo=p.payload["testo"], contiene_dosi=p.payload.get("contiene_dosi"),
        )
        for i, p in enumerate(risposta.points, start=1)
    ]
    return EsitoRicerca(
        risultati=risultati, k=k, capitolo=canonico, nota=nota, domanda_cercata=cercata
    )


def verifica_campo_dosi(client, nome: str) -> None:
    """Il filtro per dosi ha senso solo se tutti i punti hanno il campo (§22.2)."""
    senza = client.count(
        nome,
        count_filter=models.Filter(
            must=[models.IsEmptyCondition(is_empty=models.PayloadField(key="contiene_dosi"))]
        ),
        exact=True,
    ).count
    if senza:
        raise ErroreRag(
            f"{senza} punti della collezione {nome!r} non hanno il campo contiene_dosi: "
            f"esegui prima python -m rag.metadati"
        )


def crea_riscrittore(config: ConfigRag) -> Riscrittore | None:
    """Il riscrittore di LM Studio se RICERCA_RISCRITTURA=si, altrimenti None."""
    if not config.riscrittura:
        return None
    return RiscrittoreLMStudio(config.lm_base_url, config.modello_riscrittura)


def main(argv: list[str] | None = None) -> int:
    usa_utf8()
    parser = argparse.ArgumentParser(prog="python -m rag.ricerca", description="Ricerca nelle ricette.")
    parser.add_argument("domanda")
    parser.add_argument("--k", type=int, default=K_PREDEFINITO)
    parser.add_argument("--capitolo")
    parser.add_argument(
        "--solo-dosi", action="store_true", help="cerca solo tra i chunk con un elenco di ingredienti"
    )
    args = parser.parse_args(argv)
    try:
        config = carica_config_rag()
        embedder = EmbedderLMStudio(config.lm_base_url, config.embedding_model)
        esito = cerca(
            args.domanda, crea_client(config.qdrant_url), embedder, config, args.k, args.capitolo,
            riscrittore=crea_riscrittore(config), solo_dosi=args.solo_dosi,
        )
    except ErroreRag as errore:
        print(f"Errore: {errore}", file=sys.stderr)
        return 1
    if esito.domanda_cercata and esito.domanda_cercata != args.domanda:
        print(f"Domanda cercata: {esito.domanda_cercata}\n")
    for r in esito.risultati:
        print(f"{r.posizione}. score {r.score:.3f} — Ricetta {r.ricetta} — {r.titolo}")
        dosi = ", con elenco di dosi" if r.contiene_dosi else ""
        print(f"   Capitolo: {r.capitolo} (chunk {r.posizione_chunk}{dosi})")
        print(f"   {r.testo}\n")
    if not esito.risultati:
        print("Nessun risultato.")
    if esito.nota:
        print(f"Nota: {esito.nota}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
