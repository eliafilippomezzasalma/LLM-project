# Assistente del laboratorio

Progetto del corso «Deep Learning e LLM: costruire chatbot e agenti».
La cartella del progetto è `lezione_4/`. Specifica in `specs.md`, piano in
`implementation_plan.md` (copie in `docs/superpowers/`); configurazione, avvio e diagnosi nel
`README.md`.

## Struttura
- `assistente/`: `config` (variabili d'ambiente), `log` (stderr), `orologio` (strumento),
  `strumenti` (esecuzione delle chiamate), `modello` (client LM Studio), `router` (router d'ambito), `revisore` (revisore della risposta), `riassunto` (riassunto della cronologia), `grafo` (LangGraph),
  `sessione` (cronologia e prompt di sistema), `terminale` (chat, `python -m assistente`),
  `mcp_remoto` (ponte sincrono verso server MCP via stdio), `nota` (nota non normativa dei risultati di
  `compute_deadline`, data una sola volta per chat).
- `scadenze.py` + `festivita.json`: server MCP di giorni e scadenze (sei strumenti, festività solo dal file);
  specifica in `specs.md` §15.
- `calcolatrice.py`: server MCP della calcolatrice sicura (strumento `calculate`, senza `eval`);
  specifica in `specs.md` §14, piano in `docs/superpowers/plans/` (2026-11-03).
- `convertitore.py`: server MCP del convertitore di unità (strumento `convert_units`);
  specifica in `specs.md` §13, piano in `docs/superpowers/plans/` (2026-11-02).
- `rag/`: RAG sul ricettario dell'Artusi (`specs.md` §20), moduli: `config` (configurazione da ambiente), `errori` (errore base e UTF-8
  del terminale), `corpus` (lettura e controllo del ricettario), `chunking` (divisione in chunk),
  `embedding` (vettori da LM Studio), `indice` (collezione Qdrant), `ingestion` (indicizzazione),
  `ricerca` (ricerca per similarità), `riscrittura` (riscrittura della domanda, §21),
  `metadati` (campo `contiene_dosi` sui punti esistenti, §22),
  `valutazione` (tabella con fonte attesa) e
  `domande_valutazione.json` (le domande); si eseguono con `python -m rag.ingestion`, `rag.ricerca`,
  `rag.valutazione`.
- `tests/`: test automatici con modello finto (`finti.py`); `test_reale.py` per LM Studio.
- `Dockerfile`, `.dockerignore`, `compose.yaml`: immagine solo runtime, LM Studio sull'host.
- Dipendenze: `requirements.txt` (runtime, versioni fissate), `requirements-dev.txt` (+ pytest).

## Comandi (PowerShell, da `lezione_4/`)
- Test automatici: `.\venv\Scripts\python.exe -m pytest -q`
- Prova reale: `$env:RUN_REAL_TESTS="1"; .\venv\Scripts\python.exe -m pytest -m reale -v -s`
- Chat: `.\venv\Scripts\python.exe -m assistente`
- Docker: `docker compose build`, poi `docker compose run --rm assistente`

## Obiettivo
Un'applicazione da terminale in Python che conversa con un modello locale e:
- organizza il flusso in un grafo LangGraph esplicito (stato, nodi, instradamento riconoscibili);
- usa un modello servito da LM Studio, che resta sul computer host;
- conserva la cronologia della conversazione per la durata della sessione (nessuna persistenza);
- offre uno strumento orologio con fuso orario esplicito, richiesto dal modello tramite tool calling
  ed eseguito davvero dal programma;
- offre un convertitore di unità tramite un server MCP separato (`convertitore.py`, stdio),
  con unità come elenco chiuso nello schema e validazione Pydantic con errori in italiano;
- offre una calcolatrice sicura tramite un secondo server MCP (`calcolatrice.py`, stdio): espressioni
  aritmetiche senza `eval`, con rifiuti espliciti in italiano;
- offre giorni e scadenze tramite un terzo server MCP (`scadenze.py`, stdio): scadenze, giorni lavorativi,
  differenze tra date, festività italiane da `festivita.json`, date solo `AAAA-MM-GG`, con rifiuti in italiano;
- classifica ogni domanda con un router d'ambito prima dell'agente: le domande fuori ambito ricevono
  una risposta fissa senza chiamare l'agente (`specs.md` §17);
- fa rivedere la risposta finale da un revisore, che la rimanda all'agente se è parziale o con valori non
  ricavati dagli strumenti (`specs.md` §18);
- riassume la cronologia lunga: oltre una soglia i turni vecchi diventano un riassunto nel prompt di
  sistema, restano gli ultimi turni interi (`specs.md` §19);
- indicizza il ricettario dell'Artusi in Qdrant e lo interroga per significato, con valutazione della
  ricerca (RAG, `specs.md` §20);
- si avvia anche con Docker Compose.

## Confini
- Implementare solo i requisiti concordati. Le nuove funzionalità si aggiungono una alla volta,
  ciascuna con specifica e piano approvati; i workflow non vanno anticipati.
- Niente interfacce grafiche, servizi cloud o framework non concordati.
- Lavorare solo dentro `lezione_4/`. La repository contiene altre lezioni:
  non leggerle per copiarne il codice e non modificarle.
- Le nuove funzionalità si sviluppano nel branch `feature/nuove-funzionalita`; il RAG nel branch
  `RAG`; nessun altro branch o worktree se non richiesto.

## RAG: regole stabili
- L'ingestion è uno script separato (`python -m rag.ingestion`), non uno strumento dell'agente.
- Il modello di embedding viene dalla configurazione (`EMBEDDING_MODEL`), mai fissato nel codice.
- Qdrant gira con Docker Compose e un volume persistente (`qdrant_dati`); versione dell'immagine fissata.
- I dati scaricati (`dati/`, compreso il testo del ricettario) e il `.env` restano fuori da Git.
- Test con embedder finto e Qdrant in memoria, a servizi spenti (né Qdrant né LM Studio).
- La collezione registra modello, prefissi e titolo nel testo: la ricerca si ferma se la
  configurazione è diversa; l'ingestion ricalcola i vettori nella stessa collezione (cambio di
  modello bloccato). Più configurazioni a confronto = una `QDRANT_COLLECTION` ciascuna (§21, §22).
