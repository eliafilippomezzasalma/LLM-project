# Assistente del laboratorio — lezione 4

Chat da terminale in Python che conversa con un modello servito da **LM Studio** sul computer
host. Il flusso è un grafo **LangGraph** esplicito (nodo `modello` → nodo `strumenti` → di
nuovo `modello`), la cronologia dura quanto la sessione e il modello può chiedere l'ora con lo
strumento **`get_current_time`**, che richiede sempre un fuso orario IANA (es. `Asia/Tokyo`).
Può anche convertire unità di misura con lo strumento **`convert_units`**, offerto da un server
**MCP** separato (`convertitore.py`) che l'assistente avvia da solo all'avvio.

Specifica: [`specs.md`](specs.md) · Piano: [`implementation_plan.md`](implementation_plan.md)
· Convertitore: [specifica](docs/superpowers/specs/2026-11-02-convertitore-mcp-design.md),
[piano](docs/superpowers/plans/2026-11-02-convertitore-mcp.md)

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
  mcp_remoto.py ponte sincrono verso un server MCP avviato via stdio
convertitore.py server MCP del convertitore di unità (python convertitore.py)
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

### Convertitore di unità (MCP)

All'avvio l'assistente lancia `convertitore.py` come processo figlio e ci parla con il
protocollo MCP su stdin/stdout; l'intestazione della chat dice se è `attivo` o
`non disponibile` (in quel caso la chat funziona comunque, con il solo orologio). Il server
viene chiuso all'uscita.

Unità ammesse (elenco chiuso, nello schema dello strumento):

| Grandezza | Unità |
|---|---|
| lunghezza | `mm` `cm` `m` `km` `in` `ft` `mi` |
| massa | `g` `kg` `lb` `oz` |
| tempo | `s` `min` `h` |
| temperatura | `°C` `°F` `K` |
| volume | `ml` `l` `gal` (gallone USA) |
| velocità | `m/s` `km/h` `mph` |

Sono accettate anche alcune varianti fisse (maiuscole, `miglia`, `celsius`, `kph`…), ricondotte
al simbolo ufficiale. Lo schema Pydantic `RichiestaConversione` fa tutta la validazione e
risponde con errori in italiano: unità fuori elenco, grandezze diverse (`kg` → `m`), valore non
numerico, temperatura sotto lo zero assoluto. Esempio di riga di log:

```
23:20:11 WARNING strumenti: passo 1/3 convert_units {"value": 5, "from_unit": "kg", "to_unit": "m"} -> Errore: impossibile convertire 'kg' (massa) in 'm' (lunghezza): grandezze diverse
```

Il server si può avviare anche da solo con `.\venv\Scripts\python.exe convertitore.py`: resta in
attesa di messaggi MCP su stdin e termina quando l'input si chiude.

### Docker

LM Studio resta sull'host; il container lo raggiunge su `http://host.docker.internal:1234/v1`
(impostato in `compose.yaml`, sovrascrive `LM_BASE_URL` del `.env`).

```powershell
docker compose build
docker compose run --rm assistente
```

L'immagine contiene solo `assistente/`, `convertitore.py` e `requirements.txt` e gira come utente non-root `app`;
il `.env` viene letto solo all'avvio. L'orario delle righe di log nel container è in UTC
(l'ora restituita dallo strumento no: il fuso è sempre esplicito).

## Test

Test automatici, senza modello (grafo, cronologia, instradamento, strumento con istante
controllato, convertitore e server MCP vero avviato via stdio):

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

Prova reale con LM Studio acceso (separata, va attivata esplicitamente):

```powershell
$env:RUN_REAL_TESTS="1"; .\venv\Scripts\python.exe -m pytest -m reale -v -s
Remove-Item Env:RUN_REAL_TESTS
```

Verifica che il modello chiami davvero lo strumento con `Asia/Tokyo` e dia una risposta finale
non vuota (circa 20 s con Qwen), e che usi `convert_units` per «Converti 10 km in miglia» (risultato
6,21) e che per «Converti 5 kg in metri» non inventi un risultato.

### Prova manuale guidata

Avviare la chat (locale o Docker) e scrivere:

1. `Ciao, mi chiamo Elia` → saluto, nessuna riga di log dello strumento.
2. `Che ore sono a Tokyo?` → riga di log con `Asia/Tokyo` e ora riportata.
3. `e a Roma?` → riga di log con `Europe/Rome`.
4. `Come mi chiamo?` → «Elia» (cronologia della sessione).
5. `Converti 10 km in miglia` → riga di log con `convert_units` e circa 6,21 miglia.
6. `Converti 5 kg in metri` → riga di log `WARNING` con l'errore; l'assistente spiega che non si può.
7. `esci` → `Ciao!`.

Limite noto: al punto 3 il modello a volte (circa 1 volta su 6 nelle prove) non chiama lo
strumento e calcola l'ora da quella di Tokyo, anche sbagliando. La riga di log permette di
accorgersene: senza riga, l'ora non viene dallo strumento.

Convertitore e cronologia: le chiamate a `convert_units` (con il loro risultato) restano nella
cronologia della sessione, quelle all'orologio no. Senza questi esempi, dopo una dozzina di
domande il modello smetteva di chiamare lo strumento e rispondeva a mente; il prompt di sistema
contiene anche due esempi di richieste da passare comunque allo strumento («anni luce», «-300 °C»).
Prove del 2026-11-03 (Docker, Qwen 3.5 9B): sessione lunga di 19 domande con tutte le 13 conversioni
fatte dallo strumento, errori compresi; casi di errore in sessione nuova 11 volte su 12 (una volta
«10 litri in chilogrammi» è stata rifiutata a mente, senza numeri inventati). La riga di log dice
sempre se il risultato o l'errore viene dallo strumento.

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
| `Convertitore di unità (MCP): non disponibile` nell'intestazione | il server `convertitore.py` non è partito (dipendenza `mcp` mancante, file assente nell'immagine) | `pip install -r requirements.txt`; provare `python convertitore.py` per vedere l'errore; il motivo è anche nella riga di log `convertitore MCP non disponibile` |
| `Errore: server MCP non raggiungibile` nel log | il server del convertitore si è interrotto durante la chat | riavviare l'assistente (non c'è riavvio automatico) |
| `(nessuna risposta dal modello)` | il modello ha restituito un testo vuoto | riprovare; con `LOG_LEVEL=DEBUG` si vede l'esito di ogni chiamata (`chiamata -> risposta finale (7.6s)` o richiesta di strumento) |
