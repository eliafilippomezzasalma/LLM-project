# Assistente del laboratorio — lezione 4

Chat da terminale in Python che conversa con un modello servito da **LM Studio** sul computer
host. Il flusso è un grafo **LangGraph** esplicito (nodo `modello` → nodo `strumenti` → di
nuovo `modello`), la cronologia dura quanto la sessione e il modello può chiedere l'ora con lo
strumento **`get_current_time`**, che richiede sempre un fuso orario IANA (es. `Asia/Tokyo`).
Può anche convertire unità di misura con lo strumento **`convert_units`**, offerto da un server
**MCP** separato (`convertitore.py`) che l'assistente avvia da solo all'avvio.
Per i conti usa la **calcolatrice sicura** `calculate` (`calcolatrice.py`, un secondo server MCP, senza `eval`).
Per date e scadenze usa i **sei strumenti dei giorni e delle scadenze** (`scadenze.py`, un terzo server MCP, con le festività italiane in `festivita.json`).

Specifica: [`specs.md`](specs.md) · Piano: [`implementation_plan.md`](implementation_plan.md)
· Giorni e scadenze: specifica in [`specs.md`](specs.md) §15
· Calcolatrice: specifica in [`specs.md`](specs.md) §14, [piano](docs/superpowers/plans/2026-11-03-calcolatrice-mcp.md)
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
calcolatrice.py server MCP della calcolatrice sicura (python calcolatrice.py)
scadenze.py     server MCP di giorni e scadenze (python scadenze.py), legge festivita.json
festivita.json  festività italiane 2020–2040 (le uniche date di festività del progetto)
assistente/nota.py  nota «calcolo indicativo» da dare una sola volta per chat
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

### Calcolatrice sicura (MCP)

Come il convertitore, `calcolatrice.py` è un server MCP che l'assistente lancia all'avvio; i due
server sono indipendenti e l'intestazione dice di ciascuno se è `attivo` o `non disponibile`
(`Calcolatrice (MCP): ...`). Lo strumento `calculate` riceve l'espressione come testo e **non usa
`eval`**: un piccolo analizzatore scritto a mano riconosce solo ciò che è consentito.

Accetta: numeri interi e decimali (virgola o punto, `3,5` = `3.5`), `+` `-` `*` `/`, la potenza `^`
(anche `**`; `×` e `÷` valgono `*` e `/`), le parentesi tonde e il segno davanti a un numero.
Precedenza matematica (`-2^2` = -4), aritmetica esatta (`0,1 + 0,2` = 0.3). Esempi: `(3,5 + 2) * 4` = 22, `2^10` = 1024.

Rifiuta con un messaggio `Errore: ...` in italiano (nessun numero inventato):

| Rifiuto | Esempio | Messaggio |
|---|---|---|
| divisione per zero | `10 / 0` | `Errore: divisione per zero` |
| forma indeterminata | `0^0` | `Errore: 0^0 è una forma indeterminata` |
| base negativa, esponente non intero | `(-8)^0,5` | `Errore: potenza con base negativa ed esponente non intero non supportata` |
| risultato troppo grande | `10^1000` | `Errore: risultato troppo grande (oltre 10^100)` |
| risultato troppo piccolo | `10^-1000` | `Errore: risultato troppo piccolo (sotto 10^-100)` |
| carattere non consentito | `2 x 3` | `Errore: carattere non consentito 'x' in posizione 3: ...` |
| numero scritto male | `3,5,2` | `Errore: numero scritto male '3,5,2' in posizione 1` |
| operando mancante | `3 + * 2` | `Errore: manca un numero in posizione 5` |
| operatore mancante | `2 3` | `Errore: manca un operatore prima di '3' in posizione 3` |
| parentesi non chiusa | `(1 + 2` | `Errore: parentesi aperta in posizione 1 non chiusa` |
| espressione troppo lunga | oltre 200 caratteri | `Errore: espressione troppo lunga (massimo 200 caratteri)` |

