"""Campo contiene_dosi: riconoscimento e aggiornamento dei punti esistenti (specs.md §22.2).

python -m rag.metadati aggiunge il campo ai punti di QDRANT_COLLECTION leggendo il testo dal
payload: nessun embedding ricalcolato, nessuna chiamata a LM Studio.
"""

import re
import sys
from dataclasses import dataclass

from rag.config import carica_config_rag
from rag.errori import ErroreRag, usa_utf8
from rag.indice import ErroreCollezioneAssente, conta_punti, connessione, crea_client, crea_indici

CAMPO = "contiene_dosi"

# Riga di elenco: ingrediente, virgola, poi una quantità. Es. «Farina, grammi 150.»,
# «Lardone, circa grammi 20.», «Magro di manzo nella coscia, senz'osso, grammi 500».
_QUANTITA = (
    r"(?:grammi|decilitri|centilitri|litri|chilogrammi|ettogrammi|"
    r"mezzo|mezza|un|uno|una|due|tre|quattro|cinque|sei|sette|otto|dieci|quanto)\b"
    r"|gr\.|n\.|q\.|\d"
)
# La riga intera è corta (al più 90 caratteri): una frase di prosa con una virgola («Fate un
# battuto con due spicchi d'aglio, un pizzico di…») non è un elenco.
_RIGA_DOSE = re.compile(
    rf"^(?=[^\n]{{1,90}}$)[^\n,]{{1,60}},[^\n]*?(?<![^\s,;(])(?:{_QUANTITA})",
    re.MULTILINE | re.IGNORECASE,
)
MINIMO_RIGHE = 2


def contiene_dosi(testo: str) -> bool:
    """Vero se il testo ha almeno due righe in forma di elenco di ingredienti con la quantità."""
    return len(_RIGA_DOSE.findall(testo)) >= MINIMO_RIGHE


@dataclass(frozen=True)
class EsitoMetadati:
    punti: int
    vero: int
    falso: int


def aggiorna_metadati(client, nome: str) -> EsitoMetadati:
    """Scrive contiene_dosi in ogni punto dal testo del payload; vettori invariati, rieseguibile."""
    if not client.collection_exists(nome):
        raise ErroreCollezioneAssente(
            f"la collezione {nome!r} non esiste: esegui prima python -m rag.ingestion"
        )
    gruppi: dict[bool, list] = {True: [], False: []}
    offset = None
    while True:
        punti, offset = client.scroll(
            nome, limit=1000, offset=offset, with_payload=["testo"], with_vectors=False
        )
        for p in punti:
            gruppi[contiene_dosi((p.payload or {}).get("testo", ""))].append(p.id)
        if offset is None:
            break
    for valore, ids in gruppi.items():
        for i in range(0, len(ids), 1000):
            client.set_payload(nome, payload={CAMPO: valore}, points=ids[i : i + 1000])
    crea_indici(client, nome)
    return EsitoMetadati(
        punti=conta_punti(client, nome), vero=len(gruppi[True]), falso=len(gruppi[False])
    )


def main(argv: list[str] | None = None) -> int:
    usa_utf8()
    try:
        config = carica_config_rag()
        with connessione(config.qdrant_url):
            esito = aggiorna_metadati(crea_client(config.qdrant_url), config.collezione)
    except ErroreRag as errore:
        print(f"Errore: {errore}", file=sys.stderr)
        return 1
    print(
        f"Collezione: {config.collezione}\n"
        f"Punti: {esito.punti} (contiene_dosi vero: {esito.vero}, falso: {esito.falso})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
