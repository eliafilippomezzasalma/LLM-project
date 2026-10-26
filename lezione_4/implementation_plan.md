# Assistente con orologio — Piano di implementazione

> **Per chi esegue:** eseguire nella sessione corrente con superpowers:executing-plans, un task
> alla volta (TDD: test che fallisce → codice → test verde → commit). A implementazione finita,
> revisione indipendente con un sub-agent (Task 12). I passi usano le caselle (`- [ ]`).

**Obiettivo:** chat da terminale con grafo LangGraph esplicito, modello Qwen in LM Studio,
strumento orologio, limite di passaggi, log e Docker.

**Architettura:** un modulo per ogni elemento nel pacchetto `assistente/`. Il grafo riceve
modello e registro strumenti come dipendenze (i test usano un modello finto); la cronologia
vive in `Sessione`; il terminale fa solo I/O.

**Tecnologie:** Python 3.12, LangGraph (Graph API), langchain-openai, python-dotenv, tzdata,
pytest, Docker Compose.

**Specifica:** `lezione_4/specs.md` (copia di
`lezione_4/docs/superpowers/specs/2026-10-26-assistente-orologio-design.md`).

## Struttura dei file

```
lezione_4/
├── assistente/
│   ├── __init__.py
│   ├── __main__.py      # python -m assistente → terminale.main()
│   ├── config.py        # variabili d'ambiente → Config
│   ├── log.py           # configurazione logging
│   ├── orologio.py      # strumento get_current_time + formato italiano
│   ├── strumenti.py     # registro ed esecuzione sicura delle tool_call
│   ├── modello.py       # ChatOpenAI verso LM Studio + pulizia <think>
│   ├── grafo.py         # stato, nodi, instradamento, costruzione grafo
│   ├── sessione.py      # cronologia + prompt di sistema
│   └── terminale.py     # ciclo Tu>/Assistente>, uscita, errori
├── tests/
│   ├── finti.py         # ModelloFinto per i test
│   ├── test_config.py  test_log.py  test_orologio.py  test_strumenti.py
│   ├── test_modello.py  test_grafo.py  test_sessione.py  test_terminale.py
│   └── test_reale.py    # solo con RUN_REAL_TESTS=1
├── .env.example  .gitignore  .dockerignore  pytest.ini
├── requirements.txt  requirements-dev.txt
├── Dockerfile  compose.yaml  README.md
├── specs.md
└── implementation_plan.md
```

## Vincoli globali

- Python 3.12, codice sincrono; messaggi, log e commit in italiano (Conventional Commits).
- Versioni dirette fissate: `langgraph==1.2.17`, `langchain-openai==1.7.2`,
  `python-dotenv==1.2.4`, `tzdata==2026.5`, `pytest==9.1.1` (solo dev); transitive fissate
  con `pip freeze`.
- Predefiniti: `LM_MODEL=qwen/qwen3.5-9b`, `MAX_TOOL_STEPS=3`, `LOG_LEVEL=INFO`, timeout
  300 s, chiave API segnaposto `"lm-studio"`.
- Solo Graph API: niente `ToolNode`, `create_react_agent`, checkpointer, Functional API.
- Lavorare solo in `lezione_4/`; prima di ogni commit `git status`, diff, staging selettivo;
  push solo su richiesta.

## Punti critici (test aggiunti al task indicato)

1. **Ctrl+C mentre si attende il modello** → esce con `Ciao!`, senza traceback (Task 8).
2. **Risposta finale vuota** (solo ragionamento) → stampa `(nessuna risposta dal modello)`
   invece di una riga vuota (Task 7).
3. **Fuso con maiuscole o spazi** (`asia/tokyo`, `" Asia/Tokyo "`) → su Windows `zoneinfo`
   ignora le maiuscole, su Linux no. Per avere lo stesso comportamento ovunque: spazi tolti e
   validazione su `zoneinfo.available_timezones()`; `asia/tokyo` → errore con suggerimento
   ovunque (Task 3).
