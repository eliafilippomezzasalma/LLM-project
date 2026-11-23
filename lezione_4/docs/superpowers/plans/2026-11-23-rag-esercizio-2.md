# RAG parte 3: Esercizio 2 (modifica A e chiusura della B) — piano di implementazione

> Eseguito in linea (superpowers:executing-plans) su richiesta dell'utente di procedere in autonomia.

**Obiettivo:** campo `contiene_dosi` con filtro e aggiornamento dei punti esistenti senza nuovi
embedding (A); ingestion che ricalcola i vettori nella stessa collezione quando cambiano prefissi
o titolo (B).

**Spec:** `specs.md` §22 (si appoggia a §20 e §21).

## Vincoli globali
- Test a servizi spenti; nomi dei modelli solo da configurazione; nessun commit senza ordine.
- Cambio di modello o dimensione sempre bloccato.

## Task 1: riconoscimento delle dosi e comando `rag.metadati`
- `rag/metadati.py`: `contiene_dosi(testo) -> bool` (almeno due righe «ingrediente, quantità»),
  `aggiorna_metadati(client, nome) -> EsitoMetadati(vero, falso, punti)` con scroll del payload,
  `set_payload` a gruppi e indice booleano; `main`.
- Test: elenco vero, dosi nel discorso, una sola riga, nessuna dose; aggiornamento senza
  embedder, vettori identici, rieseguibile, punti invariati.

## Task 2: ingestion (campo e modifica B)
- Payload con `contiene_dosi`; indice booleano alla creazione.
- `rag/indice.py`: `inizia_ingestion(client, nome, modello, dimensione, impostazioni)` crea o
  verifica il solo modello e segna `ingestion_incompleta`; `chiudi_ingestion(client, nome,
  impostazioni)` registra le impostazioni e toglie il segno (metadati letti e riscritti interi).
- `verifica_modello` (ricerca) si ferma con `ErroreIngestionIncompleta` se il segno c'è.
- Test: ricalcolo con titolo sulla stessa collezione (punti uguali, impostazioni aggiornate),
  modello diverso ancora bloccato, ricerca bloccata a ingestion incompleta.

## Task 3: filtro nella ricerca e nella valutazione
- `cerca(..., solo_dosi=False)`: condizione `contiene_dosi = true` in `must` con il capitolo;
  collezione con punti senza il campo → errore che indica `python -m rag.metadati`.
- `--solo-dosi` in `rag.ricerca` e `rag.valutazione`.
- Test: tutti i risultati con il campo vero e al più k; combinato con il capitolo; errore senza
  campo.

## Task 4: misure (controllore)
- `ricette_b`: ingestion di partenza, poi ingestion con `INDICE_CON_TITOLO=si` (punti uguali),
  valutazione k 5 e 10.
- `rag.metadati` su `ricette`, `ricette_prefissi`, `ricette_titolo`, `ricette_bge`, `ricette_b`.
- Valutazione su `ricette` con e senza `--solo-dosi`; ricerca d'esempio con capitolo e dosi.

## Task 5: documentazione
`docs/retrieval.md` (sezione Esercizio 2), README (comando e opzione, diagnosi), CLAUDE.md,
stato della §22, suite completa.
