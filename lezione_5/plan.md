# Piano e consuntivo — Lezione 4, assistente con orologio

Aggiornato: 2026-11-01 · Branch: `master` · Stato: **completato** (Task 1–12)

Questo file riassume com'è andato davvero il lavoro rispetto al piano approvato.
Il piano completo, con i passi e i test di ogni task, è in
[`implementation_plan.md`](implementation_plan.md); la specifica in [`specs.md`](specs.md);
configurazione, avvio e diagnosi nel [`README.md`](README.md).

## 1. Obiettivo

Chat da terminale in Python con un grafo LangGraph esplicito (modello ⇄ strumenti), modello
locale servito da LM Studio (`qwen/qwen3.5-9b`), cronologia limitata alla sessione, strumento
`get_current_time` con fuso orario IANA obbligatorio, avvio anche con Docker Compose.

## 2. Metodo

1. Brainstorming e specifica → approvata (`43a8d65`).
2. Piano in 12 task → approvato (`423150f`).
3. Esecuzione nella sessione corrente (skill `superpowers:executing-plans`): TDD per ogni
   passo (test visto fallire, poi passare), un commit per incremento, registro delle decisioni.
4. Revisione finale dell'intero branch con un sub-agent indipendente, poi correzioni con test.

## 3. Task

| # | Task | Stato | Commit | Note |
|---|---|---|---|---|
| 1 | Struttura e configurazione | ✅ | `2c11284`, `e3e4f46` | variabile presente ma vuota = mancante |
| 2 | Log su stderr | ✅ | `0222f8d` | librerie esterne a WARNING |
| 3 | Strumento orologio | ✅ | `9bcfb1d` | validazione su `available_timezones()`; caso `Asia/Kolkata` (UTC+05:30) |
| 4 | Esecuzione degli strumenti | ✅ | `ed98c79` | argomenti errati e strumenti sconosciuti → messaggio d'errore al modello, mai eccezioni |
| 5 | Collegamento al modello | ✅ | `1d87184` | API compatibile OpenAI tramite `langchain-openai` |
| 6 | Grafo | ✅ | `2b6628f` | `recursion_limit = 2·max_passi + 5`, altrimenti LangGraph si fermava prima del nostro limite |
| 7 | Sessione e cronologia | ✅ | `b1becd0` | in cronologia solo domanda e risposta finale |
| 8 | Terminale e avvio | ✅ | `1538566` | stdout/stderr forzati in UTF-8 (bug reale su Windows) |
| 9 | Prova reale con LM Studio | ✅ | `73c26ac`, `21c2863`, `2efa7d2`, `ba89f4a`, `70d1b0a` | vedi §4 |
| 10 | Docker | ✅ | `e30eceb` | immagine solo runtime, utente non-root `app` |
| 11 | README e `CLAUDE.md` | ✅ | `7a9047f` | solo comandi verificati |
| 12 | Revisione indipendente | ✅ | `6d8b9ca`, `5978be1`, `dc516dd`, `09dbf10` | vedi §5 |

## 4. Problemi trovati nella prova reale (Task 9)

**Risposta finale vuota.** Dopo la chiamata allo strumento, LM Studio metteva spesso la
risposta di Qwen nel campo `reasoning_content`, che `langchain-openai` scarta: risposta vuota
in 2–4 casi su 5–6. Ipotesi provate, una alla volta:

| Prova | Esito |
|---|---|
| `chat_template_kwargs: {enable_thinking: false}` | ancora 2 vuote su 6, tempi invariati: ignorato |
| `extra_body={"reasoning_effort": "none"}` | 6/6 risposte, strumento sempre giusto, 12–16 s invece di 30–60 s |

Decisione (approvata dall'utente): **ragionamento disattivato** con
`extra_body={"reasoning_effort": "none"}`. Costo: risposte meno ragionate su domande
complesse, fuori dal perimetro di questa lezione.

**Domanda di seguito senza strumento.** A «e a Roma?» dopo Tokyo il modello ricavava spesso
l'ora dalla risposta precedente invece di chiamare lo strumento, a volte sbagliando:

| Configurazione | Strumento chiamato per Roma |
|---|---|
| senza ragionamento, prompt originale | 2/6 (3 ore sbagliate) |
| con ragionamento, prompt originale | 3/4 |
| senza ragionamento, prompt rafforzato | 5/6 |

Decisione: aggiunta al prompt di sistema la frase «non calcolare l'ora partendo da un altro
fuso». Il caso residuo (~1 su 6) è un limite del modello, documentato in spec e README.

**Log rumorosi.** `openai` 3.x usa `httpx2`/`httpcore2`, che a INFO stampavano una riga per
richiesta: portati a WARNING come le altre librerie esterne.

## 5. Revisione indipendente (Task 12)

Esito del revisore: «pronto, con correzioni». Corrette con un test ciascuna (RED → GREEN):

- qualunque errore del modello diverso da `openai.APIError` (es. `LM_BASE_URL` senza `/v1`)
  chiudeva la chat con un traceback;
- gli errori HTTP del server (es. cronologia oltre il contesto) venivano presentati come
  «impossibile contattare il modello»;
- `LOG_LEVEL` non valido → traceback all'avvio;
- senza `lezione_4/.env` veniva letto il `.env` di un'altra lezione nella radice del repository;
- a DEBUG mancavano i messaggi inviati al modello (spec §6.7).

Rimandate (minori):

- `</think>` senza apertura o `<think>` non chiuso non vengono rimossi (rischio basso con
  ragionamento disattivato);
- chiamate valide e non valide nello stesso messaggio non eseguite nell'ordine originale;
- il segnaposto «(nessuna risposta dal modello)» viene salvato in cronologia;
- il messaggio d'errore dello strumento elenca tutti i nomi degli argomenti;
- log ERROR dello strumento senza passo e argomenti; avviso d'errore del modello mostrato due
  volte nel terminale;
- orario dei log nel container in UTC.

## 6. Verifiche eseguite

| Ambito | Comando | Esito |
|---|---|---|
| Test automatici | `.\venv\Scripts\python.exe -m pytest -q` | 79 passed, 1 skipped (anche in un venv nuovo) |
| Prova reale | `$env:RUN_REAL_TESTS="1"; .\venv\Scripts\python.exe -m pytest -m reale -v -s` | passed, ~20 s |
| Chat locale | `.\venv\Scripts\python.exe -m assistente` | Tokyo, Roma, nome ricordato; messaggi chiari con server spento, URL senza `/v1`, `LOG_LEVEL` non valido, configurazione mancante |
| Docker | `docker compose build` · `docker compose run --rm assistente` | build OK; immagine con solo `assistente/` e `requirements.txt`, utente `app`; chat funzionante con LM Studio sull'host |

## 7. Da fare

Fatto il 2026-11-01:

- ✅ `docker compose run --rm assistente` eseguito con il comando esatto del README (domande
  passate in ingresso): strumento chiamato con `Asia/Tokyo`, risposta corretta, uscita con
  `Ciao!`.
- ✅ Push su GitHub (`origin/master`, repository `LLM-project`): la lezione è nella cartella
  `lezione_4/`, accanto a `lezione_3/`, che non è stata modificata.

Resta:

- Provare `google/gemma-4-e2b` come modello alternativo.
- Valutare le segnalazioni minori di §5.