4. **LM Studio che cade a metà sessione** → messaggio, cronologia intatta, la domanda
   successiva funziona (Task 7, 8).
5. **`tool_call` malformata** (`invalid_tool_calls`) → `ToolMessage` d'errore, conta come
   passaggio, l'instradamento la tratta come richiesta di strumento (Task 4, 6).

---

### Task 1: Struttura iniziale e configurazione

**File:** `.gitignore` (`venv/`, `__pycache__/`, `.pytest_cache/`, `.env`), `pytest.ini`
(`testpaths = tests`, marcatore `reale`), `requirements.txt`, `requirements-dev.txt`,
`.env.example`, `assistente/__init__.py`, `assistente/config.py`, `tests/test_config.py`.

**Produce:**
- `@dataclass(frozen=True) class Config: lm_base_url: str; lm_model: str; max_tool_steps: int; log_level: str`
- `class ErroreConfigurazione(Exception)`
- `carica_config(env: Mapping[str, str] | None = None) -> Config` — con `None` chiama
  `load_dotenv()` e legge `os.environ`.

- [ ] Creare `venv` in `lezione_4/`, installare le dipendenze dirette fissate; generare
  `requirements.txt` con `pip freeze` (senza pytest e le sue dipendenze);
  `requirements-dev.txt` = `-r requirements.txt` + `pytest==9.1.1`.
- [ ] Test che falliscono: `test_valori_completi`, `test_predefiniti` (3 / `INFO`),
  `test_manca_lm_base_url` (`ErroreConfigurazione` con `LM_BASE_URL` nel messaggio),
  `test_manca_lm_model`, `test_max_tool_steps_non_intero` (`"tre"`), `test_max_tool_steps_zero`.
- [ ] `pytest tests/test_config.py -v` → FAIL.
- [ ] Implementare.
- [ ] `pytest tests/test_config.py -v` → PASS.
- [ ] Commit `chore: struttura del progetto e dipendenze fissate` e
  `feat(config): legge la configurazione dalle variabili d'ambiente`.

### Task 2: Log

**File:** `assistente/log.py`, `tests/test_log.py`.

**Produce:** `configura_log(livello: str) -> None` — `StreamHandler` su stderr, formato
`%(asctime)s %(levelname)s %(name)s: %(message)s`, `datefmt="%H:%M:%S"`; `httpx`, `openai`,
`langchain`, `langchain_core`, `langchain_openai`, `langgraph` a WARNING. Logger del progetto
chiamati `strumenti`, `modello`, `grafo`, `sessione`.

- [ ] Test: `test_formato_riga` (`capsys`, regex `^\d\d:\d\d:\d\d INFO strumenti: ciao$` su
  stderr), `test_librerie_esterne_a_warning`, `test_debug_abilitato`.
- [ ] FAIL → implementare → PASS.
- [ ] Commit `feat(log): configura i log su stderr`.

### Task 3: Strumento orologio

**File:** `assistente/orologio.py`, `tests/test_orologio.py`.

**Produce:**
- `class FusoNonValido(ValueError)`
- `formatta_ora(istante: datetime, fuso: str) -> str` — `istante` con fuso; nome non IANA →
  `FusoNonValido(fuso)`.
- `crea_orologio(adesso: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> BaseTool`
  — `@tool` `get_current_time(timezone: str) -> str`; fuso non valido → stringa d'errore della
  specifica (mai eccezione); descrizione che suggerisce `Europe/Rome` se manca un luogo.

Giorni e mesi italiani da tuple costanti; scostamento da `utcoffset()` → `UTC+09:00`.