Esempio di riga di log di un rifiuto:

```
23:25:40 WARNING strumenti: passo 1/3 calculate {"expression": "10 / 0"} -> Errore: divisione per zero
```

Il server si può avviare anche da solo con `.\venv\Scripts\python.exe calcolatrice.py`: resta in
attesa di messaggi MCP su stdin e termina quando l'input si chiude.

Uso dello strumento misurato il 2026-11-03 (locale, Qwen 3.5 9B, due giri): la calcolatrice è stata
chiamata **in tutti i 44 calcoli**: 24 domande in sessione nuova su due giri (12 valide, 12 da
rifiutare: `10 / 0`, `5 / (3 - 3)`, `0^0`, `2^1000`, «radice di 16»...) e due sessioni lunghe da 20
domande miste (10 calcoli, più conversioni, orari e chiacchiere): 40 domande su 40 con lo strumento
giusto, compresi tutti e 20 i calcoli. Il prompt dice anche di non usare `calculate` per le
conversioni: in un giro, per «1 parsec in km», il modello aveva convertito da solo con `calculate`
(sbagliando poi il risultato); dopo l'aggiunta di questa regola chiama `convert_units`, che rifiuta
l'unità.

Dopo un rifiuto il modello spiega il motivo e **si ferma**: non dà il risultato a mente né riscrive
l'operazione per aggirare l'errore. Le funzioni non ammesse (radice, seno, logaritmo…) vanno comunque
mandate a `calculate` (per «radice di 16» con `sqrt(16)`), che le rifiuta. Il prompt non elenca ciò che
la calcolatrice non supporta: con quella descrizione il modello rispondeva da solo senza chiamarla
(1 volta su 10 con lo strumento) e dava comunque il risultato. Misura del 2026-11-03 col prompt attuale:
radice di 16 ×6, seno di 30 ×2, logaritmo di 1000 ×2 → strumento sempre chiamato e nessun risultato
nella risposta (10/10); controlli `10 / 0`, `2^10`, `(3,5 + 2) * 4` corretti.

### Giorni e scadenze (MCP)

`scadenze.py` è il terzo server MCP lanciato all'avvio; come gli altri è indipendente e l'intestazione dice
se è `attivo` o `non disponibile` (`Giorni e scadenze (MCP): ...`). Ha sei strumenti: `compute_deadline`,
`add_business_days`, `count_business_days`, `days_between`, `date_info`, `list_holidays`. Non conosce la data di
oggi (se serve, il modello la chiede prima a `get_current_time`) e non calcola la Pasqua: le festività sono
solo quelle di `festivita.json` (12 per anno, il 4 ottobre solo dal 2026).

Domande supportate (un esempio per gruppo):

| Gruppo | Esempio |
|---|---|
| Scadenza da data e durata | «Ho firmato l'affitto il 15/03/2024, dura 4 anni: quando scade?» (anche all'indietro: «preavviso di 6 mesi rispetto al 31/12/2026») |
| Giorni lavorativi | «Quanti giorni lavorativi ci sono tra il 1° e il 30 novembre?» |
| Differenza tra date | «Quanti giorni mancano al 25/12/2026?» |
| Informazioni su una data | «Il 2 giugno 2027 è festivo?», «Quali sono le festività di dicembre 2026?» |

Regole. Non lavorativi: sabato, domenica e festività. Se una scadenza (gruppo A) cade in un giorno non
lavorativo, in avanti si sposta al primo giorno lavorativo successivo, all'indietro (preavviso) al giorno
lavorativo precedente; la risposta riporta data calcolata, motivo e data finale. I giorni sono di calendario,
i mesi a fine mese si fermano all'ultimo giorno del mese. Intervallo coperto: dal 2020-01-01 al 2040-12-31.
Le date si scrivono solo in formato ISO `AAAA-MM-GG` (le converte il modello) e nei risultati compare anche il giorno
della settimana. La **nota** «calcolo indicativo, non ha valore legale.» accompagna la prima scadenza della chat:
se il modello non la riporta, la sessione la aggiunge in fondo alla risposta; dalle scadenze successive viene tolta dai
risultati. Se il turno fallisce (errore del modello, limite di passaggi) la nota non conta come data e ricompare.

