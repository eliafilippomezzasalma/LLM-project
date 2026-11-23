"""Collezione Qdrant del RAG: creazione, modello registrato, conteggio (specs.md §20.5)."""

import warnings
from collections.abc import Iterator
from contextlib import contextmanager

import httpx
from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from rag.errori import ErroreRag


class ErroreQdrant(ErroreRag):
    """Qdrant non raggiungibile."""


class ErroreCollezioneAssente(ErroreRag):
    """La collezione non esiste: va creata con l'ingestion."""


class ErroreModelloDiverso(ErroreRag):
    """La collezione è stata creata con un altro modello di embedding o un'altra dimensione."""


class ErroreIndiceDiverso(ErroreRag):
    """La collezione è stata indicizzata con altri prefissi o un'altra scelta sul titolo (§21.5)."""


class ErroreIngestionIncompleta(ErroreRag):
    """Un'ingestion si è interrotta: la collezione può avere vettori calcolati in modi diversi."""


# Valori di una collezione della §20, creata prima che queste chiavi esistessero.
IMPOSTAZIONI_PREDEFINITE = {"prefisso_documento": "", "prefisso_domanda": "", "titolo_nel_testo": False}


def impostazioni_indice(config) -> dict:
    """Le impostazioni che decidono come sono fatti i vettori, da registrare nella collezione."""
    return {
        "prefisso_documento": config.prefisso_documento,
        "prefisso_domanda": config.prefisso_domanda,
        "titolo_nel_testo": config.titolo_nel_testo,
    }


def crea_client(url: str) -> QdrantClient:
    """Crea il client; non si connette finché non serve (gli errori di rete arrivano alla prima chiamata)."""
    return QdrantClient(url=url, timeout=60, check_compatibility=False)


@contextmanager
def connessione(url: str) -> Iterator[None]:
    """Traduce gli errori di connessione del client in ErroreQdrant con il rimedio."""
    try:
        yield
    except (ResponseHandlingException, httpx.TransportError) as e:
        raise ErroreQdrant(
            f"Qdrant non raggiungibile su {url}: docker compose up -d qdrant e controlla QDRANT_URL"
        ) from e
    except UnexpectedResponse as e:
        raise ErroreQdrant(
            f"Qdrant ha risposto con un errore {e.status_code} su {url}: "
            f"controlla QDRANT_URL e che Qdrant sia avviato"
        ) from e


def _metadati(client, nome: str) -> dict:
    return client.get_collection(nome).config.metadata or {}


def verifica_modello(
    client, nome: str, modello: str, dimensione: int, impostazioni: dict | None = None
) -> None:
    """Si ferma se la collezione manca o è stata creata con un altro modello o un'altra dimensione."""
    if not client.collection_exists(nome):
        raise ErroreCollezioneAssente(
            f"la collezione {nome!r} non esiste: esegui prima python -m rag.ingestion"
        )
    meta = _metadati(client, nome)
    registrato = meta.get("modello_embedding", "sconosciuto")
    dim_registrata = meta.get("dimensione")
    if registrato != modello or dim_registrata != dimensione:
        raise ErroreModelloDiverso(
            f"la collezione {nome!r} è stata creata con il modello {registrato} "
            f"(dimensione {dim_registrata}), ma ora il modello è {modello} (dimensione {dimensione}): "
            f"cancella la collezione e riesegui python -m rag.ingestion, oppure usa un'altra QDRANT_COLLECTION"
        )
    if impostazioni is None:
        return
    if meta.get("ingestion_incompleta"):
        raise ErroreIngestionIncompleta(
            f"l'ultima ingestion nella collezione {nome!r} non è terminata (vettori forse misti): "
            f"riesegui python -m rag.ingestion"
        )
    registrate = {k: meta.get(k, v) for k, v in IMPOSTAZIONI_PREDEFINITE.items()}
    if registrate != impostazioni:
        diverse = ", ".join(
            f"{k}: registrato {registrate[k]!r}, ora {impostazioni[k]!r}"
            for k in IMPOSTAZIONI_PREDEFINITE if registrate[k] != impostazioni[k]
        )
        raise ErroreIndiceDiverso(
            f"la collezione {nome!r} è stata indicizzata con impostazioni diverse ({diverse}): "
            f"usa un'altra QDRANT_COLLECTION oppure riporta la configurazione ai valori registrati"
        )


def crea_indici(client, nome: str) -> None:
    """Indici sul payload dei campi filtrati (capitolo, ricetta, contiene_dosi); rieseguibile."""
    with warnings.catch_warnings():
        # Il Qdrant in memoria (solo test) ignora gli indici e lo dice con un avviso: sul server vero no.
        warnings.filterwarnings("ignore", message="Payload indexes have no effect", category=UserWarning)
        client.create_payload_index(nome, "capitolo", models.PayloadSchemaType.KEYWORD)
        client.create_payload_index(nome, "ricetta", models.PayloadSchemaType.INTEGER)
        client.create_payload_index(nome, "contiene_dosi", models.PayloadSchemaType.BOOL)


def prepara_collezione(
    client, nome: str, modello: str, dimensione: int, impostazioni: dict | None = None
) -> None:
    """Inizio dell'ingestion: crea la collezione o ne verifica il solo modello, poi la segna incompleta.

    Prefissi e titolo diversi da quelli registrati non fermano l'ingestion (§22.3): i vettori si
    ricalcolano tutti nella stessa collezione e chiudi_ingestion registra le nuove impostazioni.
    """
    if client.collection_exists(nome):
        verifica_modello(client, nome, modello, dimensione)
    else:
        client.create_collection(
            nome,
            vectors_config=models.VectorParams(size=dimensione, distance=models.Distance.COSINE),
            metadata={"modello_embedding": modello, "dimensione": dimensione, **(impostazioni or {})},
        )
    crea_indici(client, nome)
    client.update_collection(nome, metadata={"ingestion_incompleta": True})


def chiudi_ingestion(client, nome: str, impostazioni: dict | None = None) -> None:
    """Fine dell'ingestion: registra le impostazioni usate e toglie il segno di incompleta."""
    client.update_collection(nome, metadata={**(impostazioni or {}), "ingestion_incompleta": False})


def conta_punti(client, nome: str) -> int:
    """Numero esatto di punti nella collezione."""
    return client.count(nome, exact=True).count