- [ ] Test con istante fisso `2026-10-26T11:30:41Z`:
  - `Asia/Tokyo` → `"lunedì 26 ottobre 2026, 20:30:41 — Asia/Tokyo (UTC+09:00)"`
  - `Europe/Rome` → `"lunedì 26 ottobre 2026, 12:30:41 — Europe/Rome (UTC+01:00)"` (solare)
  - `America/Los_Angeles` → `"lunedì 26 ottobre 2026, 04:30:41 — America/Los_Angeles (UTC-07:00)"`
  - cambio di data: `2026-10-26T02:00:00Z` con `America/Los_Angeles` → `"domenica 25 ottobre 2026, 19:00:00 — America/Los_Angeles (UTC-07:00)"`
  - ora legale: `2026-07-15T10:00:00Z` con `Europe/Rome` → `UTC+02:00`
  - `test_fuso_non_valido` (`JST`) → `"Errore: fuso orario 'JST' non valido, usa un nome IANA come 'Asia/Tokyo'"`
  - `test_fuso_minuscolo_non_valido` (`asia/tokyo`) → stesso tipo di errore
  - `test_spazi_rimossi` (`" Asia/Tokyo "`) → valido
  - `test_schema_strumento`: `tool.name == "get_current_time"`, `"timezone"` negli argomenti
- [ ] FAIL → implementare → PASS.
- [ ] Commit `feat(strumenti): aggiunge lo strumento orologio`.

### Task 4: Registro ed esecuzione degli strumenti

**File:** `assistente/strumenti.py`, `tests/test_strumenti.py`.

**Consuma:** `crea_orologio` (Task 3).

**Produce:**
- `crea_registro(strumenti: list[BaseTool]) -> dict[str, BaseTool]`
- `esegui_chiamate(registro: dict[str, BaseTool], messaggio: AIMessage, passo: int, max_passi: int) -> list[ToolMessage]`
  — esegue `tool_calls` e `invalid_tool_calls` in ordine, un `ToolMessage` ciascuna con il suo
  `tool_call_id`; log INFO `passo {p}/{max} {nome} {args json} -> {risultato}`, oppure
  WARNING/ERROR secondo la tabella §6.6 della specifica.

- [ ] Test (con uno strumento finto che solleva `RuntimeError`): `test_chiamata_singola`
  (contenuto, `tool_call_id`, riga INFO), `test_due_chiamate_in_ordine`,
  `test_strumento_sconosciuto` → `"Errore: strumento 'meteo' non disponibile"`,
  `test_argomento_mancante` → `"Errore: argomento 'timezone' mancante o non valido"`,
  `test_invalid_tool_call` → stesso messaggio, `test_eccezione_generica` →
  `"Errore: esecuzione dello strumento non riuscita"` + log ERROR.
- [ ] FAIL → implementare → PASS.
- [ ] Commit `feat(strumenti): esegue le chiamate agli strumenti in modo sicuro`.

### Task 5: Collegamento al modello

**File:** `assistente/modello.py`, `tests/test_modello.py`.

**Produce:**
- `crea_modello(config: Config, strumenti: list[BaseTool]) -> Runnable` —
  `ChatOpenAI(base_url=..., model=..., api_key="lm-studio", timeout=300).bind_tools(strumenti)`.
- `pulisci_ragionamento(testo: str) -> str` — rimuove i blocchi `<think>…</think>` (anche su
  più righe) e gli spazi ai bordi.

- [ ] Test: `test_pulisce_think`, `test_testo_senza_think_invariato`,
  `test_crea_modello_usa_config` (verifica `base_url` e `model`, nessuna chiamata di rete).
- [ ] FAIL → implementare → PASS.
- [ ] Commit `feat(modello): collega LM Studio tramite API compatibile OpenAI`.

### Task 6: Grafo

**File:** `assistente/grafo.py`, `tests/finti.py`, `tests/test_grafo.py`.

**Consuma:** `esegui_chiamate`, `crea_registro` (Task 4).

