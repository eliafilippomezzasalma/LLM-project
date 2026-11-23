# Assistente del laboratorio — Specifica

Data: 2026-10-26 (orologio), aggiornata il 2026-11-09 · Cartella: `lezione_4/`

Documento unico e cumulativo: le sezioni 1–12 descrivono l'assistente originale con l'orologio
(approvate il 2026-10-26); ogni strumento aggiunto dopo ha una propria sezione dalla 13 in poi,
che estende o sostituisce le regole precedenti dove lo dice esplicitamente (per esempio i
non-obiettivi del §3 su altri strumenti e MCP).

## 1. Intento

Un'applicazione da terminale in Python per la lezione 4 del corso «Deep Learning e LLM:
costruire chatbot e agenti». L'utente scrive domande, un modello locale servito da LM Studio
risponde, e il flusso è organizzato in un **grafo LangGraph esplicito** in cui stato, nodi e
instradamento si riconoscono a colpo d'occhio. Il modello può chiedere uno **strumento
orologio**: il programma lo esegue davvero, restituisce il risultato al modello e solo dopo
mostra la risposta finale.

Lo scopo è didattico: il codice deve essere piccolo, leggibile e servire da base per le
lezioni successive (altri strumenti, MCP, RAG), senza anticiparle. Ogni elemento (grafo,
modello, strumenti, terminale, configurazione, log) sta in un modulo distinto, così da essere
riconoscibile e modificabile da solo.

## 2. Obiettivi

- Chat interattiva da terminale con cronologia conservata **per la sola sessione**
  (alla chiusura si perde; nessuna persistenza su disco).
- Grafo LangGraph con nodi `modello` e `strumenti` e un instradamento condizionale esplicito.
- Strumento orologio con fuso orario esplicito scelto dal modello.
- Chiamate allo strumento visibili nei log.
- Limite al numero di passaggi modello→strumento per ogni domanda.
- Avvio sia locale (venv) sia con Docker Compose; LM Studio resta sull'host.
- Test automatici che non richiedono un modello attivo, più prove reali separate e
  attivabili esplicitamente.

## 3. Non obiettivi (da non anticipare)

- Altri strumenti oltre all'orologio, MCP, RAG, workflow multi-agente.
- Interfacce web o grafiche, servizi cloud.
- Persistenza della cronologia (file, database, checkpointer).
- Streaming della risposta token per token.
- Containerizzare LM Studio.
- Eseguire i test dentro Docker.

## 4. Anti-obiettivi (sarebbe un fallimento anche se "funziona")

- Un'orchestrazione nascosta (agente prebuilt `create_react_agent`, `ToolNode`, Functional
  API) che rende invisibili nodi e instradamento.
- Un orologio "finto" in cui il modello inventa l'ora o riusa un orario vecchio senza che lo
  strumento venga eseguito.
- Identificativo del modello o indirizzo del server scritti nel codice.
- Test che passano solo con LM Studio acceso.
- Credenziali, `.env`, venv o cache versionati o copiati nell'immagine Docker.

## 5. Vincoli (dal `CLAUDE.md`)

- Python, codice **sincrono**, moduli piccoli e distinti.
- LM Studio raggiunto tramite API compatibile OpenAI.
- `LM_BASE_URL` e `LM_MODEL` solo da variabili d'ambiente; `LM_MODEL` è un id restituito da
  `GET /v1/models`, mai inventato.
- `.env.example` versionato senza credenziali; `.env` reale fuori da Git.
- Dipendenze motivate e con versioni fissate.
- Comandi documentati anche per PowerShell.
- Lavorare solo in `lezione_4/`, branch corrente, Conventional Commits in italiano,
  push solo su richiesta.

## 6. Comportamento

### 6.1 Modello

