# Passaggio di consegne — Lezione 4, assistente con orologio

> **Documento storico.** Fotografa lo stato al 2026-10-26, a lavoro interrotto. Il lavoro è
> stato completato il 2026-11-01: per l'esito vedere [`plan.md`](../../plan.md).

Aggiornato: 2026-10-26 · Branch: `master` (nessun push fatto) · Ultimo commit: `1538566`

Questo documento serve a riprendere il lavoro in una nuova sessione senza perdere nulla.
Leggere in quest'ordine: questo file → `lezione_4/CLAUDE.md` → `lezione_4/specs.md` →
`lezione_4/implementation_plan.md`.

## 1. Dove siamo

| Fase | Stato |
|---|---|
| Specifica (`specs.md`, copia in `docs/superpowers/specs/2026-10-26-assistente-orologio-design.md`) | approvata, commit `43a8d65` |
| Piano (`implementation_plan.md`) | approvato, commit `423150f` |
| Task 1–8 (config, log, orologio, strumenti, modello, grafo, sessione, terminale) | **completati**, 70 test verdi |
| Task 9 (prova reale con LM Studio) | **in corso**: trovato un bug reale, causa individuata, correzione da decidere |
| Task 10 (Docker), 11 (README + CLAUDE.md), 12 (revisione indipendente) | da fare |

Modalità di esecuzione decisa con l'utente: **nella sessione corrente** (skill
`superpowers:executing-plans`, TDD per ogni task, un commit per incremento) e **un sub-agent
revisore solo a implementazione finita** (Task 12). Push solo su richiesta esplicita.

## 2. Commit fatti

```
1538566 feat(terminale): aggiunge la chat da terminale
b1becd0 feat(sessione): conserva la cronologia della sessione
2b6628f feat(grafo): costruisce il grafo modello-strumenti con limite di passaggi
1d87184 feat(modello): collega LM Studio tramite API compatibile OpenAI
ed98c79 feat(strumenti): esegue le chiamate agli strumenti in modo sicuro
9bcfb1d feat(strumenti): aggiunge lo strumento orologio
0222f8d feat(log): configura i log su stderr
e3e4f46 feat(config): legge la configurazione dalle variabili d'ambiente
2c11284 chore: struttura del progetto e dipendenze fissate
423150f docs: aggiunge il piano di implementazione della lezione 4
43a8d65 docs: aggiunge la specifica della lezione 4
```

**Non committato:** `lezione_4/tests/test_reale.py` (scritto, vedi §4) e questo file.
Il `.env` locale esiste (copia di `.env.example`) ed è escluso da Git; il `venv/` è in
`lezione_4/venv` con tutte le dipendenze, incluso pytest.

## 3. Comandi utili (verificati)

Da `lezione_4/`:

```powershell
.\venv\Scripts\pytest.exe -q                         # 70 passed, 1 skipped
$env:RUN_REAL_TESTS="1"; .\venv\Scripts\pytest.exe -m reale -v -s   # prova reale (oggi FALLISCE, §4)
.\venv\Scripts\python.exe -m assistente              # avvio della chat
```

## 4. Il problema aperto (Task 9) — risposta finale vuota con Qwen

**Sintomo.** `test_tokyo_usa_lo_strumento` con LM Studio: Qwen chiama correttamente lo
strumento (`get_current_time {"timezone": "Asia/Tokyo"}`, il `ToolMessage` è giusto), ma la
risposta finale dopo lo strumento arriva con `content=''`. L'utente vedrebbe
`(nessuna risposta dal modello)`.

**Causa individuata (debugging sistematico, fase 1–2).** Richiamando LM Studio direttamente con
lo stesso payload che invia `langchain-openai`, la risposta di Qwen dopo lo strumento finisce
**interamente in `reasoning_content`** e `content` resta vuoto. Esempio reale:
`reasoning_content = 'A Tokyo sono le 01:54 di martedì 27 ottobre 2026.'`, `content = ''`.
È la separazione del ragionamento fatta da LM Studio per Qwen dopo un messaggio `tool`: il
nostro codice è corretto. `langchain-openai` scarta `reasoning_content`, quindi il testo si
perde.

Prove raccolte (payload identico, dopo lo strumento):

| Prova | Esito |
|---|---|
| Impostazioni predefinite | vuoto in 4 casi su 5 (non deterministico) |
| Domanda senza strumento («Ciao, mi chiamo Elia») | OK, testo in `content` (27 s) |
| `chat_template_kwargs: {enable_thinking: false}` | OK, testo in `content`, niente ragionamento (14 s) |
| `reasoning_effort: "none"` | OK, testo in `content` (12 s) |
| `reasoning: {effort: "none"}` | ignorato da LM Studio (ragionamento presente) |

