# repo-lab-llm

Client Python minimo che dialoga da terminale con un modello eseguito in locale con LM Studio: più domande nella stessa esecuzione, risposta in streaming e cronologia mantenuta per la sessione. Materiale della Lezione 3 del corso Deep Learning e LLM (ITS Alto Adriatico).

## Contenuto della repository

| File | Funzione |
|---|---|
| `client.py` | Client che chiede domande da terminale e stampa in streaming le risposte del modello |
| `requirements.txt` | Dipendenze con versioni fissate |
| `.env.example` | Modello della configurazione locale, senza segreti |
| `CLAUDE.md` | Istruzioni di sviluppo lette da Claude Code |
| `.gitignore` | File esclusi da Git: configurazione locale, ambiente virtuale, pesi, log |

## Prerequisiti

- Windows con PowerShell, Git e VS Code (estensioni Python e Git Graph).
- Python con il launcher `py`.
- LM Studio con il modello `google/gemma-4-e2b`, quantizzazione a 4 bit (`Q4_K_M`).
- Claude Code CLI: guida ufficiale <https://code.claude.com/docs/en/setup>. In PowerShell: `irm https://claude.ai/install.ps1 | iex`, poi riaprire il terminale e verificare con `claude --version`.

## Preparazione

Dalla radice della repository:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

In VS Code selezionare l'interprete `.venv` con **Python: Select Interpreter**.

## Configurazione

1. In LM Studio scaricare e caricare `google/gemma-4-e2b` (4 bit), poi avviare il server dalla sezione Developer.
2. Leggere l'identificativo del modello esposto dal server:

   ```powershell
   $base = "http://localhost:1234/v1"
   (Invoke-RestMethod "$base/models").data | Select-Object id
   ```

3. Creare la configurazione locale, solo se `.env` non esiste già, e inserire l'identificativo letto al punto 2 al posto di `ID_MODELLO_REALE`:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

`LM_BASE_URL` può essere scritto con o senza `/v1` (per esempio `http://127.0.0.1:1234`): il client aggiunge `/v1` se manca.

`.env` resta sul proprio computer ed è escluso da Git.

## Avvio

```powershell
.\.venv\Scripts\python.exe client.py
```

Il programma chiede una domanda, la invia al modello e stampa la risposta man mano che arriva. Poi chiede la domanda successiva; per terminare si scrive `esci` (anche in maiuscolo):

```text
Domanda (esci per terminare): Mi chiamo Elia.
Piacere di conoscerti, Elia. Come posso esserti utile oggi?
Domanda (esci per terminare): Come mi chiamo?
Ti sei presentato come Elia.
Domanda (esci per terminare): esci
```

## Funzionalità

- **Input da terminale:** più domande nella stessa esecuzione, uscita con `esci`. Una riga vuota viene ignorata.
- **Streaming:** la richiesta usa `"stream": true` e la risposta compare progressivamente. I byte del flusso sono decodificati in UTF-8 in modo esplicito, così gli accenti restano corretti.
- **Cronologia in memoria:** la lista `messages` vive per tutta l'esecuzione, quindi il modello ricorda le domande precedenti (per esempio il nome). Alla chiusura la cronologia si perde: non viene salvata su disco. Una domanda che non riceve risposta (errore, timeout) non entra nella cronologia.
- **Errori gestiti:** con server fermo, timeout o errore HTTP il programma stampa il messaggio e resta attivo, così si può riprovare senza riavviare.

Limite noto: la cronologia non viene tagliata, quindi in sessioni molto lunghe si può superare il contesto del modello.

## Diagnosi rapida

| Messaggio | Primo controllo |
|---|---|
| `Connessione fallita` | LM Studio acceso, server avviato, URL e porta in `.env` |
| `Errore HTTP` con messaggio sul modello | Identificativo in `.env`, modello caricato |
| `Attesa scaduta` | Carico del computer, tempi del modello |
| Risposta vuota | `"reasoning_effort": "none"` nel payload: senza, il modello ragiona e consuma i token prima di rispondere |
| `KeyError: 'LM_BASE_URL'` o `'LM_MODEL'` | `.env` mancante o variabile non definita |
| `ModuleNotFoundError: No module named 'requests'` | Dipendenze non installate nell'ambiente usato: rieseguire `pip install -r requirements.txt` con l'interprete dell'ambiente virtuale |

Una risposta arrivata non è necessariamente corretta: va letta e valutata.
