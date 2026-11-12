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
- Di un turno riuscito la cronologia conserva **solo** il messaggio dell'utente e la risposta
  finale; `AIMessage` con tool_call e `ToolMessage` restano visibili nei log ma non vengono
  salvati. Così un orario vecchio non resta nel contesto e, a domande come «e adesso?», il
  modello deve richiamare lo strumento.
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
  aggiunge la risposta allo stato.
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
- cronologia: il secondo turno riceve domanda e risposta finale del primo (senza tool_call né
  `ToolMessage`); un turno fallito o interrotto dal limite non sporca la cronologia;
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
  oggi (l'ora non va riusata).
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