- `contiene_dosi` si aggiorna sui punti esistenti con `python -m rag.metadati`, senza ricalcolare
  gli embedding (§22).
- Le domande di valutazione si fissano prima di misurare e non si cambiano dopo aver visto i risultati.
- Comandi (PowerShell, da `lezione_4/`): `docker compose up -d qdrant`, poi
  `.\venv\Scripts\python.exe -m rag.ingestion`, `-m rag.ricerca "domanda"`, `-m rag.valutazione`,
  `-m rag.metadati`.

## Scelte tecniche
- Python, codice sincrono e moduli piccoli, con una separazione semplice tra
  grafo, collegamento al modello, strumenti e interfaccia da terminale.
- LM Studio sull'host, raggiunto tramite la sua API compatibile con OpenAI.
- Indirizzo del server e identificativo del modello solo da variabili d'ambiente.
  L'identificativo è quello restituito dal server (`GET /v1/models`), mai inventato.
- Un file di configurazione di esempio senza credenziali; il file reale resta fuori da Git.
- Docker Compose per l'applicazione; LM Studio non va containerizzato.
- Dipendenze motivate, concordate e con versioni fissate.
- Comandi documentati anche per PowerShell (Windows).

## Metodo: Superpowers
- Usare le skill di Superpowers per brainstorming, specifica, piano, implementazione e verifica.
- Non scrivere codice prima che io abbia approvato la specifica e poi il piano.
- Specifica unica e cumulativa: `specs.md`. Ogni nuovo strumento vi aggiunge una propria
  sezione (dalla 13 in poi), niente documenti di specifica separati per strumento.
- Salvare i piani in `lezione_4/docs/superpowers/plans/`.
- Procedere per incrementi piccoli, ciascuno verificato prima del commit.

## Test e verifiche
- Test automatici ripetibili che non richiedono un modello attivo (grafo, cronologia,
  instradamento, strumento con istante controllato).
- Prove reali con LM Studio e con Docker tenute separate e attivate esplicitamente.
- Una risposta simulata non dimostra che il modello locale sappia usare lo strumento.
- Nel resoconto indicare che cosa è stato eseguito, con quale esito, e che cosa resta da provare.

## Git
- Conventional Commits in italiano, per esempio `feat(grafo): ...`, `test(strumenti): ...`,
  `docs: ...`.
- Prima di ogni commit: `git status`, controllo del diff, staging selettivo dei soli file pertinenti.
- Mai versionare credenziali, `.env`, ambienti virtuali, cache o pesi dei modelli.
- Commit e push soltanto su mia richiesta.

## Documentazione
- Tenere aggiornato il README con configurazione, avvio, test e diagnosi, riportando solo
  comandi verificati.
- Aggiornare questo file quando cambiano convenzioni stabili (struttura, comandi di test,
  regole di lavoro), non per annotare l'avanzamento.