**Produce:**
- `class StatoAssistente(TypedDict): messages: Annotated[list[AnyMessage], add_messages]; passi_strumento: int`
- `instrada(stato: StatoAssistente, max_passi: int) -> Literal["strumenti", "fine"]`
- `costruisci_grafo(modello: Runnable, registro: dict[str, BaseTool], max_passi: int) -> CompiledStateGraph`
  — nodo `"modello"` (invoca, log DEBUG di durata e `reasoning_content` se presente), nodo
  `"strumenti"` (`esegui_chiamate`, `passi_strumento + 1`); archi `START → modello`,
  condizionale `modello → strumenti | END`, `strumenti → modello`.
- `limite_raggiunto(stato: StatoAssistente) -> bool` — vero se l'ultimo `AIMessage` ha ancora
  `tool_calls` o `invalid_tool_calls`.

`tests/finti.py`: `ModelloFinto(risposte: list[AIMessage])` con `invoke(messaggi)` che registra
i messaggi in `self.chiamate` e restituisce la risposta successiva.

- [ ] Test: `test_instrada_senza_tool_call` → `"fine"`, `test_instrada_con_tool_call` →
  `"strumenti"`, `test_instrada_al_limite` → `"fine"`, `test_instrada_invalid_tool_call` →
  `"strumenti"`, `test_giro_completo` (Human → AI con tool_call → Tool → AI finale,
  `passi_strumento == 1`, una riga INFO), `test_si_ferma_al_limite` (modello che chiede sempre
  lo strumento, `max_passi=3` → esattamente 3 `ToolMessage`, `limite_raggiunto` vero),
  `test_grafo_ha_nodi_espliciti` (nodi `{"modello", "strumenti"}`).
- [ ] FAIL → implementare → PASS.
- [ ] Commit `feat(grafo): costruisce il grafo modello-strumenti con limite di passaggi`.

### Task 7: Sessione e cronologia

**File:** `assistente/sessione.py`, `tests/test_sessione.py`.

**Consuma:** `costruisci_grafo`, `limite_raggiunto` (Task 6), `pulisci_ragionamento` (Task 5).

**Produce:**
- `PROMPT_SISTEMA: str` — italiano; usare sempre `get_current_time` per l'ora attuale, non
  riusare orari precedenti.
- `class LimitePassaggiRaggiunto(Exception)`
- `class Sessione` — `__init__(self, grafo)`, `cronologia: list[BaseMessage]` (inizia con il
  `SystemMessage`), `chiedi(self, domanda: str) -> str`: invoca il grafo con
  `cronologia + [HumanMessage]` e `passi_strumento=0`; limite → `LimitePassaggiRaggiunto`
  senza toccare la cronologia; eccezione del grafo → propagata, cronologia intatta; turno
  riuscito → aggiunge solo `HumanMessage` e `AIMessage(testo pulito)`; testo vuoto →
  `"(nessuna risposta dal modello)"`.

- [ ] Test: `test_cronologia_solo_domanda_e_risposta` (dopo un giro con strumento `len == 3`,
  nessun `ToolMessage`), `test_secondo_turno_riceve_il_primo` (dalle `chiamate` del modello
  finto), `test_limite_non_sporca_cronologia`, `test_errore_modello_non_sporca_cronologia`,
  `test_risposta_vuota_segnaposto`, `test_think_rimosso_da_cronologia`.
- [ ] FAIL → implementare → PASS.
- [ ] Commit `feat(sessione): conserva la cronologia della sessione`.

### Task 8: Terminale e avvio

**File:** `assistente/terminale.py`, `assistente/__main__.py`, `tests/test_terminale.py`.

**Produce:**
- `esegui_chat(sessione: Sessione, intestazione: str, leggi: Callable[[str], str] = input, scrivi: Callable[[str], None] = print) -> None`
  — stampa intestazione e riga d'aiuto; prompt `Tu> `; righe vuote ignorate; `esci`/`exit`
  (senza distinzione di maiuscole), `EOFError`, `KeyboardInterrupt` → `Ciao!` e fine;
  `(sto pensando...)` poi `Assistente> …`; `LimitePassaggiRaggiunto` → avviso e continua;
  `openai.APIError` (connessione, timeout, modello inesistente) →
  `Impossibile contattare il modello su {url}: {dettaglio}` + log WARNING, e continua.
