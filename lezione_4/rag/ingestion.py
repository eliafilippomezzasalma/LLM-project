"""Ingestion del ricettario in Qdrant: python -m rag.ingestion (specs.md §20.6)."""

import logging
import sys
import time
from dataclasses import dataclass

from qdrant_client import models

from assistente.log import configura_log
from rag.chunking import dividi_tutte, contenuto_da_incorporare
from rag.config import ConfigRag, carica_config_rag
from rag.corpus import carica_corpus
from rag.embedding import Embedder, EmbedderLMStudio, ErroreEmbedding
from rag.errori import ErroreRag, usa_utf8
from rag.indice import (
    chiudi_ingestion, conta_punti, connessione, crea_client, impostazioni_indice, prepara_collezione,
)
from rag.metadati import contiene_dosi

log = logging.getLogger(__name__)

FONTE = "Pellegrino Artusi, La scienza in cucina e l'arte di mangiar bene"
LOTTO = 32


@dataclass
class EsitoIngestion:
    ricette: int
    chunk: int
    punti_prima: int
    punti_dopo: int
    rimossi: int
    modello: str
    dimensione: int
    secondi: float
    caratteri_min: int
    caratteri_medi: int
    caratteri_max: int


def _punto(chunk, vettore: list[float]) -> models.PointStruct:
    return models.PointStruct(
        id=chunk.id_punto,
        vector=vettore,
        payload={
            "ricetta": chunk.ricetta,
            "titolo": chunk.titolo,
            "capitolo": chunk.capitolo,
            "posizione": chunk.posizione,
            "testo": chunk.testo,
            "fonte": FONTE,
            "documento_id": chunk.documento_id,
            "contiene_dosi": contiene_dosi(chunk.testo),
        },
    )


def _rimuovi_obsoleti(client, nome: str, scritti: set[str]) -> int:
    """Cancella i punti della collezione il cui ID non è stato scritto in questa esecuzione."""
    obsoleti: list = []
    offset = None
    while True:
        punti, offset = client.scroll(
            nome, limit=1000, offset=offset, with_payload=False, with_vectors=False
        )
        obsoleti.extend(p.id for p in punti if str(p.id) not in scritti)
        if offset is None:
            break
    if obsoleti:
        client.delete(nome, points_selector=models.PointIdsList(points=obsoleti))
    return len(obsoleti)


def esegui_ingestion(config: ConfigRag, embedder: Embedder, client, attese: int = 790) -> EsitoIngestion:
    """Indicizza il corpus: ripetibile (ID stabili, upsert) e con rimozione dei punti obsoleti."""
    inizio = time.monotonic()
    ricette = carica_corpus(config.corpus, attese)  # si ferma qui se il corpus è incompleto
    log.info("Corpus: %d ricette", len(ricette))
    chunk = dividi_tutte(ricette, config.strategia, config.dimensione, config.overlap)
    lunghezze = [len(c.testo) for c in chunk]
    minimo, massimo = min(lunghezze), max(lunghezze)
    medio = round(sum(lunghezze) / len(lunghezze))
    log.info("Chunk: %d (caratteri min/medi/max: %d/%d/%d)", len(chunk), minimo, medio, massimo)

    def testi(lotto):
        return [contenuto_da_incorporare(c, config.titolo_nel_testo, config.prefisso_documento) for c in lotto]

    primo = embedder.incorpora(testi(chunk[:LOTTO]))
    dimensione = len(primo[0])
    log.info("Modello di embedding: %s, dimensione dei vettori: %d", embedder.modello, dimensione)

    with connessione(config.qdrant_url):
        prepara_collezione(
            client, config.collezione, embedder.modello, dimensione, impostazioni_indice(config)
        )
        punti_prima = conta_punti(client, config.collezione)
        log.info("Punti nella collezione prima: %d", punti_prima)
        for i in range(0, len(chunk), LOTTO):
            lotto = chunk[i : i + LOTTO]
            vettori = primo if i == 0 else embedder.incorpora(testi(lotto))
            if len(vettori) != len(lotto):
                raise ErroreEmbedding(
                    f"LM Studio ha restituito {len(vettori)} vettori per {len(lotto)} testi"
                )
            client.upsert(config.collezione, points=[_punto(c, v) for c, v in zip(lotto, vettori)])
            log.info("Scritti %d/%d punti", i + len(lotto), len(chunk))
        rimossi = _rimuovi_obsoleti(client, config.collezione, {c.id_punto for c in chunk})
        log.info("Punti obsoleti rimossi: %d", rimossi)
        chiudi_ingestion(client, config.collezione, impostazioni_indice(config))
        punti_dopo = conta_punti(client, config.collezione)
    secondi = time.monotonic() - inizio
    log.info("Punti nella collezione dopo: %d (%.1f s)", punti_dopo, secondi)
    return EsitoIngestion(
        ricette=len(ricette), chunk=len(chunk), punti_prima=punti_prima, punti_dopo=punti_dopo,
        rimossi=rimossi, modello=embedder.modello, dimensione=dimensione, secondi=secondi,
        caratteri_min=minimo, caratteri_medi=medio, caratteri_max=massimo,
    )


def main(argv: list[str] | None = None) -> int:
    usa_utf8()
    configura_log("INFO")
    try:
        config = carica_config_rag()
        embedder = EmbedderLMStudio(config.lm_base_url, config.embedding_model)
        esito = esegui_ingestion(config, embedder, crea_client(config.qdrant_url))
    except ErroreRag as errore:
        print(f"Errore: {errore}", file=sys.stderr)
        return 1
    print(
        f"Ricette: {esito.ricette}\n"
        f"Chunk: {esito.chunk} (caratteri min/medi/max: "
        f"{esito.caratteri_min}/{esito.caratteri_medi}/{esito.caratteri_max})\n"
        f"Modello: {esito.modello} (dimensione {esito.dimensione})\n"
        f"Punti prima: {esito.punti_prima}, dopo: {esito.punti_dopo}, rimossi: {esito.rimossi}\n"
        f"Tempo: {esito.secondi:.1f} s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