- Predefinito: **`qwen/qwen3.5-9b`** (deciso con l'utente).
- Prova preliminare del 2026-10-26 (chiamata diretta all'API di LM Studio, temperatura 0,
  strumento di prova): Qwen ha chiamato lo strumento sia per «Che ore sono a Tokyo?»
  (`Asia/Tokyo`) sia per «Che ore sono adesso?» (`Europe/Rome`), con circa 55–60 s per
  risposta. `google/gemma-4-e2b` era più veloce ma nel secondo caso non ha chiamato lo
  strumento. Entrambi restituiscono il ragionamento nel campo separato `reasoning_content`.
- Il modello resta un valore di `.env`: cambiarlo non richiede modifiche al codice.
- **Ragionamento disattivato** (deciso con l'utente il 2026-11-01, durante la prova reale):
  con il ragionamento attivo LM Studio a volte mette la risposta finale di Qwen dopo lo
  strumento in `reasoning_content`, che `langchain-openai` scarta, e la risposta arriva vuota
  (2–4 casi su 5–6). Il client invia quindi `reasoning_effort: "none"` nel corpo della
  richiesta (`extra_body`; il parametro `reasoning_effort` di `ChatOpenAI` diventerebbe
  `reasoning: {effort}`, che LM Studio ignora). Prova del 2026-11-01: 6 risposte non vuote
  su 6, strumento sempre chiamato con il fuso giusto, 12–16 s per domanda invece di 30–60 s.
  Costo: risposte meno ragionate su domande complesse, fuori dal perimetro di questa lezione.

### 6.2 Sessione da terminale

Sessione tipica (approvata):

```
Assistente del laboratorio — modello: qwen/qwen3.5-9b @ http://host.docker.internal:1234/v1
Scrivi la tua domanda. Per uscire: esci, exit, Ctrl+D o Ctrl+C.

Tu> Ciao, mi chiamo Elia
(sto pensando...)
Assistente> Ciao Elia! Come posso aiutarti?

Tu> Che ore sono a Tokyo?
(sto pensando...)
12:30:41 INFO strumenti: passo 1/3 get_current_time {"timezone": "Asia/Tokyo"} -> lunedì 26 ottobre 2026, 20:30:41 — Asia/Tokyo (UTC+09:00)
Assistente> A Tokyo sono le 20:30 di lunedì 26 ottobre 2026.

Tu> Come mi chiamo?
(sto pensando...)
Assistente> Ti chiami Elia.

Tu> esci
Ciao!
```

- All'avvio: riga di benvenuto con modello e indirizzo, e come uscire.
- Prompt `Tu> `; prima di ogni chiamata stampa `(sto pensando...)` (semplice riga, niente
  animazione), poi `Assistente> ...`.
- Uscita con `esci` / `exit`, Ctrl+D / EOF o Ctrl+C, sempre con `Ciao!` e senza traceback.
- Righe vuote ignorate.
- La cronologia (messaggio di sistema + scambi precedenti) viene passata al grafo a ogni
  domanda ed è tenuta come lista in memoria dall'interfaccia da terminale.
  *Aggiunto il 2026-11-17:* quando la cronologia supera la soglia, il nodo `riassunto` toglie i
  turni vecchi e li sostituisce con un riassunto nel prompt di sistema (vedi §19).
- Di un turno riuscito la cronologia conserva il messaggio dell'utente, le chiamate allo
  strumento con le loro risposte (`AIMessage` con tool_call e `ToolMessage`) e la risposta
  finale. *Modificato il 2026-11-13:* prima chiamate e risposte dell'orologio non venivano
  salvate, per non lasciare un orario vecchio nel contesto; ma l'orario restava comunque nella
  risposta finale e, senza esempi di chiamata, ai seguiti («e a Roma?») il modello lo copiava
  spostando il fuso a mente (prova reale: orologio chiamato 3 volte su 12 contro 10 su 12
  tenendo le chiamate, nessun orario inventato).
- Il messaggio di sistema (in italiano) dice al modello di usare **sempre** lo strumento per
  conoscere l'ora attuale, di non riutilizzare orari citati in precedenza e di non calcolare
  l'ora di un fuso partendo da un altro (aggiunto il 2026-11-01: nella prova reale, a «e a
  Roma?» dopo Tokyo, Qwen chiamava lo strumento solo 2 volte su 6 e sbagliava l'ora in 3; con
  la frase aggiunta 5 su 6. Il caso residuo è un limite del modello, non del programma).
- Il ragionamento del modello non viene mai stampato né salvato in cronologia: quello nel
  campo separato viene ignorato (registrato a DEBUG); eventuali blocchi `<think>…</think>`
  dentro il contenuto vengono rimossi per sicurezza.

### 6.3 Grafo

Si usa la **Graph API** di LangGraph (`StateGraph`), e solo questa: stato dichiarato come
classe, `add_node`, `add_edge`, `add_conditional_edges`, `compile()`. Niente
`create_react_agent`, `ToolNode`, checkpointer o Functional API.

Stato: lista di messaggi (con reducer `add_messages`) più un contatore dei passaggi-strumento
del turno corrente.

```
START → modello ──(ci sono tool_calls e passi < limite)──→ strumenti → modello
                 ├─(ci sono tool_calls e passi = limite)──→ END (limite raggiunto)
                 └─(nessuna tool_call)───────────────────→ END (risposta finale)
```

- **modello**: invia i messaggi al modello con lo strumento collegato (`bind_tools`) e
  aggiunge la risposta allo stato. *Aggiunto il 2026-11-14:* se la risposta contiene chiamate
  agli strumenti **e** del testo, il testo viene registrato a DEBUG
  (`agente: testo insieme alle chiamate, tolto: …`) e tolto dal messaggio prima di entrare nello
  stato. L'utente vede solo la risposta finale: nella prova reale il modello scriveva
  «17 × 23 = 391, 5 miglia = 8,05 km» insieme alla chiamata a `days_between` e, rivedendolo,
  nella risposta finale riportava solo i giorni a Natale (1 risposta su 10 senza gli altri
  risultati; 0 su 18 dopo la correzione).
- **strumenti**: nodo scritto a mano: per ogni `tool_call` esegue lo strumento, scrive il log
  e aggiunge un `ToolMessage`; incrementa il contatore di 1 (più tool_call nello stesso
  messaggio contano come un solo passaggio).
- **instradamento**: funzione esplicita e testabile separatamente.
- Il grafo viene costruito da una funzione che riceve il modello e l'orologio come
  dipendenze, così i test iniettano un modello finto e un istante fisso.

### 6.4 Limite dei passaggi

- Massimo **3** giri modello→strumenti per domanda (predefinito, variabile `MAX_TOOL_STEPS`).
- Se il modello chiede ancora lo strumento al limite, il grafo termina, il terminale stampa
  un avviso (es. «Limite di passaggi raggiunto, riprova riformulando la domanda»), il turno
  incompleto **non** entra in cronologia e si torna al prompt.

### 6.5 Strumento orologio

- Nome `get_current_time`, argomento obbligatorio `timezone`: nome IANA (es. `Asia/Tokyo`)
  **scelto dal modello in base alla domanda dell'utente**.
- La descrizione dello strumento suggerisce `Europe/Rome` quando l'utente non indica un luogo.
- Risultato **leggibile in italiano**, già pronto da riportare (il modello copia, non
  calcola il giorno della settimana):
  `lunedì 26 ottobre 2026, 20:30:41 — Asia/Tokyo (UTC+09:00)`.
  Nomi di giorni e mesi da tabelle nel codice, senza dipendere dal locale del sistema
  (l'immagine slim non ha il locale italiano).
- Fuso inesistente: nessuna eccezione verso l'utente; lo strumento restituisce al modello un
  messaggio d'errore con un suggerimento (vedi §6.6).
- L'istante corrente è fornito da una funzione iniettabile (istante fisso nei test).
- Usa `zoneinfo` della libreria standard più il pacchetto `tzdata` (Windows e l'immagine slim
  non hanno il database IANA).

### 6.6 Gestione dettagliata degli strumenti

**Definizione e registro**
- Lo strumento è una funzione Python in un modulo dedicato, dichiarata con `@tool` di
  LangChain: nome, descrizione e schema dell'argomento si leggono dal codice.
- Un piccolo **registro** `nome → strumento` (oggi una sola voce): il nodo `strumenti` cerca lì
  ciò che il modello chiede e la stessa lista viene passata a `bind_tools`. Il nodo del grafo
  non nomina mai l'orologio.

**Esecuzione nel nodo `strumenti`**
- Più tool_call nello stesso messaggio: eseguite in ordine, una riga di log e un `ToolMessage`
  per ciascuna, ognuno con il proprio `tool_call_id`; contano come **un** passaggio.
- Il programma non si blocca mai per uno strumento: in caso di problema il modello riceve un
  `ToolMessage` che inizia con `Errore:` e può correggersi o spiegarlo all'utente.

| Caso | Messaggio al modello | Log |
|---|---|---|
| strumento sconosciuto | `Errore: strumento 'meteo' non disponibile` | WARNING |
| argomenti mancanti o malformati (anche `invalid_tool_calls`) | `Errore: argomento 'timezone' mancante o non valido` | WARNING |
| fuso non IANA (`JST`, `Tokyo`, `UTC+9`) | `Errore: fuso orario 'JST' non valido, usa un nome IANA come 'Asia/Tokyo'` | WARNING |
| qualunque altra eccezione | `Errore: esecuzione dello strumento non riuscita` | ERROR con dettaglio |

- Un tentativo fallito conta comunque come passaggio; il limite (§6.4) impedisce cicli
  infiniti di tentativi.

### 6.7 Log

- Modulo `logging` su **stderr**, livello da `LOG_LEVEL` (predefinito `INFO`).
- Formato: `HH:MM:SS LIVELLO componente: messaggio`.
- **INFO**: solo le chiamate allo strumento — passo, nome, argomenti, risultato
  (es. `12:30:41 INFO strumenti: passo 1/3 get_current_time {"timezone": "Asia/Tokyo"} -> ...`).
  Una domanda che non usa lo strumento non produce log.
- **WARNING**: limite di passaggi raggiunto; errori di collegamento al modello.
- **DEBUG**: ogni chiamata al modello con durata ed esito (richiesta strumento / risposta
  finale), messaggi inviati, ragionamento del modello.
- Le librerie esterne (`httpx`, `httpx2`, `httpcore`, `httpcore2`, `openai`, `langchain*`,
  `langgraph`) sono portate a WARNING,
  così a INFO compaiono solo i log del progetto.

### 6.8 Errori

- LM Studio non raggiungibile, modello inesistente o timeout: messaggio chiaro su terminale
  con l'indirizzo usato, il turno non entra in cronologia, il programma resta aperto.
- Variabili obbligatorie mancanti o `MAX_TOOL_STEPS` non intero ≥ 1: errore all'avvio che
  dice quale variabile correggere.

## 7. Configurazione

`lezione_4/.env.example` (versionato); il `.env` reale sta in `lezione_4/` ed è già escluso
dal `.gitignore` della radice.

```
LM_BASE_URL=http://localhost:1234/v1
LM_MODEL=qwen/qwen3.5-9b
MAX_TOOL_STEPS=3
LOG_LEVEL=INFO
```

| Variabile | Obbligatoria | Predefinito | Note |
|---|---|---|---|
| `LM_BASE_URL` | sì | — | include `/v1` |
| `LM_MODEL` | sì | — | id da `GET /v1/models` |
| `MAX_TOOL_STEPS` | no | `3` | intero ≥ 1 |
| `LOG_LEVEL` | no | `INFO` | `DEBUG` per il dettaglio |

- In locale le variabili si leggono dal `.env` con `python-dotenv` (le variabili già presenti
  nell'ambiente hanno precedenza).
- Chiave API: LM Studio non la richiede; il client usa il segnaposto fisso `"lm-studio"`, che
  non è una credenziale.
- Timeout fisso di 300 s per chiamata al modello, non configurabile.

## 8. Dipendenze

Collegamento al modello con `langchain-openai` (`ChatOpenAI` con `base_url` verso LM Studio),
per avere `bind_tools` e i messaggi LangChain usati nativamente da LangGraph.

Dirette (versioni più recenti al 2026-10-26):

| Pacchetto | Versione | Motivo |
|---|---|---|
| `langgraph` | 1.2.17 | grafo |
| `langchain-openai` | 1.7.2 | client compatibile OpenAI per LM Studio |
| `python-dotenv` | 1.2.4 | lettura del `.env` in locale |
| `tzdata` | 2026.5 | database dei fusi per `zoneinfo` |
| `pytest` | 9.1.1 | test (solo sviluppo) |

- `requirements.txt`: dipendenze di runtime **tutte fissate**, comprese le transitive
  (generato con `pip freeze` da un venv pulito).
- `requirements-dev.txt`: `-r requirements.txt` + `pytest` fissato; usato solo in locale.

## 9. Docker

- Verificato il 2026-10-26: un container `python:3.12-slim` raggiunge LM Studio su
  `http://host.docker.internal:1234/v1` senza modificare le impostazioni di LM Studio.
- Un'unica immagine **solo per l'esecuzione**: base `python:3.12.15-slim`; installa
  `requirements.txt`, poi copia il codice; gira come utente non-root; comando predefinito:
  la chat.
- `.dockerignore`: esclude `.env`, `venv/`, cache, `tests/`, `docs/`, `requirements-dev.txt`.
  Il `.env` arriva solo a runtime.
- `compose.yaml`, servizio `assistente`: `build: .`, `env_file: .env`, `LM_BASE_URL`
  sovrascritto a `http://host.docker.internal:1234/v1`,
  `extra_hosts: host.docker.internal:host-gateway`, `stdin_open: true`, `tty: true`.
- Comandi:

```powershell
docker compose build
docker compose run --rm assistente
```

## 10. Test e verifiche

**Automatici (solo in locale, senza modello):** `pytest`
- strumento: istante fisso → testo italiano atteso per più fusi (incluso un cambio di data e
  l'ora legale/solare); fuso non valido → messaggio d'errore con suggerimento;
- nodo strumenti: più tool_call nello stesso messaggio, strumento sconosciuto, argomenti
  mancanti, eccezione generica → `ToolMessage` con `Errore:` e passaggio contato una volta;
- instradamento: con/senza `tool_calls`, al limite;
- grafo con modello finto che prima chiede l'orologio e poi risponde: sequenza
  `AIMessage` con tool_call → `ToolMessage` → risposta finale, e riga di log INFO;
- grafo con modello finto che chiede sempre lo strumento: si ferma al limite;
- cronologia: il secondo turno riceve domanda, chiamate all'orologio con le risposte e risposta finale del primo
  (aggiornato il 2026-11-13); un turno fallito o interrotto dal limite non sporca la cronologia;
- testo insieme alle chiamate: tolto dal messaggio e registrato a DEBUG; una risposta finale
  senza chiamate resta intatta (aggiunto il 2026-11-14);
- ragionamento: un contenuto con `<think>…</think>` viene ripulito;
- configurazione: variabile mancante o `MAX_TOOL_STEPS` non valido → errore chiaro.

**Reali (attivati esplicitamente):**
- test automatico con LM Studio, saltato salvo `RUN_REAL_TESTS=1` (marcatore `reale`):
  «Che ore sono a Tokyo?» produce almeno un `ToolMessage` per `Asia/Tokyo` e una risposta
  finale non vuota;
- verifica manuale guidata nel README, in locale e con `docker compose run --rm assistente`:
  domanda sull'ora, controllo della riga di log, domanda di follow-up che dimostra la
  cronologia, uscita con `esci`.

Una risposta simulata non dimostra che il modello locale sappia usare lo strumento: il
resoconto finale distingue ciò che è stato provato con mock, con LM Studio e con Docker.

## 11. Scelte prese da me (da verificare in lettura)

- Nodo strumenti scritto a mano (confermato dall'utente: ogni elemento distinto).
- Cronologia come lista in memoria nell'interfaccia; per turno salvati solo domanda e
  risposta finale.
- Messaggio di sistema che impone l'uso dello strumento per l'ora.
- Ragionamento mai mostrato né salvato; `<think>` rimosso per sicurezza.
- `Europe/Rome` suggerito quando la domanda non indica un luogo.
- Formato dei log e librerie esterne a WARNING.
- Segnaposto `"lm-studio"` come chiave API; timeout fisso di 300 s.
- Immagine `python:3.12.15-slim` con utente non-root.
- Strumento con `@tool` e registro `nome → strumento`; tabella degli errori in §6.6.
- Nomi italiani di giorni e mesi da tabelle nel codice (nessun locale di sistema).

Decisi con l'utente: modello Qwen, Graph API, tutte le versioni fissate, sessione tipica con
`(sto pensando...)`, variabili d'ambiente, immagine solo runtime con test in locale, log
opzione A, formato orario leggibile in italiano, esecuzione nella sessione corrente con un
revisore indipendente a implementazione finita.

## 12. Lasciato al builder

- Nomi esatti di moduli e funzioni, nel rispetto della separazione in moduli distinti.
- Testo esatto del messaggio di sistema, degli avvisi e degli errori, purché contengano le
  informazioni elencate.
- Struttura del README, purché copra configurazione, avvio (locale e Docker), test e
  diagnosi con comandi verificati.

## 13. Convertitore di unità (MCP) — aggiunto il 2026-11-02

Stato: implementato e verificato (commit `e70470f`). Documento di dettaglio originale, scritto
prima della regola dello `specs.md` unico: `docs/superpowers/specs/2026-11-02-convertitore-mcp-design.md`;
piano: `docs/superpowers/plans/2026-11-02-convertitore-mcp.md`.

- **Cosa**: server MCP separato `convertitore.py` (stdio, libreria `mcp` 2.3.0) con un solo
  strumento `convert_units(value, from_unit, to_unit)`. L'assistente lo avvia all'avvio
  tramite il ponte sincrono `assistente/mcp_remoto.py` (`ClientMCP`) e lo mette nella stessa
  lista dell'orologio; se non parte, la chat va avanti senza e l'intestazione lo segnala.
- **Schema e validazione**: unità come elenco chiuso (23 unità in 6 grandezze: lunghezza,
  massa, tempo, temperatura, volume, velocità) dentro un modello Pydantic che è insieme lo
  schema JSON mostrato al modello e il controllo vero; tabella chiusa di sinonimi; errori in
  italiano per unità fuori elenco, grandezze incompatibili, valore non finito, temperatura
  sotto lo zero assoluto.
- **Risultato**: testo breve (`10 km = 6.21371 mi`); errori come `Errore: ...` marcati come
  errore MCP e registrati a WARNING. Le chiamate restano nella cronologia della sessione.
- **Prompt**: usare sempre `convert_units`, mai calcoli a mente, con esempi.
- **Limite misurato**: il modello non chiama sempre lo strumento per le conversioni
  impossibili (kg → m); il test reale verifica che non inventi numeri. Misure nel README.

## 14. Calcolatrice sicura (MCP) — aggiunta il 2026-11-03

Stato: implementata (2026-11-03); piano: `docs/superpowers/plans/2026-11-03-calcolatrice-mcp.md`.

### 14.1 Intento

Seconda funzionalità aggiuntiva dell'assistente della lezione 4, dopo il convertitore di unità.
Testo del compito:

> Calcolatrice sicura. Espressioni aritmetiche senza eval: solo operazioni consentite.
> Allena il rifiuto esplicito di input non validi.

Si aggiunge un **secondo server MCP separato** (come il convertitore, scelta dell'utente) che
offre **un solo strumento**: una calcolatrice che riceve un'espressione come testo e restituisce
il risultato, oppure un errore esplicito.

A lezione l'utente vuole mostrare **entrambi i casi**: il calcolo che riesce e quello che viene
rifiutato, con il motivo del rifiuto ben visibile. Il valore didattico è:
1. **nessun `eval`**: l'espressione non viene mai eseguita come codice, ma letta da un piccolo
   analizzatore scritto a mano che riconosce solo ciò che è consentito;
2. **rifiuto esplicito**: ogni input non valido produce un messaggio chiaro in italiano che dice
   cosa non va (e, quando ha senso, dove), mai un risultato inventato.

### 14.2 Comportamento atteso (dall'utente)

- «quanto fa (3,5 + 2) * 4?» → l'assistente chiama la calcolatrice e risponde 22.
- «quanto fa 2^10?» → 1024, tramite la calcolatrice.
- «quanto fa 10 / 0?» → la calcolatrice restituisce «Errore: divisione per zero» e l'assistente
  lo spiega, **senza inventare un numero**.
- Il modello deve **usare sempre la calcolatrice** per i conti, anche quelli banali e anche
  quelli impossibili come 10 / 0. Che il modello risponda «impossibile» da solo, senza chiamare lo
  strumento, è per l'utente **un problema**, anche se la risposta è corretta.

### 14.3 Cosa è consentito (deciso dall'utente)

- Le quattro operazioni: `+`, `-`, `*`, `/`.
- L'elevamento a potenza con `^` (es. `2^3`), aggiunto dall'utente.
- Le parentesi tonde.
- I numeri interi e decimali, con **la virgola o il punto** come separatore decimale
  (`3,5` e `3.5` valgono uguale).

*Scelte mie:*
- Il segno meno (e più) davanti a un numero o a una parentesi è ammesso: `-3 + 5`, `-(2 + 1)`,
  `2^-1`.
- Spazi ammessi ovunque tra i pezzi dell'espressione, ignorati.
- `**` è accettato come sinonimo di `^` (i modelli tendono a scriverlo così); `×` e `÷` come
  sinonimi di `*` e `/`. Nessun altro simbolo.
- Regole di precedenza della matematica, non di Python: prima le parentesi, poi la potenza, poi
  il segno davanti, poi `*` e `/`, infine `+` e `-`. La potenza è associativa a destra:
  `2^3^2` = `2^(3^2)` = 512; `-2^2` = −4; `(-2)^2` = 4. `*`, `/`, `+`, `-` associativi a sinistra.

### 14.4 Come si analizza (scelta mia: niente `eval`, niente `ast`)

In Python `^` non è la potenza e ha una precedenza diversa, quindi il modulo `ast` darebbe
risultati sbagliati per `2 + 3^2`. La calcolatrice usa invece un **piccolo analizzatore scritto
a mano** (lettura a pezzi dell'espressione + discesa ricorsiva sulle regole di precedenza sopra),
in Python puro, leggibile e spiegabile a lezione.

Vincolo forte: nel codice della calcolatrice **non compaiono** `eval`, `exec`, `compile`,
`ast.literal_eval` né altro modo di eseguire il testo ricevuto. Un test lo verifica sul sorgente.

#### Aritmetica esatta (scelta mia)

A lezione `0,1 + 0,2` deve dare `0.3`, non `0.30000000000000004`. Somme, differenze, prodotti,
quozienti e potenze con esponente intero vanno quindi calcolati in modo esatto (per esempio con
`fractions.Fraction`); una potenza con esponente non intero (`2^0,5`) dà un risultato
approssimato. Lo strumento preciso è lasciato al costruttore, purché i test coprano questi casi.

### 14.5 Rifiuti espliciti

Ogni rifiuto produce un testo che inizia con `Errore:` seguito da un messaggio chiaro in
italiano; nessuno fa cadere il server né la chat. Il server marca anche il risultato come
errore nel protocollo MCP (come il convertitore), e l'assistente lo registra nel log come avviso.

Rifiuti matematici (quelli che l'utente vuole mostrare per primi):
1. **Divisione per zero**: `10 / 0`, `5 / (2 - 2)` → «divisione per zero».
2. **Zero elevato a esponente negativo**: `0^-1` → «divisione per zero» (è la stessa cosa).
3. *Scelta mia:* **`0^0`** → rifiutato come «forma indeterminata».
4. **Base negativa con esponente non intero**: `(-8)^0,5`, `(-8)^(1/3)` → *scelta mia (dopo la
   revisione):* rifiutato con un messaggio vero in ogni caso, «potenza con base negativa ed
   esponente non intero non supportata» (non «non è un numero reale», che per `(-8)^(1/3)` = −2
   sarebbe falso). Nessun calcolo di radici dispari.
5. **Risultato troppo grande**: `9^9^9`, `10^1000` → «risultato troppo grande». Il controllo va
   fatto **prima** di calcolare la potenza (stimando l'ordine di grandezza), altrimenti il server
   si bloccherebbe. *Scelta mia:* limite a 10^100 in valore assoluto, sia per i risultati
   intermedi sia per quello finale.
5b. **Risultato troppo piccolo** (*scelta mia dopo la revisione*): un risultato diverso da zero
   sotto 10^-100 in valore assoluto (`10^-1000`, `0,5^1000`, `10^-(9^9)`) → «risultato troppo
   piccolo», controllato anch'esso **prima** del calcolo. Mostrare `0` sarebbe un numero
   inventato; con frazioni esatte, senza limite il server si bloccherebbe.

Rifiuti di forma (*scelte mie*, necessarie per non accettare in silenzio input sbagliati):
6. **Espressione vuota** o fatta solo di spazi.
7. **Carattere non consentito**: lettere, nomi di funzioni, `%`, `=`, ecc. Il messaggio indica
   il carattere e la sua posizione (es. «carattere non consentito 'x' in posizione 3») e
   ricorda cosa è ammesso.
8. **Numero scritto male**: più di un separatore decimale (`3,5,2`, `1.000,5`), separatore
   senza cifre (`3,` o `,5`, *scelta mia:* rifiutati).
   *Scelta mia (dopo la revisione):* virgola e punto sono **sempre** separatori decimali, mai
   delle migliaia: `1.000` vale 1. Le espressioni le scrive il modello, che usa il punto
   decimale (`0.125`); trattare `.` seguito da tre cifre come migliaia sarebbe peggio.
9. **Espressione malformata**: operatore senza operando (`3 + * 2`, `4 /`), parentesi non chiusa
   o chiusa in più, parentesi vuote `()`, due numeri affiancati senza operatore (`2 3`,
   moltiplicazione implicita `2(3)` non ammessa). Il messaggio dice cosa manca e dove.
10. **Espressione troppo lunga**: *scelta mia:* oltre 200 caratteri, oppure parentesi annidate
    oltre 30 livelli (protegge la discesa ricorsiva).
11. **Argomento mancante o non testuale** (il modello manda un numero o niente): messaggio che
    dice che serve un'espressione scritta come testo.

Il testo degli errori deve bastare al modello per spiegare all'utente cosa è andato storto
senza ripetere il calcolo da solo.

### 14.6 Risultato restituito al modello

*Scelta mia:* testo breve con l'espressione e il risultato, ad esempio `(3,5 + 2) * 4 = 22`
(l'espressione come l'ha mandata il modello, il risultato con il **punto** decimale, come il
convertitore). Interi senza decimali (`22`, non `22.0`); decimali con al massimo una decina di
cifre significative, senza zeri finali; risultati periodici arrotondati (`1 / 3 = 0.3333333333`).
Il formato preciso è lasciato al costruttore, purché coerente e coperto dai test.

### 14.7 Come si costruisce

Struttura analoga al convertitore, per poterli confrontare a lezione:

- **Server**: `lezione_4/calcolatrice.py`, avviabile da solo (`python calcolatrice.py`),
  libreria `mcp` già presente (2.3.0), trasporto **stdio**, **un solo strumento**.
  *Scelta mia:* nome `calculate`, un argomento `expression` (stringa); la descrizione dello
  strumento elenca in inglese le operazioni ammesse e dice che anche i calcoli impossibili vanno
  mandati alla calcolatrice.
- **Logica separata dal protocollo**: analizzatore, calcolo e messaggi di errore in funzioni
  Python pure, testabili senza MCP; lo strato MCP è sottile e non contiene logica di calcolo.
- **Lato assistente**: riuso del ponte sincrono esistente `assistente/mcp_remoto.py`
  (`ClientMCP`), con una seconda istanza per la calcolatrice; servirà un
  `parametri_calcolatrice()` accanto a `parametri_convertitore()`. Il collegamento in
  `terminale.py` va generalizzato in modo che i due server siano **indipendenti**: se uno non
  parte, l'assistente parte comunque con gli altri strumenti; entrambi vengono chiusi all'uscita.
- **Intestazione della chat**: una riga «Calcolatrice (MCP): attivo / non disponibile» sotto
  quella del convertitore.
- **Grafo e registro** (`grafo.py`, `strumenti.py`) non cambiano struttura: lo strumento entra
  nella stessa lista dell'orologio e del convertitore.
- **Cronologia**: *scelta mia:* le chiamate a `calculate` restano nella cronologia della
  sessione, come quelle a `convert_units`.
- **Docker**: il `Dockerfile` copia anche `calcolatrice.py`; nessun servizio in più.
- **Nessuna dipendenza nuova.**

### 14.8 Usare sempre la calcolatrice (deciso dall'utente)

L'utente vuole che il modello usi **sempre** la calcolatrice. Scelta dell'utente sul come:
**rafforzare il prompt di sistema e misurare** quante volte la usa, come per il convertitore.
**Non** si forza la chiamata dal codice (niente `tool_choice` obbligato né riconoscimento
automatico delle espressioni nel messaggio).

Il prompt di sistema (`sessione.py`) va esteso per dire che ogni calcolo aritmetico, anche
semplice o impossibile (es. una divisione per zero), va fatto con `calculate` e mai a mente, e
che in caso di errore va riferito il messaggio senza proporre un risultato. Esempi concreti nel
prompt sono ammessi (come per il convertitore). Al costruttore il testo preciso, da affinare con
le misure.

### 14.9 Test e verifiche

Stessa impostazione della lezione 4 e del convertitore:
- **test automatici senza modello**: ogni operazione e la precedenza (inclusi `2^3^2`, `-2^2`,
  `2 + 3^2`), virgola e punto, sinonimi `**`/`×`/`÷`, aritmetica esatta (`0,1 + 0,2`), formato
  del risultato, **ogni rifiuto** dell'elenco sopra con il suo messaggio, `9^9^9` rifiutato in
  tempi brevi, assenza di `eval`/`exec`/`compile` nel sorgente; test del server MCP in-process e
  via stdio; test del collegamento nell'assistente (i due server indipendenti, l'intestazione);
- **prove reali con LM Studio** (attivate con `RUN_REAL_TESTS=1`, in `test_reale.py`):
  «(3,5 + 2) * 4» → 22 tramite lo strumento; «10 / 0» → lo strumento è stato **chiamato** e la
  risposta non contiene un numero inventato;
- **misure**: quante volte su N domande il modello usa la calcolatrice, in sessione nuova e in
  sessione lunga, sia per calcoli validi sia per quelli rifiutati (in particolare 10 / 0), come
  fatto per il convertitore; i numeri vanno riportati all'utente e il limite, se resta, scritto
  nel README;
- **quando è finito** (deciso dall'utente): il test reale «10 / 0 → strumento chiamato» resta
  **severo** (non si ammorbidisce come quello del convertitore); il prompt si ritocca per alcuni
  giri, poi ci si ferma e si riporta nel README il tasso misurato, senza una soglia minima
  bloccante;
- **regressione sugli altri strumenti** (deciso dall'utente): dopo il cambio di prompt si
  rifanno le misure di orologio e convertitore (inclusa qualche domanda mista, es. una
  conversione che non deve finire alla calcolatrice) e si confrontano con quelle nel README;
- **prova Docker**: la calcolatrice funziona anche nel container, intestazione «attivo».

### 14.10 Obiettivi

- Server MCP separato con la sola calcolatrice, senza `eval`.
- Quattro operazioni, potenza `^`, parentesi, decimali con virgola o punto.
- Rifiuti espliciti e chiari per gli errori matematici e di forma elencati sopra.
- L'assistente usa la calcolatrice tramite MCP, anche in Docker, con un tasso misurato.

### 14.11 Non-obiettivi

- Funzioni (radice, seno, logaritmo…), costanti (π, e), variabili, percentuale, modulo,
  divisione intera, confronti.
- Forzare dal codice la chiamata allo strumento.
- Unire calcolatrice e convertitore nello stesso server, o spostare l'orologio su MCP.
- Trasporto HTTP o uso da client esterni.

### 14.12 Anti-obiettivi (sarebbe un fallimento anche se «funziona»)

- Qualsiasi uso di `eval`, `exec`, `compile` o equivalenti sul testo ricevuto.
- Il modello che fa i conti a mente, o che risponde a «10 / 0» senza chiamare la calcolatrice.
- Un numero inventato per un'espressione rifiutata.
- Un input non valido accettato in silenzio o «corretto» senza dirlo.
- Un server bloccato da un'espressione come `9^9^9`, o un errore che fa cadere la chat.
- Logica di calcolo mescolata al codice del protocollo.

### 14.13 Vincoli di lavoro

- Solo in `lezione_4/`, sul branch `feature/nuove-funzionalita`.
- **Commit e push solo su richiesta esplicita dell'utente.**
- Aggiornare `CLAUDE.md` e `README.md` (struttura, avvio, test, limiti misurati).
- Comandi documentati per PowerShell.

### 14.14 Lasciato al costruttore

- Struttura interna dell'analizzatore e nomi delle funzioni.
- Come rendere esatta l'aritmetica (purché i casi di test passino).
- Testo esatto dei messaggi di errore (italiano, chiaro, con posizione dove indicato).
- Testo esatto del prompt di sistema e della descrizione dello strumento, da affinare con le
  misure.
- Come generalizzare il collegamento dei server MCP in `terminale.py`.

## 15. Giorni e scadenze (MCP) — aggiunta il 2026-11-09

Stato: implementata (2026-11-09).

### 15.1 Intento

Terza funzionalità aggiuntiva dell'assistente della lezione 4, dopo convertitore e calcolatrice.
Testo del compito:

> Giorni e scadenze. Date ISO e festività da file locale, risultato non normativo.
> Allena formati e casi limite.

Si aggiunge un **terzo server MCP separato** (*scelta mia*, per coerenza con i due precedenti)
che risponde a domande su date e scadenze: «quando scade il mio contratto d'affitto?», «che
giorno sarà fra 10 giorni lavorativi?», «il 2 giugno 2027 è festivo?». L'utente scrive in
linguaggio naturale; il modello chiama lo strumento e risponde con una frase che contiene il
risultato.

Il valore didattico è:
1. **formati**: lo strumento accetta e restituisce solo date ISO (`AAAA-MM-GG`); è il modello a
   convertire «15/03/2024» o «15 marzo 2024», e un formato sbagliato viene rifiutato in modo
   esplicito;
2. **casi limite**: fine mese, anni bisestili, scadenze che cadono di sabato, domenica o in un
   giorno festivo, date impossibili, anni non coperti dal file delle festività;
3. **risultato non normativo**: le scadenze sono indicative e non hanno valore legale, e la
   risposta lo dice.

### 15.2 Domande da supportare (decise dall'utente: tutti e quattro i gruppi)

**A. Scadenza da una data e una durata**
1. «Ho firmato l'affitto il 15/03/2024, dura 4 anni: quando scade?»
2. «Ho ricevuto la fattura il 10 ottobre, va pagata a 30 giorni: entro quando?»
3. «Il preavviso è di 6 mesi rispetto al 31/12/2026: entro che giorno devo disdire?»
   (conto **all'indietro**)
3b. «La fattura del 2026-11-09 va pagata entro 10 giorni lavorativi: entro quando?» — una
   scadenza espressa in giorni lavorativi è del **gruppo A** (deciso dall'utente dopo la
   revisione): vale la nota non normativa.

**B. Giorni lavorativi**
4. «Che giorno sarà fra 10 giorni lavorativi a partire da oggi?»
5. «Quanti giorni lavorativi ci sono tra il 1° e il 30 novembre?»

**C. Differenza tra date**
6. «Quanti giorni mancano al 25/12/2026?»
7. «Quanti giorni sono passati dal 1° gennaio al 9 novembre?»

**D. Informazioni su una data**
8. «Il 2 giugno 2027 è festivo?»
9. «Che giorno della settimana è il 15/03/2028?»
10. «Quali sono le festività di dicembre 2026?»

### 15.3 Regole del calendario

**Giorni non lavorativi** (deciso dall'utente): sabato, domenica e le festività del file locale.

**Spostamento della scadenza** (deciso dall'utente), solo per il gruppo A:
- conto **in avanti**: se la data calcolata cade in un giorno non lavorativo, si sposta al
  **primo giorno lavorativo successivo**;
- conto **all'indietro** (es. preavviso): si sposta al **giorno lavorativo precedente**, per non
  far scadere il termine in ritardo.

Quando c'è uno spostamento, la risposta indica **la data calcolata, il motivo e la data finale**
(deciso dall'utente), es.: «la data calcolata 2028-03-12 cade di domenica: la scadenza si sposta
al 2028-03-13». Il motivo nomina la festività quando è quella la causa («è il 25 aprile, Festa
della Liberazione»).

*Scelte mie (confermate dall'utente nel riepilogo):*
- I gruppi B, C e D non spostano nulla: restituiscono la data così com'è.
- **Durate del gruppo A** in giorni, giorni lavorativi, settimane, mesi o anni. I «giorni» sono
  **di calendario** («a 30 giorni» = 30 giorni di calendario, poi l'eventuale spostamento); la
  settimana vale 7 giorni; i «giorni lavorativi» si contano come nel gruppo B (partenza esclusa),
  quindi il risultato è già lavorativo e non serve spostamento.
- **Fine mese**: se il giorno non esiste nel mese di arrivo si prende l'ultimo giorno del mese:
  2025-01-31 + 1 mese = 2025-02-28; 2024-01-31 + 1 mese = 2024-02-29; 2024-02-29 + 1 anno =
  2025-02-28; 2024-02-29 + 4 anni = 2028-02-29. Lo stesso vale all'indietro
  (2026-03-31 − 1 mese = 2026-02-28).
- **«Fra N giorni lavorativi»** (gruppo B): la data di partenza non si conta; si avanza di N
  giorni lavorativi. Da venerdì 2026-11-06, 1 giorno lavorativo = lunedì 2026-11-09. Anche
  all'indietro («10 giorni lavorativi prima del…»), per simmetria con il gruppo A.
- **Giorni lavorativi tra due date** (gruppo B): si contano **entrambi gli estremi**, se
  lavorativi. Dal 2026-11-02 (lunedì) al 2026-11-06 (venerdì) = 5.
- **Differenza tra date** (gruppo C, *scelta mia dopo la revisione*): semplice differenza di
  calendario (dal 2026-11-09 al 2026-11-10 = 1). Lo strumento non sa quale data è oggi, quindi
  risponde in modo **neutro**, con le parole «dopo» / «prima» / «stesso giorno» invece di un numero
  negativo: «il 2026-12-25 viene 46 giorni dopo il 2026-11-09»; «il 2026-01-01 viene 312 giorni
  prima del 2026-11-09»; «le due date coincidono». È il modello, che sa quale data viene
  dall'orologio, a dire «mancano 46 giorni» o «sono passati 312 giorni».
- Le **quantità** (N giorni, mesi, anni) sono numeri interi da 1 in su; zero, negativi e decimali
  sono rifiutati (la direzione si esprime con un parametro, non con il segno).

### 15.4 Festività (decise dall'utente)

**Festività nazionali italiane**, da un **file locale** con le **date esplicite anno per anno**
dal **2020 al 2040** (deciso dall'utente). Ogni anno contiene:

| Data | Festività |
|---|---|
| 01-01 | Capodanno |
| 01-06 | Epifania |
| variabile | Lunedì dell'Angelo (Pasquetta) |
| 04-25 | Festa della Liberazione |
| 05-01 | Festa del Lavoro |
| 06-02 | Festa della Repubblica |
| 08-15 | Assunzione (Ferragosto) |
| 10-04 | San Francesco d'Assisi — **solo dal 2026** |
| 11-01 | Ognissanti |
| 12-08 | Immacolata Concezione |
| 12-25 | Natale |
| 12-26 | Santo Stefano |

Il 4 ottobre è festa nazionale dal 1° gennaio 2026 (legge 8 ottobre 2025, n. 151, verificata
il 2026-11-09). La domenica di Pasqua non si elenca: è comunque domenica. Le feste patronali
locali non ci sono (non sono nazionali).

*Scelte mie:*
- Il file è **dati, non codice**: `lezione_4/festivita.json` accanto al server, con un elenco
  per anno di coppie data ISO + nome in italiano. Il server non calcola la Pasqua: legge il file.
- Le date di Pasquetta nel file si ricavano una volta, alla costruzione; un test le confronta
  con un algoritmo di calcolo della Pasqua scritto **solo nel test**, così un errore di
  trascrizione viene scoperto.
- Il file viene letto e controllato all'avvio del server (anni 2020–2040 tutti presenti, date
  valide e dell'anno giusto, 11 festività per anno fino al 2025 e 12 dal 2026). Se manca o è
  rovinato il server non parte e l'intestazione della chat lo segnala come «non disponibile»,
  come per gli altri server.

**Intervallo coperto**: dal 2020-01-01 al 2040-12-31. Ogni data che lo strumento riceve, calcola
o restituisce (compresa la data spostata) deve stare in questo intervallo; altrimenti il calcolo
è **rifiutato** con un messaggio che dice qual è l'intervallo coperto. Mai un risultato fuori
intervallo calcolato ignorando le festività.

### 15.5 Formato delle date (deciso dall'utente)

- **ISO `AAAA-MM-GG`** sia tra modello e strumento, sia **nella risposta all'utente** quando la
  risposta usa gli strumenti delle scadenze (l'utente leggerà `2028-03-15`, non `15/03/2028`).
- **L'orologio resta com'è** (deciso dall'utente dopo la revisione): a «che giorno è oggi?» la
  risposta continua a essere nella forma attuale («lunedì 9 novembre 2026»). La regola ISO del
  prompt va scritta in modo da valere solo per le risposte delle scadenze; anche quando l'orologio
  serve solo a ricavare «oggi» per una scadenza, le date nella risposta sono in ISO.
- Lo strumento accetta **solo** date ISO scritte per intero (`2024-03-15`, non `2024-3-15` né
  `15/03/2024`); un formato diverso è rifiutato con un messaggio che mostra il formato atteso,
  così il modello può correggersi e riprovare.
- *Scelta mia:* accanto alla data, lo strumento indica il giorno della settimana in italiano
  (`2028-03-15 (mercoledì)`), utile per le domande del gruppo D e per spiegare gli spostamenti.

### 15.6 «Oggi» (deciso dall'utente)

Lo strumento **non conosce la data di oggi**. Quando la domanda parte da oggi («quanti giorni
mancano al…», «fra 10 giorni lavorativi»), il modello chiama **prima l'orologio**
(`get_current_time`, *scelta mia:* fuso `Europe/Rome` se l'utente non ne indica un altro), poi
passa la data allo strumento delle scadenze. È una **catena di due strumenti** nella stessa
domanda e va misurata a parte. Vantaggio: lo strumento è deterministico e facile da testare.

### 15.7 Nota non normativa (deciso dall'utente)

La nota «calcolo indicativo, non ha valore legale» compare:
- **solo per le scadenze del gruppo A**;
- **solo la prima volta** nella chat: la prima risposta del modello che contiene una scadenza la
  riporta; le scadenze successive nella stessa sessione no.

**Chi decide** (deciso dall'utente dopo la revisione): **l'assistente**, non il server. La nota
conta come «data» solo quando è **davvero arrivata all'utente**; se il turno fallisce (errore del
modello, limite di passaggi) o il modello si dimentica di riportarla, alla scadenza successiva
ricompare.

*Scelte mie sul come:*
- Il server è **senza stato**: ogni risultato riuscito del gruppo A contiene la nota, su una riga
  riconoscibile (es. una riga che inizia con `Nota:`).
- La sessione dell'assistente (`Sessione` in `sessione.py`) tiene un'indicazione «nota già data».
  Quando è vera, la riga della nota viene **tolta** dal risultato di `compute_deadline` prima che
  arrivi al modello; così il modello non la vede e non la ripete.
- Alla fine di un turno riuscito, se la risposta mostrata all'utente contiene la nota (il
  controllo cerca una frase fissa, es. «non ha valore legale», che il prompt chiede di riportare
  così com'è), l'indicazione diventa vera. Se la risposta non la contiene, resta falsa.
- **Nota garantita dal codice** (deciso dall'utente il 2026-11-09, dopo le misure): con Qwen 3.5 9B
  il modello riportava la nota solo in 0–2 scadenze su 5. Per questo, se nel turno riuscito un
  risultato di `compute_deadline` contiene la riga della nota e la risposta del modello no, la
  sessione **aggiunge in fondo alla risposta** la riga `Nota: calcolo indicativo, non ha valore
  legale.` prima di mostrarla e di salvarla in cronologia; da quel momento la nota è «data». Le
  chiamate agli strumenti restano invece decise dal modello (nessun cambiamento al §15.10).
- Un errore dello strumento non contiene la nota e non cambia nulla.
- Dove togliere la riga (nel registro degli strumenti, nell'adattatore di `ClientMCP` o nella
  sessione) è lasciato al costruttore, purché lo stato appartenga alla sessione e sia testabile
  con il modello finto.

### 15.8 Rifiuti espliciti

Come per la calcolatrice: ogni rifiuto è un testo che inizia con `Errore:` e un messaggio chiaro in
italiano, marcato come errore MCP e registrato a WARNING; nessun rifiuto fa cadere il server o la
chat. Dopo un errore il modello spiega e **si ferma** (regola già in vigore, `0d73750`), senza
proporre una data calcolata a mente.

*Scelte mie (l'elenco minimo; il testo esatto al costruttore):*
1. **Formato non ISO**: `15/03/2024`, `2024-3-15`, `15 marzo 2024` → «data '…' non valida: usa il
   formato AAAA-MM-GG, es. 2024-03-15».
2. **Data impossibile**: `2026-02-30`, `2025-02-29`, `2026-13-01` → «la data '…' non esiste».
3. **Fuori intervallo**: una data in ingresso, un risultato o una data spostata fuori da
   2020-01-01 … 2040-12-31 → «posso calcolare solo date tra il 2020-01-01 e il 2040-12-31».
4. **Quantità non valida**: zero, negativa, decimale o non numerica.
5. **Unità o direzione fuori elenco** (validazione Pydantic con elenco chiuso, come il
   convertitore).
6. **Intervallo rovesciato** nel conteggio dei giorni lavorativi (fine prima dell'inizio) →
   rifiuto esplicito, non uno scambio silenzioso.
7. **Mese o anno non valido** nell'elenco delle festività (`mese 13`, anno 2041).

### 15.9 Come si costruisce

Struttura analoga a convertitore e calcolatrice, per confrontarli a lezione:

- **Server**: `lezione_4/scadenze.py`, avviabile da solo, libreria `mcp` già presente (2.3.0),
  trasporto **stdio**, dati in `lezione_4/festivita.json`.
- **Strumenti** (*scelta mia, da confermare con le misure*): **pochi strumenti piccoli, uno per
  tipo di domanda**, invece di uno solo pieno di opzioni; con un modello da 9B gli strumenti
  semplici sono scelti meglio. Proposta (nomi e descrizioni in inglese come gli altri):
  - `compute_deadline(start_date, amount, unit, direction)` — gruppo A (scadenze e termini,
    anche in giorni lavorativi), con spostamento e nota;
  - `add_business_days(start_date, days, direction)` — gruppo B, «che giorno sarà fra N giorni
    lavorativi» quando **non** si parla di una scadenza (senza nota). Fa lo stesso conto di
    `compute_deadline` con i giorni lavorativi: la differenza è solo la nota, e le descrizioni
    degli strumenti devono rendere chiara la scelta (scadenza/termine → `compute_deadline`);
  - `count_business_days(start_date, end_date)` — gruppo B, conteggio;
  - `days_between(from_date, to_date)` — gruppo C;
  - `date_info(date)` — gruppo D: giorno della settimana, festività, lavorativo o no;
  - `list_holidays(year, month)` — gruppo D, `month` facoltativo.
  `unit` ∈ {giorni, giorni lavorativi, settimane, mesi, anni} (*nomi esatti dei valori al
  costruttore*),
  `direction` ∈ {avanti, indietro}, predefinita avanti. Se le misure mostrano confusione tra
  strumenti, il costruttore può raggrupparli, riportandolo.
- **Logica separata dal protocollo**: calcolo delle date, festività e messaggi in funzioni Python
  pure (`datetime.date` della libreria standard), testabili senza MCP; lo strato MCP è sottile.
- **Lato assistente**: un terzo `ClientMCP` con `parametri_scadenze()` e `collega_scadenze()`;
  i tre server restano **indipendenti** (se uno non parte, gli altri funzionano); riga
  «Giorni e scadenze (MCP): attivo / non disponibile» nell'intestazione. `ClientMCP` espone già
  tutti gli strumenti di un server (`list_tools`), quindi i sei strumenti arrivano senza modifiche
  al ponte. La gestione della nota (§15.7) è l'unica logica nuova lato assistente.
- **Grafo e registro** non cambiano struttura.
- **Cronologia** (*scelta mia*): le chiamate agli strumenti delle scadenze restano nella
  cronologia della sessione, come `convert_units` e `calculate`; l'orologio resta escluso come
  oggi (l'ora non va riusata). *Superato il 2026-11-13:* anche l'orologio resta in cronologia
  (vedi §6.2).
- **Docker**: il `Dockerfile` copia anche `scadenze.py` e `festivita.json`.
- **Nessuna dipendenza nuova.**

### 15.10 Prompt di sistema (deciso dall'utente: sempre lo strumento)

Come per gli altri strumenti: il modello usa **sempre** gli strumenti delle scadenze per ogni
domanda su date, scadenze, giorni lavorativi, festività e giorni della settimana, **mai a mente**,
anche quando la risposta sembra ovvia. Non si forza dal codice; si rafforza il prompt e si misura.
Il prompt dice anche: convertire le date dell'utente in ISO prima della chiamata; chiedere prima
l'orologio quando serve oggi; scrivere le date in ISO nelle risposte delle scadenze (non in quelle
del solo orologio); usare `compute_deadline` per scadenze e termini e `add_business_days` solo per
«che giorno sarà»; trasformare il risultato neutro di `days_between` in «mancano / sono passati»;
riportare data calcolata, motivo e data finale quando c'è uno spostamento; riportare la nota
non normativa **così com'è** quando è nel risultato; dopo un errore spiegare e fermarsi. Lezione dalla calcolatrice: non descrivere nel
prompt ciò che lo strumento **non** sa fare (fa rispondere senza strumento). Testo preciso al
costruttore, da affinare con le misure.

*Aggiunto il 2026-11-14 (domande multiple):* il prompt dice anche che, quando la domanda contiene
più richieste (per esempio «quanto fa 17*23 e quanti giorni mancano a Natale?»), dopo aver ricevuto
la data da `get_current_time` va chiamato `days_between`, senza mai contare i giorni a mente. Misura
(10 prove per riga, con tre turni precedenti): sulla domanda «17*23, 5 miglia in km e giorni a
Natale» `days_between` passa da 11/18 a 10/10 (giorni sbagliati da 3/18 a 0/10); su cinque domande
multiple diverse dall'esempio da 7/10 a 9/10 (2/10 → 0/10 numeri inventati). Una regola alternativa
(«l'utente vede solo l'ultima risposta, riporta tutti i risultati») è stata provata e scartata:
peggiorava (5/10 contro 6/10).

### 15.11 Test e verifiche

- **Test automatici senza modello**: ogni domanda del §15.2 con data fissa; spostamenti in avanti
  e all'indietro (sabato, domenica, festività, ponti di più giorni come 2026-12-25/26 + weekend);
  fine mese e bisestili del §15.3; scadenze in giorni lavorativi; conteggi agli estremi;
  differenza neutra («dopo» / «prima» / «coincidono»); festività del file (12 per anno dal 2026,
  11 prima; 4 ottobre assente nel 2025, presente nel 2026; Pasquetta controllata con l'algoritmo
  del test); **ogni rifiuto** del §15.8; nota (con il modello finto): presente alla prima
  scadenza, tolta dalla seconda dopo che è arrivata all'utente, **di nuovo presente** se il
  turno precedente è fallito o la risposta non la conteneva, mai nel gruppo B;
  server MCP in-process e via stdio con **tutti** gli strumenti elencati; collegamento
  nell'assistente (tre server indipendenti, intestazione).
- **Prove reali con LM Studio** (`RUN_REAL_TESTS=1`): una scadenza del gruppo A con spostamento
  (data calcolata, motivo e data finale nella risposta, in ISO, con la nota); una domanda che parte
  da oggi (orologio **e** scadenze chiamati); un formato non ISO dell'utente convertito dal
  modello; un rifiuto (anno 2045) senza data inventata.
- **Misure** (stesso metodo della calcolatrice): domande dei quattro gruppi in sessione nuova,
  sessione lunga mista, catena orologio → scadenze, date scritte in formati diversi, nota solo
  alla prima scadenza, scelta tra `compute_deadline` e `add_business_days`; contando le chiamate
  reali agli strumenti. **Regressione** su orologio (che deve continuare a rispondere nella forma
  attuale, non in ISO), convertitore e calcolatrice dopo il cambio di prompt, con confronto
  prima/dopo. Numeri all'utente
  e nel README; nessuna soglia bloccante, si ritocca il prompt per alcuni giri.
- **Prova Docker**: «Giorni e scadenze (MCP): attivo» nel container.

### 15.12 Obiettivi

- Server MCP separato per date e scadenze, con festività italiane 2020–2040 da file locale.
- Domande dei gruppi A–D, con spostamento della scadenza nei giorni non lavorativi.
- Date ISO ovunque, rifiuti espliciti per formati e casi limite.
- Nota non normativa alla prima scadenza della chat.
- L'assistente usa gli strumenti tramite MCP, anche in Docker, con un tasso misurato.

### 15.13 Non-obiettivi

- Festività regionali o patronali, altri paesi, anni fuori 2020–2040.
- Calcolo della Pasqua nel server; scaricare festività da Internet.
- Termini legali veri (sospensione feriale dei termini, regole del codice civile sul computo dei
  termini, ecc.): il risultato resta indicativo.
- Orari e fusi nelle scadenze (si lavora a giorni interi).
- Riconoscere date in linguaggio naturale nello strumento (lo fa il modello).
- Forzare dal codice la chiamata agli strumenti.

### 15.14 Anti-obiettivi (sarebbe un fallimento anche se «funziona»)

- Il modello che calcola date o giorni a mente, o che indovina la data di oggi senza l'orologio.
- Una scadenza spostata senza dire la data calcolata e il motivo.
- Una data fuori intervallo calcolata ignorando le festività invece di rifiutarla.
- Un formato non ISO accettato e interpretato in silenzio (03/04 è ambiguo).
- Festività scritte nel codice invece che nel file.
- Il preavviso spostato in avanti (oltre il termine).
- Una scadenza presentata come certa, senza la nota la prima volta.
- La nota considerata «data» anche se all'utente non è mai arrivata.
- L'orologio che cambia formato di risposta per colpa della regola ISO.

### 15.15 Vincoli di lavoro

- Solo in `lezione_4/`, sul branch `feature/nuove-funzionalita`.
- **Commit e push solo su richiesta esplicita dell'utente.**
- Aggiornare `CLAUDE.md` e `README.md` (struttura, avvio, test, limiti misurati).
- Comandi documentati per PowerShell.

### 15.16 Lasciato al costruttore

- Nomi interni delle funzioni, struttura del modulo, forma esatta di `festivita.json`.
- Testo esatto dei risultati e dei messaggi di errore (italiano, chiaro, date ISO).
- Nomi esatti dei valori di `unit` e `direction`; eventuale raggruppamento degli strumenti se le
  misure lo suggeriscono.
- Testo del prompt e delle descrizioni degli strumenti, da affinare con le misure.
- Dove togliere la riga della nota e quale frase fissa usare per riconoscerla (§15.7).

## 17. Router d'ambito: grafo con due nodi LLM — aggiunto il 2026-11-12

Stato: implementata (2026-11-12); piano: `docs/superpowers/plans/2026-11-12-router-ambito.md`. Indipendente dalla §16 (ancora in specifica, non implementata):
si parte dal codice del commit `f50307c`, verificato prima di cominciare.

### 17.1 Intento

Primo passo dell'evoluzione dell'assistente in un grafo con **due nodi LLM**. Testo del compito:

> Realizziamo un router che decide se la domanda rientra nell'ambito dell'agente. L'assistente ha
> un ambito dichiarato in configurazione. Un nodo LLM posto prima dell'agente decide se la domanda
> rientra nell'ambito o no. La scelta di che tool usare rimane all'agente e così com'è.

**Obiettivo (dall'utente):** le domande fuori ambito ricevono una risposta di rifiuto **senza
raggiungere l'agente**.

Regola di lavoro dell'utente: ogni passo riparte dal precedente funzionante e verificato, con le
evidenze richieste.

### 17.2 Ambito (deciso dall'utente)

- **In ambito → categoria `conversazione`:** orari e fusi, conversioni di unità, calcoli,
  date e scadenze; inoltre saluti, ringraziamenti, «cosa sai fare?» e seguiti che da soli non
  hanno senso («e a Roma?») — sono conversazione e passano all'agente.
- **Fuori ambito → categoria `fuori_ambito`:** per esempio ricette, politica, e in generale ciò
  che non rientra nell'elenco sopra.
- **Seguiti giudicati nel contesto (deciso dall'utente):** un seguito prende la categoria della
  domanda a cui si riferisce. «e a Roma?» dopo una domanda sull'ora è `conversazione`;
  «e quella dell'amatriciana?» dopo una ricetta rifiutata è `fuori_ambito`. Così non si aggira
  il router riformulando una domanda come seguito. Le misure (§17.9) includono entrambi i casi.
- *Scelta mia:* una domanda **mista** (una parte in ambito, una fuori, per esempio «converti 5
  miglia in km e dammi una ricetta») è `conversazione`: passa all'agente, che risponde come oggi.

### 17.3 Grafo

```
START → router ──(conversazione, o router non valido)──→ agente ⇄ strumenti → END
              └─(fuori_ambito)────────────────────────→ rifiuto → END
```

- **router** (nuovo, LLM): classifica la domanda e scrive categoria e motivo nello **stato**
  (campi nuovi di `StatoAssistente`), **non** nella lista dei messaggi.
- **agente**: l'attuale nodo `modello`, con il suo giro verso `strumenti`, l'instradamento
  `instrada` e il limite dei passaggi **invariati** (§6.3, §6.4). *Scelta mia:* il nodo
  `modello` si rinomina `agente`, così grafo e log usano le parole del compito.
- **rifiuto** (nuovo, senza LLM): aggiunge ai messaggi un `AIMessage` con la frase fissa
  della configurazione.
- **arco condizionale** dopo il router: una funzione esplicita e testabile a parte (come
  `instrada`) che restituisce `agente` o `rifiuto`.
- Solo Graph API di LangGraph, come in §6.3. Il limite di ricorsione si alza di quanto serve per
  i nuovi super-step (router + eventuale rifiuto), così non scatta prima di `MAX_TOOL_STEPS`.
- `costruisci_grafo` riceve il router (o il suo modello) e la frase di rifiuto come dipendenze,
  così i test iniettano un router finto.

### 17.4 Il router

- **Stesso modello** di LM Studio (`LM_BASE_URL`, `LM_MODEL`), **senza strumenti collegati**, con
  il ragionamento disattivato come l'agente (§6.1, `RAGIONAMENTO_DISATTIVATO`).
- **Output strutturato:** una classe Pydantic con due campi:
  - `categoria`: `Literal["conversazione", "fuori_ambito"]`;
  - `motivo`: frase breve in italiano.
  Si ottiene con `with_structured_output` di `ChatOpenAI`, metodo `json_schema`. **Da verificare
  per primo** con una chiamata reale al modello. *Scelta mia:* se `json_schema` non funziona con
  LM Studio e `qwen/qwen3.5-9b`, il ripiego ammesso è un prompt che chiede il JSON seguito dalla
  validazione Pydantic del testo restituito; **non** `function_calling`, perché collegherebbe uno
  strumento al router. Il ripiego va riportato all'utente prima di proseguire.
- *Scelta mia:* il router ha un **timeout proprio più breve** dell'agente (60 s, costante nel
  codice, non configurabile): un router bloccato non deve ritardare l'agente di 5 minuti. Allo
  scadere vale il fail-open.
- **Il router non valuta gli strumenti:** il suo prompt non nomina strumenti né dice come
  rispondere; giudica solo se la domanda rientra nell'ambito.
- **Che cosa vede:**
  - un messaggio di sistema proprio, con le istruzioni di classificazione (nel codice) e il
    testo dell'ambito (dalla configurazione, §17.5);
  - la cronologia della sessione ridotta a **sole domande e risposte** (`HumanMessage` e
    `AIMessage` con testo), senza il prompt di sistema dell'agente, senza chiamate agli
    strumenti e senza `ToolMessage` (deciso dall'utente);
  - la domanda corrente.
  La cronologia serve per i seguiti come «e a Roma?».
- **Router non valido (fail-open, deciso dall'utente):** se la chiamata al router va in errore
  (eccezione, timeout, output non conforme allo schema) la domanda **passa all'agente**; il log
  lo segnala con un WARNING (§17.7). Il rifiuto avviene solo con una categoria valida
  `fuori_ambito`.
- Il prompt del router si affina con le misure (§17.9), al massimo tre giri, tenendo il migliore.
- **Parti della domanda (aggiunto il 2026-11-15, per il revisore, §18.4 «Domande miste»):** lo
  schema ha due campi in più, obbligatori, tra `motivo` e `categoria` (ordine: `motivo`,
  `parti_fuori_ambito`, `domanda_in_ambito`, `categoria`):
  - `parti_fuori_ambito`: lista delle parti della richiesta fuori ambito (vuota se non ce ne sono);
  - `domanda_in_ambito`: la richiesta riscritta con le sole parti in ambito, con le parole
    dell'utente (uguale all'originale se è tutta in ambito, vuota se è tutta fuori ambito).
  La classificazione non cambia: decide sempre e solo `categoria`. Misurato prima di adottarli: 12/12
  domande del tutto fuori ambito restano `fuori_ambito` (compreso il seguito «e quella
  dell'amatriciana?»).
- **Parti solo dall'ultimo messaggio (correzione del 2026-11-16, dopo la misura g7):** nei turni
  subito dopo una domanda mista il router ripeteva le parti escluse del turno precedente (3 false
  «domande miste» su 38 turni: festività, giorni dal 1° gennaio, «Converti 3,7 km in miglia»), e una
  prova reale sul seguito «e in piedi?» falliva 2 volte su 3. In fondo a `ISTRUZIONI_ROUTER` si
  aggiunge: «Le parti fuori ambito si prendono solo dall'ultimo messaggio dell'utente: quelle dei
  turni precedenti sono già state gestite e non vanno ripetute. Se l'ultimo messaggio non chiede
  nulla fuori ambito, parti_fuori_ambito è una lista vuota.» Dopo la correzione: 10/10 (5 ripetizioni
  × 2 casi).
- **Controllo nel codice (deciso dall'utente il 2026-11-16, dopo la misura g8):** con la riga sopra
  restava 1 falsa «domanda mista» su 19 turni («Converti 3,7 km in miglia» subito dopo una domanda
  con un film). `domanda_mista(esito, domanda_utente)` riceve anche il testo dell'ultima domanda e
  restituisce None se la domanda ridotta coincide con quella dell'utente, confrontando le parole in
  minuscolo senza punteggiatura né spazi: se non è stato escluso nulla, la domanda non è mista e il
  revisore vede la domanda originale. Regola fissa, non dipende dal modello.

### 17.5 Configurazione (decisa dall'utente: variabili d'ambiente in `config.py`)

| Variabile | Contenuto | Obbligatoria |
|---|---|---|
| `AMBITO_ASSISTENTE` | descrizione in italiano dell'ambito (§17.2), su una riga | sì |
| `MESSAGGIO_RIFIUTO` | la frase fissa restituita alle domande fuori ambito | sì |

- *Scelta mia:* obbligatorie come `LM_MODEL`, **senza valore di riserva nel codice** (altrimenti
  l'ambito tornerebbe nel codice); se mancano, errore all'avvio che nomina la variabile (§6.8).
- Testo d'esempio in `.env.example`; il `.env` reale va aggiornato a mano (resta fuori da Git).
  Docker le riceve già tramite `env_file: .env`.
- `Config` riceve due campi nuovi; i test di `config.py` coprono presenza e assenza.

### 17.6 Cronologia (decisa dall'utente)

- Domanda **in ambito**: come oggi (§6.2 e `Sessione.chiedi`).
- Domanda **fuori ambito**: in cronologia entrano la domanda e la frase fissa di rifiuto; il
  **motivo resta solo nel log**, non va né all'agente né al router nei turni successivi.
- Il rifiuto non provoca `LimitePassaggiRaggiunto` e non tocca la nota non normativa.

### 17.7 Log (livello INFO salvo dove indicato)

- Router: una riga per domanda con categoria, motivo e destinazione, per esempio
  `INFO router: categoria=conversazione motivo="…" -> agente` oppure `-> rifiuto`.
- Router non valido: `WARNING router: risposta non valida (…) -> agente`.
- Domanda mista (2026-11-15, §18.4): una seconda riga
  `INFO router: domanda mista: al revisore solo "…" (escluse: "…; …")`.
- Agente: **una riga INFO a ogni esecuzione** del nodo `agente` (per esempio
  `INFO agente: chiamata 1`), così il log dimostra quando l'agente gira e quando no. Cambia
  quindi la regola di §6.7 «una domanda che non usa lo strumento non produce log».
- Rifiuto: `INFO rifiuto: risposta fissa`.
- Il DEBUG già esistente dell'agente resta; il router a DEBUG registra i messaggi inviati.

### 17.8 Evidenze richieste (dall'utente)

1. **Domanda in ambito:** log con categoria, motivo e passaggio all'agente.
2. **Domanda fuori ambito:** risposta di rifiuto; **nessuna** riga dell'agente nel log.
3. **Test con risposte del router simulate** per entrambi i percorsi.

### 17.9 Test e verifiche

- **Automatici (router finto, nessun LM Studio):**
  - percorso `conversazione` → agente eseguito (anche con strumenti), log del router e
    dell'agente presenti;
  - percorso `fuori_ambito` → frase fissa, modello dell'agente **mai chiamato**, nessuna riga
    dell'agente nel log;
  - router che solleva un'eccezione o restituisce un output non valido → agente eseguito,
    WARNING;
  - funzione dell'arco condizionale testata da sola;
  - il router riceve solo domande e risposte (niente `ToolMessage`, niente chiamate, niente
    prompt dell'agente) e il testo dell'ambito dalla configurazione;
  - cronologia dopo un rifiuto: domanda + frase fissa, senza motivo;
  - configurazione: variabili nuove obbligatorie;
  - i test esistenti aggiornati al grafo nuovo, tutti verdi.
- **Reali (LM Studio, `RUN_REAL_TESTS=1`):** almeno un caso in ambito e uno fuori ambito nel
  file `test_reale.py`; i 9 test reali esistenti restano verdi.
- **Misure (dal controllore, app vera via stdin):** una serie di domande in ambito (orari,
  conversioni, calcoli, scadenze), di conversazione (saluti, «cosa sai fare?», seguiti come
  «e a Roma?») e fuori ambito (ricette, politica, altro), anche con parole diverse dagli esempi
  del prompt, ripetuta in più sessioni; si contano le righe `router:` e `agente:` del log.
  Errori da cercare: domanda in ambito rifiutata (il più grave), domanda fuori ambito passata,
  output non valido. Numeri all'utente e nel README; nessuna soglia bloccante.
- **Chi misura:** il controllore della sessione, cioè Claude nella sessione principale, non i
  subagenti. Fa il ciclo misura → ritocco del prompt del router → nuova misura (massimo tre giri)
  e riporta i numeri di prima mano.
- **Regressione:** *scelta mia*, poiché l'elenco delle 15 domande della prova guidata non è
  salvato nel repository, il controllore lo ricostruisce prendendo almeno una domanda per
  strumento e i casi dei limiti noti. Lo esegue **prima** della modifica, sul codice di
  `f50307c`, per avere gli esiti di riferimento, e **dopo** la modifica. Criterio: nessuna
  domanda in ambito rifiutata ed esiti degli strumenti non peggiori di quelli di riferimento.
  Lo script resta nella scratchpad.
- **Docker:** `docker compose build`, poi un rifiuto e una domanda in ambito nel container.

### 17.10 Obiettivi

- Nodo router LLM con output strutturato (categoria e motivo) prima dell'agente.
- Ambito e frase di rifiuto descritti in configurazione, non nel codice.
- Arco condizionale: conversazione → agente; fuori ambito → rifiuto → fine.
- Agente e strumenti invariati nel comportamento.
- Le evidenze di §17.8, prodotte e riportate.

### 17.11 Non-obiettivi

- Più di due categorie, o un instradamento verso agenti diversi (passi successivi).
- Frase di rifiuto generata dall'LLM o che cita il motivo.
- Far scegliere gli strumenti al router, o togliere strumenti all'agente.
- Un modello diverso per il router, o una configurazione del modello separata.
- Persistenza della cronologia.

### 17.12 Anti-obiettivi (sarebbe un fallimento anche se «funziona»)

- Una domanda in ambito (o un saluto, o un seguito come «e a Roma?») rifiutata.
- Il nodo agente eseguito per una domanda classificata `fuori_ambito`.
- L'ambito o la frase di rifiuto scritti nel codice.
- Il router che menziona o sceglie strumenti, o che cambia il comportamento dell'agente.
- Il motivo del router che finisce nella risposta o nella cronologia.
- Un guasto del router che trasforma ogni domanda in un rifiuto.

### 17.13 Vincoli di lavoro

- Solo in `lezione_4/`, sul branch `feature/nuove-funzionalita`; la §16 non committata resta
  intatta e fuori da questo lavoro.
- **Commit e push solo su richiesta esplicita dell'utente.**
- Aggiornare `CLAUDE.md` (struttura del grafo), `README.md` (variabili nuove, log, misure) e la
  descrizione del grafo in testa a `grafo.py`.
- Comandi documentati per PowerShell.

### 17.14 Lasciato al costruttore

- Nomi interni (classe dello schema, funzioni, campi dello stato), modulo nuovo o dentro `grafo.py`.
- Testo delle istruzioni del router e degli esempi in `.env.example`, da affinare con le misure.
- Formato esatto delle righe di log, purché contengano quanto richiesto in §17.7.
- Come si riduce la cronologia per il router, purché rispetti §17.4.

## 18. Revisore della risposta: secondo nodo LLM — aggiunto il 2026-11-14

Stato: implementata (2026-11-14); piano: `docs/superpowers/plans/2026-11-14-revisore-risposta.md`;
misure nel README («Misure del revisore»). Si parte dal codice del commit `96d46a2` (router §17 e
correzioni successive), verificato prima di cominciare. Indipendente dalla §16 (bozza, non implementata).

### 18.1 Intento

Secondo passo dell'evoluzione dell'assistente in un grafo con **due nodi LLM** (il primo è il
router, §17). Testo del compito (dall'utente):

> Aggiungere un nodo revisore che controlla che la risposta sia coerente con la domanda.
> L'obiettivo è far sì che una risposta incompleta o fuori tema torni all'agente con il motivo,
> finché non è coerente o si raggiunge il limite.

Da realizzare (dall'utente):
1. nodo revisore che riceve la domanda dell'utente e la risposta proposta dall'agente;
2. output strutturato: coerente (sì o no) e motivo;
3. se non coerente, il motivo entra nella cronologia come indicazione per l'agente;
4. limite di revisioni nello stato: al limite si restituisce l'ultima risposta e lo si segnala
   nei log.

Regola di lavoro dell'utente: ogni passo riparte dal precedente funzionante e verificato, con le
evidenze richieste.

### 18.2 Che cosa giudica il revisore (deciso dall'utente)

Una risposta proposta è **coerente** solo se tutte queste condizioni valgono:
- **completa:** risponde a tutte le parti della domanda (una domanda in due parti con una sola
  parte risolta è non coerente);
- **in tema:** risponde alla domanda posta, letta nel contesto della conversazione (un seguito
  come «e a Roma?» si giudica rispetto alla domanda precedente);
- **fedele ai risultati degli strumenti:** i valori riportati sono quelli restituiti dagli
  strumenti del turno, senza valori cambiati o inventati;
- **nessun valore a mente:** un valore che andava ottenuto da uno strumento (ora, conversione,
  calcolo, data, conteggio di giorni) ma non viene da nessun risultato di strumento è motivo di
  rifiuto, **anche se il valore è giusto** (regola «sempre lo strumento», vedi §15.10).
- *Scelta mia:* un valore già dato in un turno precedente e ripetuto tale e quale non è «a
  mente»; un valore nuovo derivato da esso (per esempio da giorni a settimane) sì.
- *Scelta mia:* saluti, ringraziamenti, «cosa sai fare?» e risposte che spiegano un rifiuto o un
  errore di uno strumento non contengono valori da verificare: si giudicano solo per completezza
  e tema.
- **Domande miste (deciso dall'utente):** il revisore conosce l'ambito (`AMBITO_ASSISTENTE`, lo
  stesso testo del router, §17.5) e **ignora le parti fuori ambito**: per «converti 5 miglia in
  km e dammi una ricetta» una risposta che tratta solo la conversione è coerente. Il revisore non
  deve mai spingere l'agente a rispondere a una parte fuori ambito. Come si ottiene: §18.4
  «Domande miste».
- *Scelta mia:* il revisore giudica il testo dell'agente prima che `Sessione` aggiunga la nota
  non normativa di `compute_deadline`; non deve pretendere la nota.

Il revisore **non** sceglie strumenti, **non** riscrive la risposta e **non** risponde
all'utente: dà solo il giudizio e il motivo.

### 18.3 Grafo

Percorso principale (dall'utente): `START → router → agente → revisore → END`. Con gli archi
esistenti:

```
START → router ──(fuori_ambito)──→ rifiuto → END
              └─(conversazione o router non valido)──→ agente ⇄ strumenti
                                                        │ (risposta finale)
                                                        ▼
                                                    revisore ──(coerente, revisore non valido,
                                                        │       o limite revisioni)──→ END
                                                        └─(non coerente, sotto il limite)──→ agente
```

- **revisore** (nuovo, LLM): si esegue quando l'agente dà una **risposta finale** (nessuna
  tool_call). L'instradamento dopo l'agente diventa: strumenti se li chiede e c'è ancora passo;
  revisore se la risposta è finale; fine se il limite degli strumenti è raggiunto, senza passare
  dal revisore:
  - al **primo tentativo** del turno (nessuna risposta proposta prima): come oggi,
    `LimitePassaggiRaggiunto`;
  - in un **tentativo dopo una revisione** (deciso dall'utente): si restituisce l'**ultima
    risposta proposta** (quella rifiutata) con `WARNING revisore: limite degli strumenti nel
    tentativo dopo la revisione, restituita l'ultima risposta`. Serve conservare nello stato
    l'ultima risposta proposta.
- **arco condizionale** dopo il revisore: funzione esplicita e testabile a parte (come
  `instrada` e `dopo_router`) che restituisce `agente` o `fine`.
- Il **rifiuto** del router non passa dal revisore.
- *Scelta mia:* il conteggio dei passaggi verso gli strumenti (`passi_strumento`) **si azzera a
  ogni ritorno dal revisore**: ogni tentativo dell'agente ha i suoi `MAX_TOOL_STEPS`, altrimenti
  dopo un rifiuto l'agente potrebbe non avere più passaggi per chiamare lo strumento mancante.
- Il limite di ricorsione di LangGraph si alza di quanto serve (fino a `MAX_REVISIONI + 1`
  tentativi, ciascuno con i suoi passaggi agli strumenti e un passaggio dal revisore), così non
  scatta prima dei nostri limiti.
- `costruisci_grafo` riceve il revisore come dipendenza e il limite di revisioni, così i test
  iniettano un revisore finto.

### 18.4 Il revisore

- **Stesso modello** di LM Studio, **senza strumenti collegati**, ragionamento disattivato,
  timeout proprio di 60 s e `max_retries=0`, come il router (§17.4).
- **Output strutturato** (dall'utente): classe Pydantic con due campi, **`motivo` prima di
  `coerente`** (*scelta mia*, per lo stesso effetto misurato sul router: il modello ragiona
  prima di decidere):
  - `motivo`: frase breve in italiano; se non coerente, dice che cosa manca o che cosa è
    sbagliato, in modo utilizzabile dall'agente;
  - `coerente`: booleano.
  `with_structured_output`, metodo `json_schema`, come il router.
- **Regola violata (deciso dall'utente il 2026-11-14, contro i falsi rifiuti pignoli):** lo schema
  ha un terzo campo `regola`, **tra `motivo` e `coerente`**, con valori
  `Literal["nessuna", "completezza", "contraddizione", "valore_a_mente"]`, cioè le tre regole di
  rifiuto del prompt (parte in ambito senza risposta; valore che contraddice uno strumento; valore
  non ottenuto da uno strumento). La risposta torna all'agente **solo se `coerente` è falso e
  `regola` non è `nessuna`**. Un `coerente` falso con `regola = nessuna` conta come approvazione e
  lo si segnala nel log (§18.7); un `coerente` vero con una regola indicata resta un'approvazione.
- **Che cosa vede (deciso dall'utente: anche gli scambi precedenti, come contesto):**
  - un messaggio di sistema proprio con le istruzioni di revisione (nel codice) e il testo
    dell'ambito (dalla configurazione, come il router);
  - gli **scambi precedenti** della sessione ridotti a domande e risposte in testo (come il
    router), senza il prompt di sistema dell'agente;
  - del **turno corrente**: la domanda, le chiamate agli strumenti con argomenti e risultati
    (**dall'utente: controlla anche i risultati dei tool**), le eventuali indicazioni di
    revisioni precedenti dello stesso turno e la risposta proposta.
  *Scelta mia:* il turno corrente si passa al revisore in forma leggibile (per esempio un unico
  messaggio che elenca chiamate, risultati e risposta proposta), non come tool_call native,
  perché il revisore non ha strumenti collegati. La forma esatta è lasciata al costruttore.
- **Numeri in formato italiano (deciso dall'utente il 2026-11-14, dopo le misure):** nel turno
  presentato al revisore i numeri decimali dei **risultati degli strumenti** si scrivono con la
  virgola (`49.7097` → `49,7097`), come li scrive l'agente nelle risposte; date (`2026-11-14`),
  orari (`15:42:19`), argomenti delle chiamate e risposta proposta restano invariati. Il prompt del
  revisore non parla più di virgola e punto. Motivo: con il punto nei risultati il revisore
  respingeva risposte corrette scritte con la virgola, anche quando il prompt diceva che erano
  equivalenti (falsi rifiuti nelle misure e in due test reali).
- **Revisore non valido (fail-open, *scelta mia* confermata dall'utente):** eccezione, timeout o
  output non conforme → la risposta proposta passa all'utente; `WARNING revisore: risposta non
  valida (…) -> fine`.
- Il prompt del revisore si affina con le misure (§18.9), al massimo tre giri, tenendo il
  migliore; verificare anche su domande diverse dagli esempi del prompt.
- **Domande miste (deciso dall'utente il 2026-11-15, variante «V2c»):** nella misura g6 il revisore
  ha preteso la parte fuori ambito in 3 domande miste su 3 (anti-obiettivo §18.12), nonostante il
  prompt dicesse «non chiederla mai». Per questo il revisore **non vede più la parte fuori ambito**:
  - il router scrive le parti fuori ambito e la domanda ridotta alle parti in ambito (§17.4);
  - se la domanda è `conversazione`, ha almeno una parte fuori ambito non vuota e la domanda ridotta
    non è vuota, il turno presentato al revisore comincia con
    `Domanda dell'utente (solo le parti in ambito): <domanda ridotta>` e
    `Parti fuori ambito già escluse (l'assistente fa bene a non rispondere, non chiederle mai): a; b`
    al posto di `Domanda dell'utente: <domanda>`; in tutti gli altri casi (domanda tutta in ambito,
    router non valido) il revisore vede la domanda originale, così i seguiti non vengono riscritti;
  - la riduzione sta nello stato del grafo (`mista`), azzerata dal router a ogni turno, e vale per
    tutte le revisioni del turno;
  - **l'agente non cambia:** vede sempre la domanda intera e spiega lui che la parte fuori ambito
    non rientra nei suoi compiti.
  Varianti provate prima (spike su 14 casi × 2, nessuna modifica al progetto): prompt attuale 19/28;
  revisore che divide da sé le parti 26/28 (approva un conteggio di giorni a mente); router che divide
  + nota 26/28 (indulgente sulle risposte incomplete); revisore con la sola domanda ridotta 26/28
  (sbaglia i seguiti riscritti dal router). V2c unisce le ultime due solo quando la domanda è
  davvero mista. Misura con l'app vera: README, «Misure del revisore» (g7). Dopo g7 il router prende
  le parti fuori ambito solo dall'ultimo messaggio, e una domanda ridotta uguale all'originale non
  conta come mista (§17.4, 2026-11-16; misura g8 nel README).

### 18.5 Indicazione all'agente (dall'utente: il motivo entra nella cronologia)

- Se la risposta non è coerente, ai messaggi del turno si aggiungono, nell'ordine, la
  **risposta proposta** dell'agente (già presente) e un **messaggio di indicazione** con il
  motivo del revisore; poi si torna all'agente, che vede tutto il turno e può chiamare gli
  strumenti mancanti.
- *Scelta mia:* l'indicazione è un `HumanMessage` con un prefisso riconoscibile (per esempio
  `[Revisione] La risposta precedente non va bene: <motivo>. Correggila.`), non un
  `SystemMessage`: il modello di chat di Qwen può rifiutare messaggi di sistema a metà
  conversazione. **Da verificare per primo** con una chiamata reale; se il formato scelto dà
  errore o l'agente non lo segue, si riporta all'utente prima di proseguire.
- **Con la regola (2026-11-14):** l'indicazione nomina anche la regola violata, nella forma
  `[Revisione] Regola violata: <regola>. La risposta precedente non va bene: <motivo> Correggila: …`.
- **Solo per il turno corrente** (confermato dall'utente): alla fine del turno, in cronologia di
  sessione entrano come oggi solo la domanda, le chiamate di `STRUMENTI_IN_CRONOLOGIA` e la
  risposta finale. Risposte rifiutate e indicazioni restano solo nei log.
- *Scelta mia:* le chiamate agli strumenti conservate in cronologia sono quelle di tutti i
  tentativi del turno (regola di §6.2 applicata a tutti i passaggi intermedi).

### 18.6 Limite di revisioni (dall'utente: nello stato)

- Un campo dello stato conta le revisioni con esito «non coerente» nel turno; parte da 0 a ogni
  domanda.
- Configurazione: `MAX_REVISIONI`, intero ≥ 0, predefinito **2** (*scelta mia*, confermata
  dall'utente): al massimo 2 rimandi all'agente, quindi al massimo 3 risposte proposte e 3
  revisioni per turno. Valore non valido → errore all'avvio, come `MAX_TOOL_STEPS`. Con 0 il
  revisore giudica una volta e la risposta passa comunque.
- **Aggiornamento (deciso dall'utente il 2026-11-14):** predefinito **3**, quindi al massimo 3
  rimandi, 4 risposte proposte e 4 revisioni per turno (anche nel `.env` locale e in `.env.example`).
- **Al limite:** si restituisce l'**ultima risposta proposta** e si scrive nel log
  `WARNING revisore: limite di N revisioni raggiunto, restituita l'ultima risposta` (dall'utente:
  segnalarlo nei log). Nessun messaggio aggiuntivo all'utente (*scelta mia*).

### 18.7 Log (livello INFO salvo dove indicato)

- Revisore, una riga per revisione, nello stesso stile del router:
  `INFO revisore: coerente=no motivo="…" -> agente (revisione 1/2)` oppure
  `INFO revisore: coerente=sì motivo="…" -> fine`.
- Con la regola (2026-11-14) la riga riporta anche la regola, per esempio
  `INFO revisore: coerente=no regola=completezza motivo="…" -> agente (revisione 1/3)`; un rifiuto
  senza regola si scrive `INFO revisore: coerente=no regola=nessuna motivo="…" -> fine (rifiuto senza regola, trattato come coerente)`.
- Limite: il WARNING di §18.6. Revisore non valido: il WARNING di §18.4.
- DEBUG: messaggi inviati al revisore.
- Le righe esistenti di router, agente e rifiuto restano; `agente: chiamata n` continua a
  contare i passaggi del tentativo corrente.

### 18.8 Evidenze richieste

Dall'utente:
1. **Domanda in due parti con risposta parziale:** rifiuto motivato del revisore e nuova risposta
   completa (log e risposta finale).
2. **Risposta coerente:** approvata al primo passaggio (una sola riga `revisore:`).
3. **Limite rispettato con un revisore simulato che rifiuta sempre:** esattamente
   `MAX_REVISIONI + 1` revisioni, restituita l'ultima risposta, WARNING nel log.

*Scelta mia, dalla decisione dell'utente su §18.2:*
4. **Valore a mente:** una risposta con un valore non ottenuto da uno strumento viene rifiutata.

*Scelta mia, su come produrle:* il modello reale potrebbe rispondere subito per intero, e allora
le evidenze 1 e 4 non comparirebbero. Per questo si producono a due livelli:
- **test automatici** con agente e revisore finti, che dimostrano l'instradamento;
- **test reali** in `test_reale.py` con un **agente finto** che dà la risposta parziale (1) o il
  valore a mente (4) e il **revisore vero** su LM Studio. Dimostrano che il modello riconosce i
  due casi. Per la 1, il secondo tentativo usa l'agente vero, che deve dare la risposta completa;
- inoltre si osserva l'app vera via stdin, e si riportano i casi in cui l'agente reale dà
  spontaneamente risposte parziali o valori a mente.

### 18.9 Test e verifiche

- **Automatici (agente e revisore finti, nessun LM Studio):**
  - risposta coerente → una revisione, fine, risposta invariata;
  - non coerente poi coerente → indicazione con il motivo nei messaggi del turno, agente
    richiamato, risposta finale = seconda risposta;
  - revisore che rifiuta sempre → `MAX_REVISIONI + 1` revisioni, ultima risposta restituita,
    WARNING; anche con `MAX_REVISIONI=0`;
  - revisore che solleva un'eccezione o dà output non valido → risposta passa, WARNING;
  - dopo un rifiuto l'agente può chiamare gli strumenti (contatore azzerato);
  - il revisore riceve scambi precedenti, chiamate e risultati del turno e risposta proposta,
    non il prompt di sistema dell'agente;
  - rifiuto del router e limite degli strumenti non passano dal revisore;
  - limite degli strumenti al primo tentativo → `LimitePassaggiRaggiunto`; nel tentativo dopo
    una revisione → ultima risposta proposta e WARNING;
  - domanda mista: il revisore riceve il testo dell'ambito;
  - domanda mista (V2c): schema del router con i campi nuovi nell'ordine giusto e obbligatori;
    `domanda_mista` restituisce la riduzione solo per una vera domanda mista; il revisore vede la
    domanda ridotta e le parti escluse, l'agente la domanda intera; riga di log; riduzione
    conservata dopo una revisione e azzerata al turno successivo; le istruzioni del router chiedono
    le parti fuori ambito solo dall'ultimo messaggio; nessuna riduzione se la domanda ridotta
    coincide con quella dell'utente (maiuscole, punteggiatura e spazi ignorati), anche nel grafo;
  - cronologia di sessione senza risposte rifiutate né indicazioni;
  - funzione dell'arco dopo il revisore testata da sola; configurazione di `MAX_REVISIONI`;
  - test esistenti aggiornati al grafo nuovo, tutti verdi.
- **Reali (LM Studio, `RUN_REAL_TESTS=1`):** almeno la domanda in due parti e una risposta
  coerente in `test_reale.py`; i test reali esistenti restano verdi. Per V2c: il router vero estrae
  le parti di una domanda mista; catena vera router → revisore che approva la risposta giusta a una
  domanda mista; dopo una domanda mista il router non ripete le parti escluse nella domanda seguente
  (festività, seguito «e in piedi?»).
- **Primo controllo reale:** output strutturato del revisore e formato dell'indicazione (§18.5).
- **Misure (dal controllore, app vera via stdin):** domande semplici, in due parti, seguiti,
  saluti, per ogni strumento, ripetute in più sessioni. Si contano: risposte coerenti rifiutate
  (falsi rifiuti, il più grave perché allunga i tempi e può peggiorare la risposta), risposte
  parziali o con valori a mente approvate, limiti raggiunti, output non validi, tempi per turno.
  Numeri all'utente e nel README; nessuna soglia bloccante.
- **Contesto:** misurare i token della richiesta al revisore (cronologia + turno) rispetto al
  contesto di 8192 di LM Studio; se serve, riportarlo all'utente prima di ridurre il contesto.
- **Regressione:** le domande della regressione di §17.9 prima (su `96d46a2`) e dopo; criterio:
  esiti non peggiori.
- **Docker:** `docker compose build`, poi una domanda in due parti nel container.
- **Chi misura:** il controllore in sessione, numeri di prima mano.

### 18.10 Obiettivi

- Nodo revisore LLM con output strutturato (motivo, coerente) dopo la risposta finale
  dell'agente.
- Rimando all'agente con il motivo, fino a coerenza o limite.
- Limite di revisioni nello stato, configurabile, con segnalazione nei log.
- Le evidenze di §18.8, prodotte e riportate.

### 18.11 Non-obiettivi

- Un revisore che riscrive la risposta o risponde lui all'utente.
- Un revisore con strumenti, o che ricalcola i valori per controllarli.
- Revisione del rifiuto fisso del router.
- Un modello diverso per il revisore o una configurazione del modello separata.
- Persistenza della cronologia.

### 18.12 Anti-obiettivi (sarebbe un fallimento anche se «funziona»)

- Risposte coerenti rifiutate di frequente (turni più lenti senza guadagno).
- Un ciclo che non termina, o che termina per il limite di ricorsione invece che per il nostro.
- Risposte rifiutate o indicazioni del revisore che restano nella cronologia di sessione o
  arrivano all'utente.
- Un guasto del revisore che blocca la risposta.
- Un revisore che spinge l'agente a rispondere a una parte fuori ambito.
- Un errore all'utente quando esisteva già una risposta proposta.
- Il router, l'agente e gli strumenti che cambiano comportamento oltre il nuovo instradamento.

### 18.13 Vincoli di lavoro

- Solo in `lezione_4/`, sul branch `feature/nuove-funzionalita`; la §16 non committata resta
  intatta e fuori da questo lavoro.
- **Commit e push solo su richiesta esplicita dell'utente.**
- Aggiornare `CLAUDE.md` (struttura e obiettivo), `README.md` (variabile nuova, log, misure), la
  descrizione del grafo in testa a `grafo.py` e `.env.example`.

### 18.14 Lasciato al costruttore

- Nomi interni (schema, funzioni, campi dello stato), modulo nuovo (per esempio
  `assistente/revisore.py`) o dentro `grafo.py`.
- Testo delle istruzioni del revisore e dell'indicazione, da affinare con le misure.
- Forma con cui il turno corrente viene presentato al revisore, purché contenga quanto in §18.4.
- Formato esatto delle righe di log, purché contengano quanto in §18.7.

## 19. Riassunto della cronologia: terzo nodo LLM — aggiunto il 2026-11-16

Stato: implementata (2026-11-17), con due limiti noti misurati (nome/preferenze dopo più compressioni,
seguito ellittico verso un turno riassunto: vedi README «Misure del riassunto»); piano:
`docs/superpowers/plans/2026-11-16-riassunto-cronologia.md`. In specifica dal 2026-11-16. Si parte dal codice del commit `2eea005` (router §17 e revisore
§18), verificato prima di cominciare. Indipendente dalla §16 (bozza, non implementata). Restano
aperti dal passo precedente, fuori da questo lavoro salvo diversa decisione dell'utente: il
secondo controllo sulle false «domande miste» nei seguiti, le righe g7/g8 nel README, i test
reali completi e la regressione del revisore.

### 19.1 Intento

Terzo e ultimo passo dell'evoluzione dell'assistente in un grafo con nodi LLM (router §17,
revisore §18). Testo del compito (dall'utente):

> Un nodo LLM sostituisce i messaggi più vecchi con un riassunto e mantiene intatti gli ultimi
> turni.

**Obiettivo (dall'utente):** la conversazione resta utilizzabile su molti turni senza perdere le
informazioni importanti.

Da realizzare (dall'utente):
1. soglia configurabile, in numero di messaggi o stima dei token, oltre la quale si riassume;
2. nodo riassunto all'inizio del turno: comprime i messaggi vecchi e conserva gli ultimi N turni;
3. il riassunto è un campo dello stato che viene aggiornato, non accumulato;
4. il taglio non separa mai una richiesta di strumento dal relativo `ToolMessage`.

Regola di lavoro dell'utente: ogni passo riparte dal precedente funzionante e verificato, con le
evidenze richieste.

### 19.2 Dove vive la memoria (deciso dall'utente: strada A)

Oggi il grafo non ha memoria tra i turni: `Sessione` conserva la cronologia e la passa intera a
ogni `invoke`; la aggiorna solo se il turno riesce (§6.2). Due strade valutate con l'utente:
- **A (scelta):** `Sessione` conserva **cronologia e riassunto** e li passa al grafo a ogni turno;
  il nodo `riassunto` restituisce il riassunto nuovo e la cronologia accorciata; `Sessione` li
  salva **solo se il turno riesce**.
- B (scartata): checkpointer di LangGraph con `thread_id`; avrebbe richiesto di riscrivere il
  ripristino dopo un turno fallito e la pulizia della cronologia (risposte respinte, chiamate non
  conservate, nota), con ricadute su gran parte dei test.

Conseguenze della strada A:
- `riassunto` è un **campo di `StatoAssistente`** (testo, vuoto o assente se non c'è ancora un
  riassunto): entra nel grafo con la cronologia, il nodo lo **sostituisce** con quello nuovo, e
  `Sessione` lo conserva per il turno dopo. Non si accumulano riassunti.
- Turno fallito (limite degli strumenti, errore del modello): cronologia e riassunto di
  `Sessione` restano quelli di prima; il riassunto fatto all'inizio del turno si perde e si rifà
  al turno seguente (costo accettato).
- Tutto ciò che `Sessione` fa oggi resta: in cronologia entrano solo domanda, chiamate di
  `STRUMENTI_IN_CRONOLOGIA` con i loro risultati e risposta finale ripulita con la nota; le
  risposte respinte dal revisore e le indicazioni non entrano mai (§18.12). Il calcolo di che cosa
  aggiungere va adattato: dopo il riassunto la cronologia nel grafo è più corta di quella di
  `Sessione`, quindi non si può più usare `len(self.cronologia)` come punto di partenza del turno.

### 19.3 Grafo

Percorso principale (dall'utente): `START → riassunto → router → agente → revisore → END`. Con
gli archi esistenti:

```
START → riassunto → router ──(fuori_ambito)──→ rifiuto → END
                           └─(conversazione o router non valido)──→ agente ⇄ strumenti
                                                                     │ (risposta finale)
                                                                     ▼
                                                                 revisore ──→ END | agente
```

- **riassunto** (nuovo, LLM): primo nodo, si esegue **a ogni turno**, anche per le domande poi
  rifiutate dal router (il riassunto riguarda la cronologia, non la domanda nuova). Arco fisso
  verso il router.
- Router, agente, strumenti, revisore, rifiuto e i loro archi **invariati**, salvo il riassunto
  nel loro contesto (§19.6). `inizio_turno` resta calcolato dal router, che gira dopo il
  riassunto, quindi sulla cronologia già accorciata.
- Il limite di ricorsione si alza di uno (super-step del riassunto).
- `costruisci_grafo` riceve il modello del riassunto e i parametri della soglia come
  dipendenze, così i test iniettano un modello finto.

### 19.4 Soglia e taglio

**Configurazione.** Variabili d'ambiente in
`config.py`, facoltative con valore predefinito, validate come `MAX_REVISIONI` (errore all'avvio
che nomina la variabile):

| Variabile | Contenuto | Predefinito |
|---|---|---|
| `RIASSUNTO_SOGLIA_TIPO` | `messaggi` oppure `token` | `token` |
| `RIASSUNTO_SOGLIA` | intero ≥ 1: messaggi, o token stimati, oltre i quali si riassume | `5000` |
| `RIASSUNTO_TURNI_DA_TENERE` | intero ≥ 1: ultimi turni completi conservati interi (N) | `3` |

*Nomi delle variabili: scelta mia.* *Aggiornato il 2026-11-17 (deciso dall'utente):* predefiniti realistici token/5000/3; i valori bassi (messaggi/10/2) restano per le prove e le misure.

**Che cosa si conta (scelta mia).** I messaggi dello stato all'ingresso del nodo **esclusi il
prompt di sistema e il riassunto**, compresa la domanda nuova: domande, risposte, chiamate agli
strumenti e loro risultati, rifiuti. In modalità `token` la stima è **caratteri / 4**
(arrotondata per eccesso) sul testo dei messaggi più gli argomenti delle chiamate, senza
librerie nuove. La soglia scatta quando il conteggio è **maggiore** del valore.

**Turno.** Un turno comincia con un messaggio dell'utente (`HumanMessage`) e comprende tutto ciò
che segue fino al messaggio dell'utente successivo: chiamate, `ToolMessage`, risposta finale o
rifiuto fisso.

**Taglio (requisito 4).** Sopra la soglia si conservano interi la domanda nuova e gli **ultimi N
turni completi** prima di essa; tutto ciò che sta prima va al riassunto. Il punto di taglio è
sempre l'inizio di un turno, cioè un `HumanMessage`: una chiamata e il suo `ToolMessage` stanno
sempre nello stesso turno, quindi non vengono mai separati. *Scelta mia:* il taglio si calcola in
una funzione pura testabile a parte, e un controllo verifica che nella parte conservata ogni
tool_call abbia il suo `ToolMessage` e viceversa. Se il controllo fallisce (non dovrebbe mai
succedere), si tratta come un guasto del riassunto (§19.5): cronologia intera, `WARNING`, il turno
prosegue.

**Casi limite (scelte mie):**
- sopra la soglia ma con N turni o meno prima della domanda (per esempio turni lunghi con molti
  strumenti): niente da togliere, **nessuna chiamata al modello**, riga di log che lo dice;
- c'è un riassunto precedente ma la cronologia è sotto la soglia: il riassunto resta com'è,
  nessuna chiamata.

### 19.5 Il modello del riassunto

- **Stesso modello** di LM Studio, **senza strumenti**, ragionamento disattivato, timeout proprio
  di 60 s e `max_retries=0`, come router e revisore. Output in **testo libero** (non serve output
  strutturato), ripulito con `pulisci_ragionamento`.
- **Ingresso:** istruzioni del riassunto, il **riassunto precedente** (se c'è) e i **messaggi
  tolti** presentati in testo (domande, risposte, chiamate agli strumenti con il loro nome).
  **Uscita:** un unico riassunto nuovo che **sostituisce** il precedente e ne conserva le
  informazioni ancora utili (requisito 3).
- **Che cosa conservare (deciso con l'utente):** dati personali e preferenze dell'utente (il nome,
  «rispondimi in miglia»), gli argomenti e i dati delle domande fatte (per esempio «ha chiesto di
  convertire 5 miglia in km»), così che un seguito dopo la compressione funzioni ancora; le
  richieste fuori ambito che sono state rifiutate, annotate come rifiutate (*scelta mia*: altrimenti
  un seguito come «e quella dell'amatriciana?» non avrebbe più contesto per il router, §17.2).
- **Che cosa non conservare (scelta mia, approvata in linea di principio dall'utente):** i
  **risultati** degli strumenti (orari, conversioni, calcoli, date). Riportati nel riassunto,
  l'agente potrebbe riusarli a mente e il revisore li respingerebbe come `valore_a_mente`; per un
  seguito basta sapere che cosa era stato chiesto. Se le misure mostrano che serve, si possono
  segnare come «già calcolati», con una decisione dell'utente.
- Riassunto breve, in italiano, in terza persona (*scelta mia*; lunghezza indicativa nelle
  istruzioni, da affinare con le misure).
- **Guasto (scelta mia, come router e revisore: fail-open):** eccezione, timeout o testo vuoto →
  cronologia **non** accorciata, riassunto precedente invariato, `WARNING riassunto: …`, il turno
  prosegue.

### 19.6 Chi vede il riassunto (scelta mia)

Il riassunto **non è un messaggio della cronologia**: vive solo nel campo `riassunto` dello stato
e ogni nodo lo aggiunge al proprio contesto al momento della chiamata.
- **Agente:** in coda al prompt di sistema, per esempio «Riassunto della conversazione
  precedente: …», così resta un solo messaggio di sistema in testa (*scelta mia*: alcuni modelli
  locali rifiutano un secondo messaggio di sistema in mezzo alla conversazione; da verificare al
  primo controllo reale).
- **Router:** nelle sue istruzioni o prima della cronologia che già vede, per capire i seguiti
  dopo la compressione.
- **Revisore:** tra gli scambi precedenti, così non contesta come inventato un dato (il nome) che
  arriva dal riassunto. Le regole del revisore non cambiano.
- Senza riassunto i messaggi inviati ai tre nodi restano **identici** a oggi.

### 19.7 Log (livello INFO salvo dove indicato)

- Una riga per turno dal nodo riassunto, con i messaggi prima e dopo (evidenza dell'utente), per
  esempio:
  - sotto la soglia: `INFO riassunto: 6 messaggi, sotto la soglia (10), nessuna chiamata`;
  - sopra la soglia: `INFO riassunto: 12 -> 5 messaggi (tolti 7, conservati 2 turni)`;
  - niente da togliere: `INFO riassunto: 13 messaggi, sopra la soglia (10) ma niente da togliere, nessuna chiamata`;
  - in modalità `token` la riga riporta anche i token stimati prima e dopo.
- Guasto: `WARNING riassunto: risposta non valida (…), cronologia invariata`.
- DEBUG: messaggi inviati al modello del riassunto e testo del riassunto nuovo.
- Le righe esistenti di router, agente, rifiuto e revisore restano.

### 19.8 Evidenze richieste

Dall'utente:
1. **Log con il numero di messaggi prima e dopo il riassunto** (§19.7).
2. **Un'informazione data al primo turno, come il nome dell'utente, è usata dopo la
   compressione.**
3. **Sotto la soglia il nodo non chiama il modello.**

*Scelte mie, su come produrle:*
- 1 e 3: test automatici con modello finto che conta le chiamate, più il log dell'app vera;
- 2: test reale (LM Studio) e prova con l'app vera via stdin: «mi chiamo …» al primo turno, poi
  abbastanza turni (anche con strumenti) da far scattare la compressione, poi una domanda che usa
  il nome; si verifica nel log che il primo turno sia stato tolto e nella risposta che il nome sia
  giusto.

**Ambito allargato (deciso dall'utente il 2026-11-16).** Con l'ambito di §17.2 il router potrebbe
rifiutare «come mi chiamo?» come fuori ambito, e l'evidenza 2 fallirebbe per colpa del router.
`AMBITO_ASSISTENTE` (in `.env.example` e nel `.env` locale) si allarga con le domande su ciò che
l'utente ha detto nella conversazione (per esempio il suo nome o le sue preferenze). Testo esatto
lasciato al costruttore, purché resti su una riga e non apra la chiacchiera libera. Va verificato
che il router classifichi `conversazione` le domande sulla conversazione e che le domande del
tutto fuori ambito delle misure del router (§17.9) restino `fuori_ambito`.

### 19.9 Test e verifiche

- **Automatici (modelli finti, nessun LM Studio):**
  - sotto la soglia → modello del riassunto mai chiamato, messaggi invariati, riga di log;
  - sopra la soglia → chiamato una volta, conservati domanda nuova e ultimi N turni, tolto il
    resto, `riassunto` nello stato sostituito (non aggiunto), riga di log con prima e dopo;
  - il riassunto precedente arriva al modello insieme ai messaggi tolti;
  - taglio con turni pieni di chiamate e `ToolMessage` (anche più chiamate in un messaggio): mai
    una chiamata separata dal suo risultato; caso «niente da togliere»;
  - modalità `token`: stima e soglia; validazione delle tre variabili in `config.py`;
  - guasto del modello del riassunto → cronologia intera, WARNING, il turno prosegue;
  - agente, router e revisore ricevono il riassunto quando c'è, e messaggi identici a oggi quando
    non c'è;
  - `Sessione`: dopo un turno riuscito conserva cronologia accorciata e riassunto nuovo; dopo un
    turno fallito entrambi invariati; la cronologia continua a non contenere risposte respinte né
    indicazioni; la nota non normativa resta data una sola volta per chat anche dopo che il turno
    che l'ha consegnata è finito nel riassunto (lo stato è in `NotaNonNormativa`, non cambia), e
    la ricerca dei risultati di `compute_deadline` del turno usa il nuovo punto di partenza;
  - test esistenti aggiornati al grafo nuovo, tutti verdi.
- **Reali (LM Studio, `RUN_REAL_TESTS=1`):** il nome del primo turno usato dopo la compressione;
  un seguito («e in piedi?») dopo che la domanda a cui si riferisce è finita nel riassunto; con
  l'ambito allargato il router vero classifica `conversazione` «come mi chiamo?» e simili, e le
  domande fuori ambito restano `fuori_ambito`; i test reali esistenti restano verdi.
- **Primo controllo reale:** formato del prompt dell'agente con il riassunto accettato da LM Studio
  e testo del riassunto (che cosa conserva, che cosa perde, se contiene risultati).
- **Misure (dal controllore, app vera via stdin):** conversazioni lunghe (almeno 15 turni, più
  sessioni) con nome, preferenze, seguiti e strumenti; si contano: informazioni del primo turno
  usate correttamente dopo la compressione, seguiti riusciti dopo la compressione, risultati a
  mente o rifiuti del revisore causati dal riassunto, guasti del riassunto, tempo aggiunto per
  turno. Numeri all'utente e nel README; nessuna soglia bloccante.
- **Regressione:** le 15 domande della regressione prima (sull'albero attuale = `2eea005`, **prima
  di toccare il codice**, senza worktree) e dopo; criterio: esiti non peggiori. Con la soglia a 10 messaggi la regressione stessa farà scattare il riassunto.
- **Docker:** `docker compose build`, poi una conversazione che supera la soglia nel container.
- **Chi misura:** il controllore in sessione, numeri di prima mano.

### 19.10 Obiettivi

- Nodo riassunto LLM all'inizio del turno, con soglia configurabile (messaggi o token stimati) e
  ultimi N turni conservati interi.
- Riassunto come campo dello stato, sostituito a ogni compressione.
- Taglio sempre all'inizio di un turno, mai tra una chiamata e il suo risultato.
- Le evidenze di §19.8, prodotte e riportate.

### 19.11 Non-obiettivi

- Persistenza della cronologia o del riassunto oltre la sessione; checkpointer di LangGraph.
- Un conteggio esatto dei token con il tokenizzatore del modello.
- Un modello diverso per il riassunto o una configurazione del modello separata.
- Cambiare le regole del router o del revisore (l'ambito allargato di §19.8 è configurazione, non
  una regola nuova).

### 19.12 Anti-obiettivi (sarebbe un fallimento anche se «funziona»)

- Informazioni importanti del primo turno perse dopo la compressione.
- L'assistente che risponde a mente usando valori presi dal riassunto invece di chiamare gli
  strumenti, o un revisore che rifiuta più spesso per colpa del riassunto.
- Una chiamata a uno strumento separata dal suo `ToolMessage` (errore dell'API o del template).
- Riassunti che si accumulano invece di sostituirsi.
- Il modello del riassunto chiamato sotto la soglia, o un guasto del riassunto che blocca il turno.
- Un turno fallito che lascia la cronologia accorciata o il riassunto cambiato.
- Router, agente, revisore e strumenti che cambiano comportamento quando non c'è riassunto.

### 19.13 Vincoli di lavoro

- Solo in `lezione_4/`, sul branch `feature/nuove-funzionalita`; la §16 non committata resta
  intatta e fuori da questo lavoro (commit parziale di `specs.md`).
- **Commit e push solo su richiesta esplicita dell'utente.**
- Aggiornare `CLAUDE.md` (struttura e obiettivo), `README.md` (variabili nuove, log, misure), la
  descrizione del grafo in testa a `grafo.py`, `.env.example` e la regola della cronologia in §6.2
  (rimando a questa sezione).

### 19.14 Lasciato al costruttore

- Nomi interni (funzioni, modulo, per esempio `assistente/riassunto.py`), salvo il campo
  `riassunto` dello stato.
- Testo delle istruzioni del riassunto e presentazione dei messaggi tolti, da affinare con le
  misure (al massimo 3 giri di ritocco, si tiene il migliore).
- Come il nodo toglie i messaggi dallo stato (per esempio `RemoveMessage` per id, o sostituzione
  dell'intera lista) e come `Sessione` ricava la cronologia nuova, purché valga §19.2.
- Formato esatto delle righe di log, purché contengano quanto in §19.7.

## 20. RAG, parte 1: ingestion e ricerca sul ricettario dell'Artusi — aggiunto il 2026-11-23

Stato: approvata dall'utente il 2026-11-23, implementata il 2026-11-23 (misure in
`docs/retrieval.md`); piano:
`docs/superpowers/plans/2026-11-23-rag-ingestion-ricerca.md`. Branch `RAG`, creato da
`i-tre-nodi` (`38d2c05`) su decisione dell'utente. Riferimento: lezione 7, Esercizio 1 (slide
`LLM_Lez_7.pdf`). La lezione 8 (ricerca come tool MCP dell'agente, citazioni, astensione,
riscrittura, reranking, soglie) e l'Esercizio 2 della lezione 7 (modifiche A «contiene_dosi» e
B «titolo nel testo indicizzato») sono passi successivi, fuori da questa sezione.

### 20.1 Intento

Prima parte del RAG dell'assistente: costruire un **indice vettoriale ripetibile** del ricettario
di Pellegrino Artusi (*La scienza in cucina e l'arte di mangiar bene*, Project Gutenberg n. 59047)
e una **ricerca semantica verificabile** che, data una domanda su una qualunque ricetta,
restituisca i passaggi pertinenti con la loro fonte (ricetta, capitolo, posizione del chunk).

Perché adesso (dalle slide): ricerca e generazione si separano; se il passaggio giusto non viene
recuperato, nessun prompt al modello generativo può compensarlo. Qui si misura solo il recupero:
il modello generativo non entra in gioco, l'agente e il grafo (§17–§19) non cambiano.

Criteri dell'utente:
1. nella repository: la cartella del progetto (`lezione_4/`) e il `CLAUDE.md` con le regole stabili;
2. brainstorming e specifica con Superpowers a partire dai requisiti; specifica letta e approvata;
3. piano e implementazione con test, un passo alla volta, con commit (li propongo io a fine passo,
   decide l'utente);
4. avviare Qdrant e LM Studio ed eseguire l'ingestion completa **due volte**;
5. valutare la ricerca sulle domande con fonte attesa: è la situazione di partenza;
6. alla fine, domande di prova **scritte senza copiare le parole del testo**.

### 20.2 Corpus (deciso con l'utente)

- Fonte: il file fornito dall'utente
  `…/ADDIS/argomenti verifica agente+tool+nodi+RAG/Ricettario.txt` (UTF-8, CRLF, ~1 MB, edizione
  Gutenberg 59047), copiato in `lezione_4/dati/artusi.txt`. **`dati/` resta fuori da Git**
  (`.gitignore`). Il percorso del file viene dalla configurazione (predefinito
  `dati/artusi.txt`).
- **Si indicizzano solo le 790 ricette numerate** (dall'utente: «le domande possono riguardare
  qualunque ricetta»). Restano fuori: intestazione e licenza Gutenberg, «La storia di un libro»,
  prefazione, «Spiegazione di voci», lettere, introduzioni dei capitoli (per esempio il testo
  sotto «MINESTRE» o «Qualità e stagione dei pesci»), l'appendice «La cucina per gli stomachi
  deboli» (dopo la ricetta 790, dalla riga `APPENDICE`) e l'indice.
- **Ogni ricetta è un documento** con `numero` (1–790), `titolo` (il testo dopo «N. » sulla riga
  del titolo, per esempio «Cappelletti all'uso di Romagna») e `capitolo`.
- **Riconoscere i titoli (osservato nel file):** una riga «N. Titolo» è l'inizio di una ricetta
  solo se N è **il numero successivo** alla ricetta precedente e la riga sta prima
  dell'appendice. Nel file ci sono falsi positivi da scartare: righe del corpo che iniziano con
  un numero («137. Mettete il composto…», «1533. Aggiungeva…») e righe dell'indice nell'appendice
  («227. Scaloppine alla livornese p. 228. …»). Alcuni titoli hanno un numero romano in fondo
  («Minestra di semolino composta I», «Fritto alla romana I»): fa parte del titolo.
- **Capitoli:** elenco chiuso, ricavato dalle intestazioni in maiuscolo prima della prima ricetta
  di ciascun capitolo e scritto in forma leggibile (prima lettera maiuscola, come nelle slide:
  «Minestre asciutte e di magro»). Intestazioni osservate: Brodi, gelatina e sughi; Minestre in
  brodo; Minestre asciutte e di magro; Principii; Salse; Uova; Paste e pastelle; Ripieni; Fritti;
  Lesso; Tramessi; Umidi; Rifreddi; Erbaggi e legumi; Piatti di pesce; Arrosti; Pasticceria;
  Torte e dolci al cucchiaio; Siroppi; Conserve; Liquori; Gelati; Cose diverse. Non sono capitoli
  le righe in maiuscolo dentro le ricette («PASTA FROLLA», «RICETTA A», «PRIMA RICETTA», «RICETTA
  DI DETTA ZUPPA PER SEI PERSONE») né la sovra-intestazione «MINESTRE». Con «Uova» (intestazione
  `UOVA` prima della ricetta 139, trovata nella revisione) sono i **23 capitoli** della slide; il
  costruttore conferma l'elenco sul file e lo fissa nel codice e nei test; ogni ricetta deve
  avere un capitolo dell'elenco.
- **Pulizia:** righe spezzate a ~70 caratteri riunite in paragrafi (i paragrafi sono separati da
  righe vuote); spazi normalizzati; CRLF → LF; i marcatori di corsivo Gutenberg (`_parola_`)
  tolti dal testo; gli elenchi degli ingredienti (righe rientrate) restano su righe proprie, una
  per ingrediente. Il titolo **non** entra nel testo del chunk (resta nel payload): è la
  configurazione di partenza dell'aula; il titolo nel testo indicizzato è la futura modifica B.
- **Verifica del corpus:** 790 ricette, numerazione 1–790 senza buchi né doppioni, ogni ricetta
  con titolo, capitolo e testo non vuoti.

### 20.3 Chunking (deciso con l'utente: configurazione dell'aula)

- Prima si divide **per ricetta**; una ricetta che sta nella dimensione massima è **un solo chunk**.
- Le ricette più lunghe si dividono **ai paragrafi**: si accumulano paragrafi interi finché non si
  supera la dimensione; un paragrafo da solo più lungo della dimensione si divide a finestra
  (preferibilmente a fine frase). Tra due chunk consecutivi della stessa ricetta si ripetono
  **circa 200 caratteri** (l'overlap, preso dalla fine del chunk precedente, possibilmente da un
  confine di frase o di parola).
- Valori predefiniti: **dimensione 1200 caratteri, overlap 200**, strategia `paragrafi`; tutti e
  tre configurabili. Strategia alternativa `finestra` (ogni N caratteri con overlap, senza
  guardare i paragrafi), richiesta dalla slide «strategia configurabile» e utile ai confronti
  futuri; non è usata nella valutazione di partenza.
- Un chunk non contiene mai testo di due ricette diverse.
- Validazione: dimensione > 0, 0 ≤ overlap < dimensione, strategia nell'elenco; altrimenti errore
  chiaro all'avvio.
- Misure osservate sul file: ricetta mediana ~900 caratteri, 90° percentile ~1.900, circa 230
  ricette oltre i 1.200 caratteri.

### 20.4 Embedding (scelta mia, confermata dalla presenza del modello)

- Modello di embedding servito da **LM Studio** sull'host, endpoint `/v1/embeddings` dello stesso
  server di `LM_BASE_URL`. Modello predefinito in `.env.example`:
  `text-embedding-nomic-embed-text-v1.5` (già installato e caricato; è quello delle slide della
  lezione 8). **Il nome del modello sta nella configurazione (`EMBEDDING_MODEL`), mai nel codice.**
- **Stesso modello e stessa configurazione** per chunk e domande.
- Embedding dei chunk **a lotti** (dimensione del lotto configurabile o fissa, scelta del
  costruttore).
- Testo inviato all'embedder: il testo del chunk così com'è e la domanda così com'è, senza
  prefissi (configurazione di partenza dell'aula). *Scelta mia:* i prefissi consigliati da Nomic
  (`search_document:` / `search_query:`) restano una possibile modifica futura da misurare, non
  entrano ora.
- La dimensione dei vettori si ricava dal modello (prima risposta dell'embedder), non si scrive a
  mano.

### 20.5 Qdrant

- **Servizio `qdrant` in `compose.yaml`** di `lezione_4`, immagine con versione fissata, porta
  6333, **volume persistente** (la collezione sopravvive al riavvio del container). L'ingestion e
  la ricerca girano sull'host e raggiungono Qdrant con `QDRANT_URL` (predefinito
  `http://localhost:6333`). Il servizio `assistente` resta com'è.
- Collezione `QDRANT_COLLECTION` (predefinito `ricette`), distanza **coseno**, dimensione dei
  vettori = quella del modello.
- **Modello registrato nella collezione:** nome del modello di embedding (e dimensione) salvati
  nei metadati della collezione alla creazione. **Cambio bloccato:** se la collezione esiste ed è
  stata creata con un altro modello o un'altra dimensione, ingestion e ricerca si fermano con un
  errore chiaro che indica i due modelli e come ripartire (cancellare la collezione o usarne
  un'altra). Se la versione di Qdrant non supporta i metadati di collezione, il costruttore
  sceglie un'alternativa equivalente e la documenta.
- **Un punto per chunk**, con payload:
  `ricetta` (numero), `titolo`, `capitolo`, `posizione` (indice del chunk nella ricetta, da 0),
  `testo` (il testo del chunk), `fonte` (riferimento leggibile al libro, per esempio «Artusi, La
  scienza in cucina e l'arte di mangiar bene»), `documento_id` (per esempio `ricetta-089`). Nomi
  in italiano come nell'esempio della slide; nomi esatti lasciati al costruttore purché ci siano
  queste informazioni.
- **Indici sul payload** per i campi filtrati: `capitolo` (keyword) e `ricetta` (intero).
- **Ripetibilità (strategia A delle slide: ID stabili e upsert):** l'ID del punto è un UUID
  deterministico (per esempio UUID v5) ricavato da documento e posizione del chunk; rieseguire
  l'ingestion sostituisce i punti (upsert) invece di aggiungerne. **Punti obsoleti:** se cambia il
  chunking e una ricetta produce meno chunk, i punti in più vanno rimossi a fine ingestion (per
  esempio cancellando i punti della collezione il cui ID non è tra quelli appena scritti).
- **Controllo:** il numero di punti è lo stesso dopo la prima e dopo la seconda ingestion completa.

### 20.6 Ingestion: script separato

- Comando `python -m rag.ingestion` (da `lezione_4/`). **Non è uno strumento dell'agente** e non
  gira a ogni domanda: si esegue quando il corpus o il chunking cambiano.
- Passi ispezionabili (dalle slide): caricare → pulire → dividere in ricette → chunking →
  metadati → embedding a lotti → upsert → rimozione dei punti obsoleti.
- Uscita su terminale / log INFO: ricette trovate, chunk prodotti (con min/medio/max dei
  caratteri), modello e dimensione dei vettori, punti nella collezione **prima** e **dopo**,
  punti rimossi, tempo totale.
- Il corpus viene verificato (§20.2) **prima** di calcolare embedding: se la numerazione non è
  completa, l'ingestion si ferma senza scrivere niente.
- Errori previsti con messaggio chiaro e senza traceback: file assente, Qdrant non raggiungibile
  (suggerire `docker compose up -d qdrant` e `QDRANT_URL`), LM Studio o modello di embedding non
  disponibili, modello diverso da quello della collezione.

### 20.7 Ricerca

- Funzione di ricerca nel pacchetto `rag` (usata da valutazione e, nella lezione 8, dal server
  MCP) e comando `python -m rag.ricerca "domanda" [--k N] [--capitolo NOME]`.
- La domanda viene trasformata in embedding così com'è, con lo stesso modello; si chiedono a
  Qdrant i k punti più vicini.
- **k:** predefinito 5; **massimo imposto dal codice** (predefinito 10, configurabile); k fuori
  dall'intervallo 1–massimo viene riportato nell'intervallo e la riduzione è segnalata.
  Domanda vuota → errore chiaro.
- **Filtro per capitolo applicato durante la ricerca** (condizione inviata a Qdrant, non filtro
  dopo): tutti i risultati appartengono al capitolo richiesto. Capitolo non presente nell'elenco
  chiuso → errore chiaro con l'elenco dei valori validi.
- Ogni risultato riporta: posizione in classifica, score, ricetta (numero e titolo), capitolo,
  posizione del chunk, testo. Uscita del comando leggibile su terminale.
- Con k uguale e indice invariato la ricerca è deterministica: due esecuzioni danno gli stessi
  risultati.

### 20.8 Valutazione con fonte attesa

- File delle domande in Git (per esempio `rag/domande_valutazione.json`): per ogni domanda il
  testo e le **ricette attese** (uno o più numeri; lista vuota = il libro non contiene la
  risposta).
- Domande di partenza (quelle viste in aula, con fonte controllata leggendo il testo):
  - «Quanta farina serve per 400 grammi di patate negli gnocchi?» → ricetta 89;
  - «Che vino si usa per il pollo alla cacciatora?» → ricetta 208;
  - «Come si chiama il cacciucco sulle coste dell'Adriatico?» → ricette 455–456;
  - «Quanti cappelletti bastano a un mangiatore moderato?» → ricetta 7;
  - «Perché gli gnocchi possono sciogliersi nell'acqua?» → ricetta 89;
  - «Qual è la ricetta del tiramisù?» → nessuna (non compare nel libro).
  Numeri delle ricette da confermare sul file prima di registrarli.
- **Domande di prova proprie (criterio 6 dell'utente):** almeno tre, **scritte da me e controllate
  dall'utente prima di lanciare la ricerca** (deciso dall'utente: il piano ha una pausa per la sua
  approvazione), alla fine, **senza copiare le parole del testo** (sinonimi, parafrasi, linguaggio di oggi), con la fonte attesa
  decisa **prima** di eseguire la ricerca e controllata leggendo la ricetta; almeno una senza
  risposta nel libro. Si aggiungono al file e alla tabella.
- Comando `python -m rag.valutazione [--k 5]`: esegue tutte le domande e stampa una **tabella
  riproducibile**: domanda, fonte attesa, posizione della prima fonte attesa nei primi k
  («assente» se non c'è), score di quel risultato, miglior score, ricetta in prima posizione.
  In fondo: fonte trovata in *x* casi su *y* domande con risposta; score migliori delle domande
  senza risposta (per confronto, nessuna soglia).
- Criterio della slide: la fonte attesa compare tra i primi k **e il chunk contiene davvero
  l'informazione**. Il secondo punto lo verifica il controllore leggendo il testo restituito
  (annotato nel resoconto); il comando misura solo il primo.
- La tabella della valutazione di partenza (k = 5) e i conteggi delle due ingestion vanno in
  `docs/retrieval.md`, con il comando per riprodurli e due query commentate.

### 20.9 Configurazione (variabili d'ambiente, in `.env.example`)

`LM_BASE_URL` (già esistente, condiviso), `EMBEDDING_MODEL`, `QDRANT_URL`, `QDRANT_COLLECTION`,
`RAG_CORPUS` (percorso del file), `CHUNK_STRATEGIA` (`paragrafi` | `finestra`), `CHUNK_DIMENSIONE`,
`CHUNK_OVERLAP`, `RICERCA_K_MAX`. Valori predefiniti come sopra; valori non validi → errore chiaro
all'avvio. La configurazione del RAG è separata da quella dell'assistente: l'assistente non deve
richiederla per avviarsi.

### 20.10 Evidenze richieste (dall'utente)

1. **Specifica e piano nella repository** (questa sezione; piano in
   `docs/superpowers/plans/2026-11-23-rag-ingestion-ricerca.md`).
2. **Test superati con i servizi spenti** (Qdrant e LM Studio spenti): embedder finto e Qdrant in
   memoria (`QdrantClient(":memory:")` o equivalente del client).
3. **Stesso numero di punti dopo le due ingestion** complete reali.
4. **Tabella della valutazione di partenza.**
5. **Domande di prova** proprie, senza le parole del testo, valutate.

### 20.11 Test e verifiche

- **Automatici (nessun servizio):**
  - corpus: 790 ricette, numerazione 1–790 senza buchi, falsi positivi scartati (righe di esempio
    del file), titolo e capitolo di alcune ricette note (per esempio 7, 89, 208, 790), licenza e
    appendice escluse, corsivi tolti; un estratto piccolo del file nei test, più un test sul
    file vero se presente in `dati/` (saltato se manca);
  - chunking: **una ricetta breve** → un chunk; **una ricetta lunga** → più chunk, nessuno oltre
    la dimensione (salvo il caso documentato), overlap presente, posizioni 0..n-1, nessun testo di
    altre ricette; strategia `finestra`; validazione dei parametri;
  - ID stabili: stesso chunk → stesso ID; chunk diversi → ID diversi;
  - ingestion con embedder finto e Qdrant in memoria: punti = chunk; **due ingestion → stesso
    numero di punti**; punti obsoleti rimossi quando il chunking cambia; payload completo; indici
    sul payload creati; modello registrato; **cambio di modello bloccato** con errore chiaro;
    corpus incompleto → nessuna scrittura;
  - ricerca: ordinamento per score, k predefinito, **k oltre il massimo ridotto**, k < 1, domanda
    vuota, **filtro per capitolo: tutti i risultati del capitolo richiesto**, capitolo
    sconosciuto → errore con elenco;
  - valutazione: posizione della fonte attesa, «assente», domande senza risposta, formato della
    tabella (con un indice finto preparato);
  - configurazione: valori predefiniti e non validi;
  - la suite esistente dell'assistente resta verde.
- **Reali (controllore, servizi accesi):** `docker compose up -d qdrant`; LM Studio con il modello
  di embedding; ingestion completa due volte con i conteggi; una ricerca con filtro per capitolo
  (per esempio «Come si frigge il pollo?» `--capitolo Fritti --k 3`); valutazione di partenza;
  riavvio del container Qdrant e controllo che la collezione sia ancora lì; domande di prova.
- Eventuali test reali automatici solo con `RUN_REAL_TESTS=1`, come per l'assistente.

### 20.12 Obiettivi

- Corpus pulito e verificato: 790 ricette con numero, titolo, capitolo.
- Chunking per ricetta e paragrafi, configurabile.
- Ingestion ripetibile senza duplicati, con modello registrato e cambio bloccato.
- Ricerca top-k con massimo imposto e filtro per capitolo durante la ricerca.
- Valutazione di partenza riproducibile con un comando.

### 20.13 Non-obiettivi

- Generazione di risposte, agente, server MCP di ricerca, citazioni, astensione (lezione 8).
- Riscrittura della domanda, reranking, soglie sullo score.
- Modifiche A (`contiene_dosi`) e B (titolo nel testo indicizzato) dell'Esercizio 2.
- Indicizzare le parti del libro che non sono ricette.
- Confronti tra strategie di chunking o tra modelli di embedding (estensioni).

### 20.14 Anti-obiettivi (sarebbe un fallimento anche se «funziona»)

- Una seconda ingestion che raddoppia i punti, o risultati duplicati nella ricerca.
- Ricette mancanti, unite o spezzate tra due documenti; testo di due ricette nello stesso chunk.
- Un risultato di cui non si sa dire ricetta, capitolo e posizione del chunk.
- Il nome del modello di embedding scritto nel codice, o domande e documenti con modelli diversi.
- Filtro per capitolo applicato dopo la ricerca (meno di k risultati) o risultati di altri capitoli.
- Test che richiedono Qdrant o LM Studio accesi per passare.
- Il testo del libro o `.env` dentro Git.
- Una valutazione «a sensazione»: fonti attese decise dopo aver visto i risultati.
- L'assistente esistente che cambia comportamento o non parte più.

### 20.15 Vincoli di lavoro

- Solo in `lezione_4/`, sul branch `RAG`. La §16 non committata di `specs.md`, `COPIONE.md` e la
  modifica locale di `docs/superpowers/handoff.md` restano fuori dai commit del RAG; anche il
  testo del ricettario (`Ricettario.txt` / `dati/artusi.txt`) non entra mai in Git (deciso
  dall'utente).
- Commit un passo alla volta: a fine passo verificato **propongo io** il commit con un messaggio
  suggerito; **decide l'utente** (nessun commit o push senza il suo ordine).
- Dipendenza nuova `qdrant-client`, con versione fissata in `requirements.txt` (ed eventuali
  dipendenze indirette fissate come le altre); versione dell'immagine di Qdrant fissata in
  `compose.yaml`. Attenzione a Smart App Control (dipendenze binarie: vedi le note su `jiter` e
  `uuid_utils`). *Scelta mia:* il primo passo del piano installa `qdrant-client` e prova
  l'import e la modalità in memoria; se Smart App Control blocca qualcosa, mi fermo e chiedo
  all'utente (nessun ripiego deciso da solo: versioni più vecchie, finto scritto a mano o API REST).
- Aggiornare `CLAUDE.md` con le regole stabili del RAG: ingestion come script separato, modello di
  embedding dalla configurazione, Qdrant con Docker Compose, dati scaricati fuori da Git, test a
  servizi spenti, branch `RAG`; togliere «RAG non va anticipato» dai confini. Aggiornare
  `README.md` (avvio di Qdrant, comandi, variabili) e `.env.example`.

### 20.16 Lasciato al costruttore

- Struttura interna del pacchetto `rag/` (moduli, nomi di funzioni), purché i tre comandi
  `rag.ingestion`, `rag.ricerca`, `rag.valutazione` esistano.
- Dimensione dei lotti di embedding; formato esatto delle stampe e dei log.
- Come registrare il modello nella collezione (metadati della collezione o alternativa
  equivalente), purché il cambio sia bloccato.
- Dettagli della pulizia non elencati, purché i testi restino fedeli al libro.
- Versione esatta di `qdrant-client` e dell'immagine di Qdrant (compatibili tra loro).


## 21. RAG, parte 2: miglioramento del retrieval (quattro leve misurate) — aggiunto il 2026-11-23

Stato: decisa con l'utente il 2026-11-23 (domande nuove e leve 1–4 in ordine), che ha chiesto di
procedere in autonomia senza fermarsi per le approvazioni; implementata e misurata il
2026-11-23 (leve tenute: titolo nel testo, riscrittura, bge-m3; prefissi tolti); piano:
`docs/superpowers/plans/2026-11-23-rag-leve-retrieval.md`. Branch `RAG`. Misure in
`docs/retrieval.md`.

### 21.1 Intento

La valutazione della §20 mostra che la ricerca trova la fonte solo quando la domanda usa le parole
del libro (3 su 5 domande d'aula) e mai quando le parafrasa (0 su 4 domande proprie, la migliore
98ª). Lo scopo è capire **quale leva migliora davvero il retrieval**, misurandole una alla volta
sulle stesse domande, e tenere solo quelle che migliorano.

### 21.2 Domande di valutazione (decise con l'utente)

- Alle 11 domande della §20 se ne aggiungono **8 nuove**, fissate **prima** di ogni misura: 4 con
  le parole del libro (Minestrone 47, Salsa verde 119/120, Arrosto d'agnello all'aretina 529,
  Ponce alla romana 770) e 4 parafrasate senza parole significative in comune con titolo e testo
  della ricetta (Torta di noci 637, Zuppa tartara 676, Mandorle tostate 785, Fagiuolini con
  l'odore di vainiglia 382). Controllo delle parole fatto con uno script.
- Totale: 19 domande, 17 con fonte attesa e 2 senza risposta (tiramisù, guacamole). Le domande
  non si cambiano durante le misure.
- Misura principale: fonte attesa nei primi 5; si riportano anche i primi 10 e lo score migliore
  delle due domande senza risposta.

### 21.3 Le leve, in ordine (deciso con l'utente)

Ogni leva si aggiunge alla configurazione migliore trovata fino a quel punto (*scelta mia:* si
tiene se aumenta le fonti nei primi 5, a parità si guardano i primi 10; altrimenti si toglie
prima della leva successiva). Ogni configurazione ha la **sua collezione Qdrant**, così le
precedenti restano per il confronto e nessuna viene sovrascritta (*scelta mia*).

1. **Prefissi di Nomic:** `search_document: ` davanti al testo dei chunk, `search_query: ` davanti
   alla domanda (sono i prefissi con cui il modello è addestrato). Collezione `ricette_prefissi`.
2. **Titolo e capitolo nel testo indicizzato** (modifica B dell'Esercizio 2, lezione 7): il testo
   che diventa vettore è «titolo — capitolo», riga vuota, testo del chunk. Il payload `testo`
   resta il chunk originale (*scelta mia*). Collezione `ricette_titolo`.
3. **Riscrittura della domanda** (lezione 8): prima della ricerca il modello di chat di LM Studio
   riscrive la domanda con il lessico del ricettario (nome probabile del piatto, ingredienti con i
   termini del libro). Si cerca con **domanda originale + riscrittura** (*scelta mia:* la domanda
   originale non va persa se la riscrittura sbaglia). Ragionamento del modello disattivato,
   temperatura 0. Non richiede una nuova ingestion.
4. **Modello di embedding multilingue:** `text-embedding-bge-m3` (scelto con l'utente, già
   caricato in LM Studio), senza prefissi (bge-m3 non li usa), con le leve 2 e 3 se tenute.
   Collezione `ricette_bge`.

### 21.4 Configurazione (nuove variabili, tutte facoltative, predefiniti = comportamento §20)

`EMBEDDING_PREFISSO_DOCUMENTO`, `EMBEDDING_PREFISSO_DOMANDA` (vuote: nessun prefisso; il codice
aggiunge lo spazio dopo il prefisso), `INDICE_CON_TITOLO` (`si`/`no`, predefinito `no`),
`RICERCA_RISCRITTURA` (`si`/`no`, predefinito `no`), `RISCRITTURA_MODEL` (obbligatoria solo se la
riscrittura è attiva; identificativo restituito da `GET /v1/models`, mai nel codice). Valori non
validi → errore chiaro all'avvio.

### 21.5 Coerenza tra indice e ricerca

- Alla creazione la collezione registra nei metadati, oltre a modello e dimensione,
  `prefisso_documento`, `prefisso_domanda` e `titolo_nel_testo`. Una collezione della §20 senza
  queste chiavi vale come «nessun prefisso, senza titolo».
- Ingestion e ricerca si fermano con un errore chiaro se la configurazione corrente è diversa da
  quella registrata (stesso trattamento del cambio di modello): indicano i valori registrati e
  quelli correnti e suggeriscono un'altra `QDRANT_COLLECTION` o una nuova ingestion.

### 21.6 Riscrittura: errori e uscita

- LM Studio spento o modello di chat non disponibile → errore chiaro, senza traceback.
- Si tolgono eventuali blocchi `<think>…</think>`; si tiene la prima riga non vuota. Riscrittura
  vuota → si cerca con la sola domanda originale.
- La ricerca stampa la domanda effettivamente cercata; la valutazione elenca le riscritture sotto
  la tabella.

### 21.7 Evidenze

- Tabella di confronto in `docs/retrieval.md`: una riga per configurazione (partenza, +prefissi,
  +titolo, +riscrittura, bge-m3) con fonti nei primi 5 e nei primi 10 (totale, domande con parole
  del libro, domande parafrasate) e score delle domande senza risposta; tabella completa della
  configurazione migliore; commento su che cosa ha aiutato e che cosa no.
- Per ogni nuova collezione: numero di punti uguale a 1106 dopo l'ingestion.
- Test automatici a servizi spenti: embedder e riscrittore finti, Qdrant in memoria.

### 21.8 Non-obiettivi e anti-obiettivi

- Niente generazione della risposta, niente strumento MCP, niente reranking (lezione 8, dopo).
- Non si cambiano le domande dopo aver visto i risultati, né si scrivono regole su misura per
  singole domande: sarebbe un miglioramento finto.
- La collezione `ricette` della §20 non si tocca; i predefiniti restano quelli della §20.

### 21.9 Lasciato al costruttore

Testo esatto del prompt di riscrittura, nomi delle funzioni, formato della riga «titolo —
capitolo», forma della tabella di confronto.


## 22. RAG, parte 3: modifica A (campo `contiene_dosi`) e chiusura della modifica B — aggiunto il 2026-11-23

Stato: approvata dall'utente il 2026-11-23 (procedere in autonomia), implementata e misurata il
2026-11-23; la §22.3 sostituisce la regola della §21.5 per l'ingestion; piano:
`docs/superpowers/plans/2026-11-23-rag-esercizio-2.md`. Branch `RAG`. Riferimento: lezione 7, Esercizio 2 (slide «due
modifiche alla pipeline»), modifiche A e B.

### 22.1 Intento

Chiudere l'Esercizio 2. La modifica B (titolo nel testo indicizzato) è già misurata nella §21, ma
in una collezione nuova: la slide chiede invece che l'ingestion ricalcoli i chunk **senza ricreare
la collezione** e senza aumentare i punti. La modifica A aggiunge un metadato utile alle domande
sulle quantità («quanta farina…», «quanti grammi…»): cercare solo tra i chunk che contengono un
elenco di ingredienti con le dosi.

### 22.2 Modifica A: il campo `contiene_dosi` (requisiti della slide)

- **Definizione** (*scelta mia, da confermare*): un chunk contiene le dosi se ha **almeno due righe
  in forma di elenco di ingredienti**: riga che comincia con l'ingrediente, poi una virgola e una
  quantità (`grammi`, `N.`, `decilitri`, `litri`, `chilogrammi`, numeri scritti in lettere come
  «mezzo», «due»…). Esempio: «Patate grosse e gialle, grammi 400.» e «Farina, grammi 150.». Le
  dosi citate nel discorso («versate grammi 500 di carne…») non contano: la slide parla di
  «elenco di ingredienti». Sul corpus attuale: **397 chunk su 1106, di 346 ricette** (*corretto
  in implementazione:* la riga deve essere corta, al più 90 caratteri, per escludere la prosa con
  una virgola, e il nome dell'ingrediente può contenere virgole, come «Magro di manzo nella
  coscia, senz'osso, grammi 500»; la stima della bozza era 385/338).
- **Payload:** campo booleano `contiene_dosi` in ogni punto, scritto dall'ingestion.
- **Indice sul payload:** `contiene_dosi` di tipo booleano, creato con la collezione e, per le
  collezioni esistenti, dal comando di aggiornamento.
- **Punti esistenti senza ricalcolare gli embedding:** nuovo comando
  `python -m rag.metadati` che legge i punti della collezione (`QDRANT_COLLECTION`), calcola il
  campo dal testo nel payload e lo scrive con l'aggiornamento del solo payload (nessuna chiamata
  a LM Studio, vettori invariati). Rieseguibile: dà lo stesso risultato. Stampa quanti punti hanno
  il campo vero e falso.
- **Filtro nella ricerca:** opzione `--solo-dosi` di `rag.ricerca` (e parametro `solo_dosi` di
  `cerca`). Condizione inviata a Qdrant durante la ricerca, combinata in `must` con il filtro per
  capitolo. Con il filtro tutti i risultati hanno `contiene_dosi` vero, al massimo k.
- **Collezione senza il campo** (ricerca con `--solo-dosi` prima di `rag.metadati`): errore chiaro
  che indica di eseguire `python -m rag.metadati`, invece di una lista vuota muta.

### 22.3 Modifica B: ricalcolo senza ricreare la collezione

- Cambia la regola della §21.5 per l'**ingestion**: se prefissi o `INDICE_CON_TITOLO` sono
  diversi da quelli registrati, l'ingestion **non si ferma**: ricalcola tutti i vettori nella
  stessa collezione (stessi ID, upsert, punti invariati) e alla fine aggiorna le impostazioni
  registrate. Il cambio di **modello o dimensione resta bloccato** (i vettori non sarebbero
  confrontabili).
- Durante il ricalcolo la collezione è segnata «ingestion incompleta» nei metadati; il segno si
  toglie a fine ingestion. La **ricerca** si ferma con un errore chiaro se il segno c'è (vettori
  misti) o se le impostazioni registrate sono diverse dalla configurazione (come nella §21.5).
- Evidenza: nuova collezione `ricette_b` indicizzata con la configurazione di partenza, poi
  ingestion con `INDICE_CON_TITOLO=si` sulla stessa collezione: punti prima e dopo uguali (1106),
  impostazioni registrate aggiornate, valutazione uguale a quella di `ricette_titolo`.
- Un test verifica il testo passato all'embedder (già presente dalla §21).

### 22.4 Valutazione (consegna: partenza, dopo A, dopo B)

- **Dopo A:** `rag.valutazione` riceve l'opzione `--solo-dosi`, che applica il filtro a tutte le
  domande. Si misura su `ricette` (configurazione di partenza) con e senza filtro, sulle 19
  domande. *Atteso:* le domande sulle quantità restano trovate o salgono, mentre le domande senza
  dosi (cacciucco, ponce…) possono sparire: il filtro serve solo quando la domanda chiede le
  dosi, e la tabella lo mostra.
- **Dopo B:** la misura della §21 (configurazione 2), ripetuta su `ricette_b`.
- In `docs/retrieval.md`: una sezione «Esercizio 2» con partenza, dopo A e dopo B, e i conteggi
  dell'aggiornamento dei metadati.

### 22.5 Test (a servizi spenti)

- Riconoscimento delle dosi: elenco vero (gnocchi), dosi solo nel discorso (falso), una sola riga
  (falso), testo senza dosi (falso).
- Ingestion: ogni punto ha `contiene_dosi`; indice creato.
- `rag.metadati`: aggiunge il campo a punti che non l'hanno, **vettori identici prima e dopo**,
  nessuna chiamata all'embedder, rieseguibile, numero di punti invariato.
- Ricerca: con `solo_dosi` tutti i risultati hanno il campo vero e sono al più k; combinata con il
  capitolo; collezione senza il campo → errore.
- Modifica B: ingestion con titolo su una collezione indicizzata senza titolo → stessi punti,
  impostazioni aggiornate; modello diverso ancora bloccato; ricerca bloccata con «ingestion
  incompleta».

### 22.6 Non-obiettivi e vincoli

- Nessun cambio alle domande di valutazione. Nessun riconoscimento delle dosi con il modello di
  chat (regola sul testo, ripetibile e testabile).
- Le collezioni esistenti restano; `rag.metadati` si esegue su tutte e quattro più `ricette_b`.
- Commit: la slide chiede «modifiche A e B ciascuna con test e commit». Si decide con l'utente
  come dividere i commit (vedi resoconto).