**Ipotesi in verifica (fase 3).** Disattivare il ragionamento di Qwen su **tutte** le chiamate
risolve il problema senza peggiorare l'uso dello strumento, e dimezza i tempi. Prova lanciata:
grafo completo con
`ChatOpenAI(..., extra_body={"chat_template_kwargs": {"enable_thinking": False}})`,
3 volte «Che ore sono a Tokyo?» e 3 volte «Che ore sono adesso?» (deve scegliere da solo
`Europe/Rome`). **Esito: vedi §4.1.**

### 4.1 Esito della prova con ragionamento disattivato

Risultato (grafo completo, `enable_thinking: False` via `extra_body`):

| Domanda | Strumento | Risposta finale | Tempo |
|---|---|---|---|
| Tokyo #1 | `Asia/Tokyo` | «A Tokyo sono le 01:57 del martedì 27 ottobre 2026.» | 36 s |
| Tokyo #2 | `Asia/Tokyo` | OK | 34 s |
| Tokyo #3 | `Asia/Tokyo` | OK | 58 s |
| «adesso» #1 | `Europe/Rome` | **vuota** | 38 s |
| «adesso» #2 | `Europe/Rome` | «Sono le 18:00 del lunedì 26 ottobre 2026.» | 58 s |
| «adesso» #3 | `Europe/Rome` | **vuota** | 36 s |

**Ipotesi NON confermata.** Lo strumento viene sempre chiamato con il fuso giusto (6/6), ma
la risposta è ancora vuota in 2 casi su 6 e i tempi non scendono: probabilmente LM Studio
**ignora** `chat_template_kwargs` per questo modello (il successo della prova diretta B era
casuale). Unico parametro con indizi a favore: `reasoning_effort: "none"` (prova C, 12 s,
testo in `content`) — ma provato una sola volta.

### 4.2 Decisione da prendere alla ripresa

Prossimo passo (debugging sistematico, fase 3, nuova ipotesi — una variabile alla volta):

1. Ripetere lo script di §7 sostituendo `extra_body` con
   `extra_body={"reasoning_effort": "none"}` (passato come campo grezzo del body, perché
   `reasoning_effort` come parametro di ChatOpenAI viene convertito da langchain in
   `reasoning: {effort}`, che LM Studio ignora — prova D). Criteri: 6/6 risposte non vuote,
   strumento sempre chiamato, tempi ~12–20 s.
2. Se funziona → proporre all'utente di disattivare il ragionamento così (cambia il
   comportamento del modello: va confermato). Se non funziona → altre strade da discutere:
   in LM Studio disattivare la separazione del ragionamento per il modello (il testo
   arriverebbe in `content` e `pulisci_ragionamento` toglie i `<think>`), oppure leggere
   `reasoning_content` come risposta quando `content` è vuoto (sconsigliato: rischia di
   mostrare ragionamento vero, vietato dalla spec), oppure provare `google/gemma-4-e2b`.
   Dopo 3 tentativi falliti: fermarsi e discutere l'approccio con l'utente.

Una volta scelta la correzione:

1. Applicarla in `assistente/modello.py` (`crea_modello`).
2. TDD: prima `test_crea_modello_disattiva_il_ragionamento` in `tests/test_modello.py`
   (verifica `modello.bound.extra_body`), vederlo fallire, poi la modifica.
3. Rilanciare `RUN_REAL_TESTS=1 pytest -m reale -v -s` finché passa; annotare esito e durata.
4. Aggiornare `specs.md` (e la copia in `docs/superpowers/specs/`) §6.1/§6.2: ragionamento di
   Qwen disattivato, con il motivo.
5. Ledger: `Task 9: Ruling: ...` con il motivo e il costo (risposte forse meno "ragionate",
   ma 2× più veloci e affidabili).

Alternativa se l'utente vuole tenere il ragionamento: estendere il client per leggere
`reasoning_content` e usarlo come risposta quando `content` è vuoto — più complesso e rischia
di mostrare ragionamento vero all'utente (vietato dalla spec), quindi sconsigliato.

### 4.3 Poi, per chiudere il Task 9

- Prova manuale `.\venv\Scripts\python.exe -m assistente`: «Ciao, mi chiamo Elia» →
  «Che ore sono a Tokyo?» (controllare la riga di log INFO) → «e a Roma?» → «Come mi chiamo?»
  → `esci`. Annotare log e risposte.
- Commit `test(reale): verifica l'uso dello strumento con LM Studio` (+ eventuale
  `fix(modello): disattiva il ragionamento di Qwen ...` separato).