Rifiuta con un messaggio `Errore: ...` in italiano (nessuna data inventata):

| Rifiuto | Esempio | Messaggio |
|---|---|---|
| formato non ISO | `15/03/2024` | `Errore: data '15/03/2024' non valida: usa il formato AAAA-MM-GG, es. 2024-03-15` |
| data inesistente | `2026-02-30` | `Errore: la data '2026-02-30' non esiste` |
| fuori intervallo | `2041-01-01` | `Errore: data 2041-01-01 fuori dall'intervallo coperto: posso calcolare solo date tra il 2020-01-01 e il 2040-12-31` |
| quantità non valida | 0 giorni | `Errore: la quantità deve essere un numero intero da 1 in su` |
| unità fuori elenco | `hours` | `Errore: unità non valida: usa days, business_days, weeks, months o years` |
| direzione fuori elenco | `sideways` | `Errore: direzione non valida: usa forward o backward` |
| intervallo rovesciato | fine prima dell'inizio | `Errore: la data finale 2026-11-01 viene prima di quella iniziale 2026-11-30` |
| mese non valido | mese 13 | `Errore: mese non valido: usa un numero da 1 a 12` |
| anno non valido | 2041 | `Errore: anno non valido: posso calcolare solo date tra il 2020-01-01 e il 2040-12-31` |

Il server si può avviare anche da solo con `.\venv\Scripts\python.exe scadenze.py`: resta in attesa di messaggi
MCP su stdin e termina quando l'input si chiude; se `festivita.json` manca o è rovinato esce con codice 1 e un
messaggio `scadenze: ...` su stderr.

Misure del 2026-11-09 (locale, Qwen 3.5 9B, prompt attuale):
- **16 domande in sessione nuova** (i quattro gruppi, date scritte in formati diversi, 2045 e 30/02 da
  rifiutare): strumento giusto **15/16** (una volta «che giorno della settimana è il 15/03/2028?» è stata
  risolta a mente, con risposta giusta); risposta con **tutte** le date in ISO **11/16** (prima del ritocco
  del prompt 3/16). Le date calcolate dallo strumento sono riportate in ISO; quelle che il modello riprende
  dalla domanda («dal 1° gennaio 2026», «rispetto al 31/12/2026») restano a volte nel formato dell'utente.
- **Catena orologio → scadenze** («quanti giorni mancano al 25/12/2026?», «che giorno sarà fra 10 giorni
  lavorativi?» ×3): **6/6** con `get_current_time` e poi lo strumento giusto.
