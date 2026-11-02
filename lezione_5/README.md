# Assistente del laboratorio — lezione 4

Chat da terminale in Python che conversa con un modello servito da **LM Studio** sul computer
host. Il flusso è un grafo **LangGraph** esplicito (nodo `modello` → nodo `strumenti` → di
nuovo `modello`), la cronologia dura quanto la sessione e il modello può chiedere l'ora con lo
strumento **`get_current_time`**, che richiede sempre un fuso orario IANA (es. `Asia/Tokyo`).

Specifica: [`specs.md`](specs.md) · Piano: [`implementation_plan.md`](implementation_plan.md)

## Struttura

```
assistente/
  config.py     variabili d'ambiente (.env)
  log.py        log su stderr
  orologio.py   strumento get_current_time
  strumenti.py  esecuzione sicura delle chiamate agli strumenti
  modello.py    client verso LM Studio (API compatibile OpenAI)
  grafo.py      grafo LangGraph modello ⇄ strumenti con limite di passaggi
  sessione.py   cronologia della sessione e prompt di sistema
  terminale.py  chat da terminale (python -m assistente)
tests/          test automatici (senza modello) e prova reale (test_reale.py)
```

## Requisiti

- Python 3.12 (verificato con 3.12.10).
- LM Studio con il server attivo su `http://localhost:1234` e un modello caricato
  (predefinito `qwen/qwen3.5-9b`).
- Per l'avvio con Docker: Docker Desktop con Compose.

## Configurazione

Da `lezione_4/`, in PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

`requirements.txt` contiene solo le dipendenze di esecuzione (versioni fissate);
`requirements-dev.txt` aggiunge `pytest`. Il file `.env` resta fuori da Git.

| Variabile | Obbligatoria | Esempio | Significato |
|---|---|---|---|
| `LM_BASE_URL` | sì | `http://localhost:1234/v1` | indirizzo dell'API di LM Studio, con `/v1` |
| `LM_MODEL` | sì | `qwen/qwen3.5-9b` | identificativo restituito da `GET /v1/models` |
| `MAX_TOOL_STEPS` | no | `3` | passaggi modello → strumenti per ogni domanda |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO` o `WARNING` |

Per vedere gli identificativi dei modelli disponibili:

```powershell
(Invoke-RestMethod http://localhost:1234/v1/models).data.id
```

Il ragionamento di Qwen è disattivato (`reasoning_effort: "none"`): con il ragionamento attivo
LM Studio a volte spostava la risposta finale in un campo che il client scarta, e la risposta
arrivava vuota. Dettagli in `specs.md` §6.1.

## Avvio

### Locale

```powershell
.\venv\Scripts\python.exe -m assistente
```

Per uscire: `esci`, `exit`, Ctrl+D o Ctrl+C. Le righe di log (stderr) mostrano ogni chiamata
allo strumento, per esempio:

```
23:14:50 INFO strumenti: passo 1/3 get_current_time {"timezone": "Asia/Tokyo"} -> lunedì 2 novembre 2026, 07:14:50 — Asia/Tokyo (UTC+09:00)
```

### Docker

LM Studio resta sull'host; il container lo raggiunge su `http://host.docker.internal:1234/v1`
(impostato in `compose.yaml`, sovrascrive `LM_BASE_URL` del `.env`).

```powershell
docker compose build
docker compose run --rm assistente
```

L'immagine contiene solo `assistente/` e `requirements.txt` e gira come utente non-root `app`;
il `.env` viene letto solo all'avvio. L'orario delle righe di log nel container è in UTC
(l'ora restituita dallo strumento no: il fuso è sempre esplicito).

## Test

Test automatici, senza modello (grafo, cronologia, instradamento, strumento con istante
controllato):

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

Prova reale con LM Studio acceso (separata, va attivata esplicitamente):

```powershell
$env:RUN_REAL_TESTS="1"; .\venv\Scripts\python.exe -m pytest -m reale -v -s
Remove-Item Env:RUN_REAL_TESTS
```

Verifica che il modello chiami davvero lo strumento con `Asia/Tokyo` e dia una risposta finale
non vuota (circa 20 s con Qwen).

### Prova manuale guidata

Avviare la chat (locale o Docker) e scrivere:

1. `Ciao, mi chiamo Elia` → saluto, nessuna riga di log dello strumento.
2. `Che ore sono a Tokyo?` → riga di log con `Asia/Tokyo` e ora riportata.
3. `e a Roma?` → riga di log con `Europe/Rome`.
4. `Come mi chiamo?` → «Elia» (cronologia della sessione).
5. `esci` → `Ciao!`.

Limite noto: al punto 3 il modello a volte (circa 1 volta su 6 nelle prove) non chiama lo
strumento e calcola l'ora da quella di Tokyo, anche sbagliando. La riga di log permette di
accorgersene: senza riga, l'ora non viene dallo strumento.

## Diagnosi

| Sintomo | Causa probabile | Cosa fare |
|---|---|---|
| `Impossibile contattare il modello su http://...: Connection error.` | LM Studio spento, server non avviato o indirizzo sbagliato | avviare il server in LM Studio; controllare `LM_BASE_URL` (porta e `/v1`) |
| `Impossibile contattare il modello su http://localhost:1234: Unexpected endpoint or method. ...` | `LM_BASE_URL` senza `/v1` | aggiungere `/v1` all'indirizzo |
| `Configurazione non valida: Variabile d'ambiente mancante: LM_MODEL` | `lezione_4/.env` assente o incompleto (viene letto solo quello della cartella del progetto) | `Copy-Item .env.example .env` e compilarlo |
| `Configurazione non valida: LOG_LEVEL deve essere uno tra ...` | valore di `LOG_LEVEL` non riconosciuto | usare `DEBUG`, `INFO` o `WARNING` |
| `Errore dal modello (HTTP 400): ...` | il server ha risposto con un errore, per esempio cronologia più lunga del contesto del modello dopo una sessione molto lunga | riavviare la chat (la cronologia riparte da zero) o aumentare il contesto del modello in LM Studio |
| Risponde un modello diverso da quello atteso | `LM_MODEL` non corrisponde a un identificativo reale: LM Studio risponde comunque con il modello caricato, senza errore | confrontare `LM_MODEL` con `(Invoke-RestMethod http://localhost:1234/v1/models).data.id` |
| Nel container: errore di connessione | il container non raggiunge l'host | avviare con `docker compose run --rm assistente` (usa `host.docker.internal` e `extra_hosts` di `compose.yaml`); verificare che LM Studio sia acceso sull'host |
| Risposte lente (15–60 s) | modello locale da 9B su CPU/GPU dell'host; la prima domanda carica il modello | normale; con `LOG_LEVEL=DEBUG` si vedono i messaggi inviati e la durata di ogni chiamata |
| `(nessuna risposta dal modello)` | il modello ha restituito un testo vuoto | riprovare; con `LOG_LEVEL=DEBUG` si vede l'esito di ogni chiamata (`chiamata -> risposta finale (7.6s)` o richiesta di strumento) |