- `task-done` (vedi §6).

## 5. Decisioni prese durante l'implementazione (ledger)

- Setup: lavoro su `master` senza worktree (lo impone `CLAUDE.md`).
- T1: variabile presente ma vuota = mancante.
- T2: test aggiuntivi su stderr e opzione A dei log.
- T3: caso `Asia/Kolkata` (UTC+05:30); validazione del fuso su `available_timezones()` (stesso
  comportamento Windows/Linux); `args_schema` pydantic.
- T4: il messaggio «argomento … mancante o non valido» prende i nomi dallo schema dello
  strumento; anche «Errore: fuso orario …» loggato a WARNING.
- T5: `ChatOpenAI` scarta `reasoning_content`; a DEBUG si logga solo se presente.
- T6: `recursion_limit = 2*max_passi + 5` (verificato: con 20 passaggi e limite 25 →
  `GraphRecursionError`); `pythonpath = .` in `pytest.ini`.
- T7: test della cronologia per tipo e contenuto (LangGraph assegna id ai messaggi); testo da
  `AIMessage.text`.
- T8: `esegui_chat(sessione, intestazione, indirizzo, leggi, scrivi)` (aggiunto `indirizzo`);
  `main()` forza UTF-8 su stdout/stderr (bug reale su Windows con output rediretto: `—` → `?`);
  WARNING di limite/errori dal logger `sessione`.

## 6. Come riprendere l'esecuzione

1. Nuova sessione in `repo-lab-llm/`; dire: «riprendi la lezione 4 dal documento
   `lezione_4/docs/superpowers/handoff.md`».
2. Caricare `superpowers:executing-plans`. Il registro di avanzamento è in
   `repo-lab-llm/.superpowers/sdd/implementation_plan/progress.md` (ignorato da Git): i Task
   1–8 risultano `complete`, quindi si riparte dal **Task 9**.
3. Script della skill (Git Bash), da `lezione_4/`:
   - `…/skills/executing-plans/scripts/task-start implementation_plan.md 9`
   - `…/skills/executing-plans/scripts/task-done implementation_plan.md 9 1538566 -- ./venv/Scripts/pytest.exe -q`
   (`…` = `C:/Users/EliaMezzasalma/.claude/plugins/cache/superpowers-marketplace/superpowers/7.0.0`)
4. Dopo il Task 9: Task 10 Docker (immagine `python:3.12.15-slim`, solo runtime; verificato
   che un container raggiunge `http://host.docker.internal:1234/v1`), Task 11 README +
   `CLAUDE.md`, Task 12 revisione con sub-agent sul modello più capace, resoconto finale
   (cosa provato con mock / LM Studio / Docker), cancellazione di `.superpowers/sdd/…`,
   skill `superpowers:finishing-a-development-branch`. Nessun push senza richiesta.

## 7. Script di diagnosi (per rilanciare la prova di §4)

Da `lezione_4/`, con `PYTHONPATH=.`:

```python
import time
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from assistente.config import carica_config
from assistente.grafo import costruisci_grafo
from assistente.orologio import crea_orologio
from assistente.sessione import PROMPT_SISTEMA
from assistente.strumenti import crea_registro

config = carica_config()
strumenti = [crea_orologio()]
chat = ChatOpenAI(base_url=config.lm_base_url, model=config.lm_model, api_key="lm-studio", timeout=300,
                  extra_body={"chat_template_kwargs": {"enable_thinking": False}})
grafo = costruisci_grafo(chat.bind_tools(strumenti), crea_registro(strumenti), 3)
for domanda in ["Che ore sono a Tokyo?", "Che ore sono adesso?"]:
    for i in range(3):
        t = time.time()
        s = grafo.invoke({"messages": [SystemMessage(PROMPT_SISTEMA), HumanMessage(domanda)], "passi_strumento": 0})
        tool = [m.content.split(" — ")[-1] for m in s["messages"] if isinstance(m, ToolMessage)]
        print(f"{domanda} #{i+1}: {time.time()-t:.0f}s strumento={tool} risposta={s['messages'][-1].text!r}")
```

## 8. Fatti di ambiente utili

- LM Studio su `http://localhost:1234/v1`, modelli `qwen/qwen3.5-9b` (predefinito) e
  `google/gemma-4-e2b`.
- Python host 3.12.10; Docker 29.5.3, Compose v5.1.4; `python:3.12-slim` = 3.12.15.
- Gli avvisi di Pyright «Import could not be resolved» dipendono dall'editor che non usa
  `lezione_4/venv`: non sono errori.
- Qwen con ragionamento attivo: ~30–60 s per chiamata; senza: ~12–15 s.
