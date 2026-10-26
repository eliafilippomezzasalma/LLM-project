# Assistente del laboratorio con orologio — Specifica

Data: 2026-10-26 · Cartella: `lezione_4/` · Stato: approvata

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
  conoscere l'ora attuale e di non riutilizzare orari citati in precedenza.
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
- Le librerie esterne (`httpx`, `openai`, `langchain*`, `langgraph`) sono portate a WARNING,
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
