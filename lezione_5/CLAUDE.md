# Assistente del laboratorio

Progetto del corso «Deep Learning e LLM: costruire chatbot e agenti».
La cartella del progetto è `lezione_4/`. Specifica in `specs.md`, piano in
`implementation_plan.md` (copie in `docs/superpowers/`); configurazione, avvio e diagnosi nel
`README.md`.

## Struttura
- `assistente/`: `config` (variabili d'ambiente), `log` (stderr), `orologio` (strumento),
  `strumenti` (esecuzione delle chiamate), `modello` (client LM Studio), `grafo` (LangGraph),
  `sessione` (cronologia e prompt di sistema), `terminale` (chat, `python -m assistente`).
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
- si avvia anche con Docker Compose.

## Confini
- Implementare solo i requisiti concordati. Altri strumenti, MCP, workflow e RAG arriveranno
  nelle lezioni successive: non anticiparli.
- Niente interfacce grafiche, servizi cloud o framework non concordati.
- Lavorare solo dentro `lezione_4/`. La repository contiene altre lezioni:
  non leggerle per copiarne il codice e non modificarle.
- Lavorare nel branch corrente; nessun branch o worktree nuovo se non richiesto.

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
- Salvare specifica e piano in `lezione_4/docs/superpowers/`.
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
- Push soltanto su mia richiesta.

## Documentazione
- Tenere aggiornato il README con configurazione, avvio, test e diagnosi, riportando solo
  comandi verificati.
- Aggiornare questo file quando cambiano convenzioni stabili (struttura, comandi di test,
  regole di lavoro), non per annotare l'avanzamento.