- `main() -> int` — carica la configurazione (`ErroreConfigurazione` → stampa e restituisce 1),
  configura i log, costruisce orologio, registro, modello, grafo, sessione, chiama `esegui_chat`.

- [ ] Test con `leggi`/`scrivi` finti: `test_esci_saluta`, `test_exit_maiuscolo`,
  `test_eof_saluta`, `test_ctrl_c_saluta_senza_traceback`,
  `test_ctrl_c_durante_attesa_modello` (la sessione finta solleva `KeyboardInterrupt` in
  `chiedi`), `test_riga_vuota_ignorata`, `test_stampa_sto_pensando_e_risposta`,
  `test_limite_mostra_avviso_e_continua`, `test_errore_connessione_e_continua` (la domanda
  successiva riceve risposta), `test_main_config_mancante_esce_con_1`.
- [ ] FAIL → implementare → PASS.
- [ ] Commit `feat(terminale): aggiunge la chat da terminale`.

### Task 9: Prova reale con LM Studio (locale)

**File:** `tests/test_reale.py`.

`test_tokyo_usa_lo_strumento` — marcatore `reale`, saltato se `RUN_REAL_TESTS != "1"`;
grafo vero dal `.env`; «Che ore sono a Tokyo?» → almeno un `ToolMessage` che contiene
`Asia/Tokyo` e una risposta finale non vuota.

- [ ] `pytest` → tutto verde, test reale saltato.
- [ ] `$env:RUN_REAL_TESTS="1"; pytest -m reale -v` → PASS con LM Studio acceso; annotare esito
  e durata.
- [ ] Prova manuale `python -m assistente`: Tokyo → «e a Roma?» → «come mi chiamo?» → `esci`;
  annotare log e risposte.
- [ ] Commit `test(reale): verifica l'uso dello strumento con LM Studio`.

### Task 10: Docker

**File:** `Dockerfile`, `.dockerignore`, `compose.yaml`.

- `Dockerfile`: `FROM python:3.12.15-slim`, `PYTHONUNBUFFERED=1`, installa `requirements.txt`
  senza cache, copia `assistente/`, utente non-root `app`, `CMD ["python", "-m", "assistente"]`.
- `.dockerignore`: `.env`, `venv/`, `__pycache__/`, `.pytest_cache/`, `tests/`, `docs/`,
  `requirements-dev.txt`, `*.md`, `.git`.
- `compose.yaml`: servizio `assistente` come da specifica §9.

- [ ] `docker compose build` → nessun errore.
- [ ] `docker compose run --rm assistente python -c "import os; print(os.listdir('/app'))"` →
  né `.env` né `tests`.
- [ ] Prova manuale `docker compose run --rm assistente`: Tokyo, riga di log, follow-up, `esci`.
- [ ] Commit `feat(docker): avvio con Docker Compose`.

### Task 11: README e CLAUDE.md

- [ ] README (solo comandi verificati nei Task 1–10): requisiti, configurazione
  (`Copy-Item .env.example .env`), avvio locale e Docker, test automatici e reali, prova
  manuale guidata, diagnosi (LM Studio spento, modello sbagliato → `GET /v1/models`, container
  che non raggiunge l'host, lentezza).
- [ ] `CLAUDE.md`: aggiungere struttura e comandi di test (convenzioni stabili).
- [ ] Commit `docs: README con configurazione, avvio, test e diagnosi`.

### Task 12: Revisione indipendente

- [ ] Sub-agent che non ha visto la conversazione: legge `specs.md`, `implementation_plan.md` e
  il codice; segnala differenze dalla specifica e bug.
- [ ] Valutare ogni segnalazione; correggere solo quelle verificate, ognuna con il suo test.
- [ ] Resoconto finale: cosa è stato provato con test automatici, con LM Studio, con Docker, e
  cosa resta da provare.