- **Domande da oggi dopo una data citata** (prima «ho firmato l'affitto il 15/03/2024…», poi «mancano»,
  «fra N giorni lavorativi», «sono passati dal…»). Prima del ritocco il modello prendeva la data dell'affitto
  come oggi («mancano 1015 giorni» invece di 46) in 2 sessioni su 6. Dopo il ritocco (regola esplicita più esempi
  di chiamata; 8 sessioni, metà con parole e date diverse dagli esempi): «mancano» **8/8** con l'orologio e
  risposta giusta; «fra N giorni lavorativi» 7/8 con l'orologio, 8/8 giuste; «sono passati» solo **1/8** con
  l'orologio, 7/8 giuste. Il modello riprende di solito il 2026-11-09 dalla propria chiamata precedente; una
  volta si è inventato oggi = 2024-11-09 (62 giorni invece di 668). Un terzo giro (regola spostata accanto a
  quella dell'orologio) non ha ridotto le risposte sbagliate (1 su 24 anche lì), ha reso le frasi meno pulite
  e ha fatto saltare lo strumento per il 2045 in 2 prove su 6 (0 su 5 con il prompt attuale): è stato scartato.
- **Regressione dopo il ritocco** (sessione nuova per ogni domanda): calcolatrice e convertitore **12/12** con lo
  strumento (kg→m ×2, parsec, 10 km, `10 / 0` ×3, radice di 16 ×2, `2^10`, `(3,5 + 2) * 4`, litri→kg). Nella
  prova guidata completa (15 domande di seguito) gli strumenti sono stati chiamati tutti in Docker. In locale
  invece «5 kg in metri» e «10 / 0» sono stati rifiutati a mente, senza valori inventati ma scrivendo «lo
  strumento indica…».
- **Nota**: prima della correzione il modello la riportava solo in 0–2 scadenze su 5; ora, aggiunta dalla
  sessione quando manca, compare alla prima scadenza e non alle due successive (2 sessioni su 2).
- **Sessione lunga** di 20 domande miste (scadenze, calcoli, conversioni, orari, chiacchiere): **19/20** con lo
  strumento giusto; l'eccezione è «Il 2045-01-01 che giorno è?», rifiutata a mente senza date inventate.
- **Regressione** sugli altri strumenti: calcolatrice 6/6 (radice di 16 ×3, `10 / 0`, `2^10`, `(3,5 + 2) * 4`),
  convertitore 8/9 (una volta «1 parsec in km» rifiutato a mente, senza numeri inventati).

Il ritocco del prompt ha richiesto tre giri: un esempio di risposta già pronta («Sì, il 2027-06-02 è
festivo…») faceva rispondere il modello **senza** strumento (12/16, una volta con una data sbagliata);
nel prompt restano solo esempi di chiamata.

### Docker

LM Studio resta sull'host; il container lo raggiunge su `http://host.docker.internal:1234/v1`
(impostato in `compose.yaml`, sovrascrive `LM_BASE_URL` del `.env`).

```powershell
docker compose build
docker compose run --rm assistente
```

L'immagine contiene solo `assistente/`, `convertitore.py`, `calcolatrice.py`, `scadenze.py`, `festivita.json` e `requirements.txt` e gira come utente non-root `app`;
il `.env` viene letto solo all'avvio. L'orario delle righe di log nel container è in UTC
(l'ora restituita dallo strumento no: il fuso è sempre esplicito).

## Test

Test automatici, senza modello (grafo, cronologia, instradamento, strumento con istante
controllato, convertitore, calcolatrice, scadenze e server MCP veri avviati via stdio):

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
6,21) e che per «Converti 5 kg in metri» non inventi un risultato. Per la calcolatrice: «Quanto fa
(3,5 + 2) * 4?» deve passare da `calculate` (22) e «Quanto fa 10 / 0?» deve **chiamare** `calculate`
(test severo) e non dare un numero. I quattro casi con strumenti MCP avviano orologio, convertitore e calcolatrice.

### Prova manuale guidata

Avviare la chat (locale o Docker) e scrivere:

1. `Ciao, mi chiamo Elia` → saluto, nessuna riga di log dello strumento.
2. `Che ore sono a Tokyo?` → riga di log con `Asia/Tokyo` e ora riportata.
3. `e a Roma?` → riga di log con `Europe/Rome`.
4. `Come mi chiamo?` → «Elia» (cronologia della sessione).
5. `Converti 10 km in miglia` → riga di log con `convert_units` e circa 6,21 miglia.
6. `Converti 5 kg in metri` → riga di log `WARNING` con l'errore; l'assistente spiega che non si può.
7. `Quanto fa (3,5 + 2) * 4?` → riga di log con `calculate` e risposta 22.
8. `Quanto fa 10 / 0?` → riga di log `WARNING` con `Errore: divisione per zero`; l'assistente lo spiega senza dare un numero.
9. `Ho firmato l'affitto il 15/03/2024, dura 4 anni: quando scade?` → riga di log con `compute_deadline`, data riportata in formato `AAAA-MM-GG` e la nota «calcolo indicativo, non ha valore legale.».
10. `Quanti giorni mancano al 25/12/2026?` → prima `get_current_time` con `Europe/Rome`, poi `days_between`; risposta con «mancano».
11. `Il 30/02/2026 è festivo?` → riga di log `WARNING` con `Errore: ...`; l'assistente spiega e non dà una data.
12. una seconda scadenza nella stessa chat → senza nota.
13. `esci` → `Ciao!`.

Limite noto: al punto 3 il modello a volte non chiama lo strumento e calcola l'ora da quella di
Tokyo, spesso sbagliando (misure del 2026-11-03: 17 chiamate su 24, sia con sia senza la parte del
prompt sulla calcolatrice). La riga di log permette di
accorgersene: senza riga, l'ora non viene dallo strumento.
Anche alla domanda secca «Che giorno è oggi?» (o «Che data è oggi?») il modello spesso non chiama
l'orologio e **inventa una data** (misure del 2026-11-09: 1 volta su 6 con lo strumento, uguale con il
prompt precedente a «Giorni e scadenze», quindi non è una regressione). Quando la data di oggi serve a
una scadenza, invece, il modello chiama l'orologio (6/6). Fa eccezione «quanti giorni sono passati dal…»
dopo altre domande sulle date: il modello riusa spesso la data di oggi già presente in conversazione invece di
richiederla (1/8 con l'orologio). Senza la riga di log `get_current_time` per quella domanda, la data di
partenza non viene dallo strumento.

Convertitore e cronologia: le chiamate a `convert_units` (con il loro risultato) restano nella
cronologia della sessione, quelle all'orologio no. Senza questi esempi, dopo una dozzina di
domande il modello smetteva di chiamare lo strumento e rispondeva a mente; il prompt di sistema
contiene anche due esempi di richieste da passare comunque allo strumento («anni luce», «-300 °C»).
Prove del 2026-11-03 (Docker, Qwen 3.5 9B): sessione lunga di 19 domande con tutte le 13 conversioni
fatte dallo strumento, errori compresi; casi di errore in sessione nuova 11 volte su 12 (una volta
«10 litri in chilogrammi» è stata rifiutata a mente, senza numeri inventati). Misure successive dello
stesso giorno (locale, 12 casi di errore in sessione nuova per giro): 8/12 con il prompt senza la parte
sulla calcolatrice, poi 10/12, 8/12 e infine 21/24 con il prompt attuale; «10 km in miglia» sempre con
`convert_units` (9/9). I casi saltati («litri in kg», «anni luce», «pollici in grammi»…) sono
rifiutati a mente senza numeri inventati, ma a volte il modello scrive «lo strumento dice…» senza
averlo chiamato. La riga di log dice sempre se il risultato o l'errore viene dallo strumento.

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
| `Calcolatrice (MCP): non disponibile` nell'intestazione | il server `calcolatrice.py` non è partito (dipendenza `mcp` mancante, file assente nell'immagine) | `pip install -r requirements.txt`; provare `python calcolatrice.py` per vedere l'errore; il motivo è anche nella riga di log `calcolatrice MCP non disponibile` |
| `Giorni e scadenze (MCP): non disponibile` nell'intestazione | il server `scadenze.py` non è partito: causa più probabile `festivita.json` mancante o rovinato (anche dipendenza `mcp` mancante o file assenti nell'immagine) | provare `python scadenze.py` per vedere il messaggio `scadenze: ...`; il motivo è anche nella riga di log `scadenze MCP non disponibile` |
| `Errore: server MCP non raggiungibile` nel log | uno dei server (convertitore, calcolatrice o scadenze) si è interrotto durante la chat | riavviare l'assistente (non c'è riavvio automatico) |
| `(nessuna risposta dal modello)` | il modello ha restituito un testo vuoto | riprovare; con `LOG_LEVEL=DEBUG` si vede l'esito di ogni chiamata (`chiamata -> risposta finale (7.6s)` o richiesta di strumento) |
