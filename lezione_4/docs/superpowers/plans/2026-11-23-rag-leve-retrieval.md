# RAG parte 2: leve del retrieval — piano di implementazione

> Eseguito in linea (superpowers:executing-plans) su richiesta dell'utente di procedere in autonomia.

**Obiettivo:** misurare quattro leve del retrieval una alla volta (`specs.md` §21) e tenere solo
quelle che migliorano.

**Architettura:** tre opzioni nuove in `ConfigRag` (prefissi, titolo nel testo, riscrittura), un
testo da incorporare calcolato in un solo punto, metadati di indicizzazione nella collezione con
controllo di coerenza, un modulo `rag/riscrittura.py`. Ogni configurazione usa una propria
`QDRANT_COLLECTION`, scelta con le variabili d'ambiente al momento del comando.

**Spec:** `specs.md` §21 (si appoggia alla §20).

## Vincoli globali
- Predefiniti = comportamento della §20: la collezione `ricette` resta valida senza ingestion.
- Nomi dei modelli solo da configurazione. Test a servizi spenti (embedder e riscrittore finti,
  Qdrant in memoria). Nessun commit senza ordine dell'utente.

## Task 1: configurazione
- `rag/config.py`: campi `prefisso_documento: str = ""`, `prefisso_domanda: str = ""`,
  `titolo_nel_testo: bool = False`, `riscrittura: bool = False`, `modello_riscrittura: str = ""`;
  variabili della §21.4; `si`/`no` (anche `true`/`false`/`1`/`0`), altro → errore;
  `RISCRITTURA_MODEL` obbligatoria solo con `RICERCA_RISCRITTURA=si`.
- Test in `tests/test_rag_config.py`: predefiniti, valori validi, booleano non valido, riscrittura
  senza modello.

## Task 2: testo indicizzato e domanda con prefisso
- `rag/chunking.py`: `contenuto_da_incorporare(chunk, titolo_nel_testo, prefisso) -> str`
  («titolo — capitolo», riga vuota, testo; prefisso + spazio davanti se non vuoto).
- `rag/ricerca.py`: la domanda riceve `prefisso_domanda`.
- `rag/ingestion.py`: incorpora `contenuto_da_incorporare(...)`; payload `testo` invariato.
- Test: testo con e senza titolo/prefisso; il payload resta il chunk; l'embedder finto riceve il
  prefisso della domanda.

## Task 3: metadati di indicizzazione
- `rag/indice.py`: `prepara_collezione` e `verifica_modello` ricevono le impostazioni
  (`prefisso_documento`, `prefisso_domanda`, `titolo_nel_testo`); creazione → metadati; collezione
  esistente con valori diversi → `ErroreIndiceDiverso` con valori registrati e correnti; chiavi
  assenti = valori della §20.
- Test: registrazione, blocco in ingestion e in ricerca, collezione senza chiavi accettata con i
  predefiniti.

## Task 4: riscrittura della domanda
- `rag/riscrittura.py`: `Riscrittore` (protocollo `riscrivi(domanda) -> str`),
  `RiscrittoreLMStudio(base_url, modello, client=None)` con temperatura 0 e
  `extra_body={"reasoning_effort": "none"}`, pulizia `<think>` e prima riga, `ErroreRiscrittura`.
- `rag/ricerca.py`: `cerca(..., riscrittore=None)`; testo cercato = domanda + «\n» + riscrittura;
  `EsitoRicerca.domanda_cercata`; `main` lo stampa se diverso dalla domanda.
- `rag/valutazione.py`: con riscrittura attiva elenca le riscritture sotto la tabella; riepilogo
  separato per origine (aula / proprie).
- Test con client finto: pulizia, riscrittura vuota, errori di connessione e di modello, testo
  cercato.

## Task 5: misure (controllore)
Per ogni configurazione: ingestion nella sua collezione (punti = 1106), `rag.valutazione --k 5` e
`--k 10`, output salvati nel registro. Ordine: partenza (`ricette`), +prefissi
(`ricette_prefissi`), +titolo (`ricette_titolo`), +riscrittura, bge-m3 (`ricette_bge`).

## Task 6: documentazione
`docs/retrieval.md` (confronto e commento), README (variabili nuove), `.env.example`, stato della
§21, suite completa a servizi spenti.
