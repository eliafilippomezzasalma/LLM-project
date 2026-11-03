# Convertitore di unità MCP — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un server MCP separato (`convertitore.py`) con un solo strumento `convert_units`, usato dall'assistente della lezione 4 accanto all'orologio.

**Architecture:** `convertitore.py` contiene in sezioni distinte la logica pura (tabella unità, sinonimi, schema Pydantic `RichiestaConversione` che fa tutta la validazione, conversione, messaggi d'errore italiani) e uno strato MCP sottile basato sul `Server` di basso livello di `mcp` (lo schema esposto è `RichiestaConversione.model_json_schema()`, la validazione è `RichiestaConversione.model_validate`). L'assistente avvia il server come processo figlio via stdio tramite `assistente/mcp_remoto.py`, un ponte sincrono (thread con event loop asyncio dedicato) che presenta lo strumento remoto come `StructuredTool` con schema JSON grezzo, così LangChain non rivalida e gli argomenti arrivano intatti al server.

**Tech Stack:** Python 3.12, `mcp==2.3.0` (nuova dipendenza), Pydantic 2.14, LangChain core, LangGraph, pytest.

**Spec:** `docs/superpowers/specs/2026-11-02-convertitore-mcp-design.md`

## Global Constraints

- Si lavora solo in `lezione_4/`, branch `feature/nuove-funzionalita`. **Nessun commit né push: lo decide l'utente.** Al posto del commit, ogni task finisce con la suite completa verde.
- Comandi da `lezione_4/` in PowerShell: test `.\venv\Scripts\python.exe -m pytest -q`.
- Il file dedicato alla funzionalità è `lezione_4/convertitore.py` (richiesta dell'utente: un file `.py` a parte).
- Unità ammesse, esattamente 23: lunghezza `mm, cm, m, km, in, ft, mi`; massa `g, kg, lb, oz`; tempo `s, min, h`; temperatura `°C, °F, K`; volume `ml, l, gal`; velocità `m/s, km/h, mph`.
- Fattori esatti: in = 0.0254 m, ft = 0.3048 m, mi = 1609.344 m, lb = 0.45359237 kg, oz = lb/16, gal = 3.785411784 l (gallone USA), km/h = 1/3.6 m/s, mph = 1609.344/3600 m/s.
- Nome strumento `convert_units`, argomenti `value`, `from_unit`, `to_unit`.
- Messaggi d'errore in italiano, testo che inizia con `Errore: `.
- Grafo (`grafo.py`) e esecuzione chiamate (`strumenti.py`) non cambiano.
- Ogni dipendenza nuova fissata a versione esatta in `requirements.txt`; `pywin32` con marcatore `; sys_platform == "win32"` (l'immagine Docker è Linux).
- Niente `langchain-mcp-adapters`: il ponte sincrono è scritto a mano (meno dipendenze, il resto del programma resta sincrono).

## Review Focus

1. Il modello passa `value` come stringa (`"10"`): Pydantic in modalità lax la accetta e converte — va bene; `"dieci"` deve dare l'errore italiano sul numero.
2. Il modello passa un booleano o `null` come `value`: deve essere un errore italiano, non un crash né `1.0`.
3. Sinonimi ambigui: `m` deve restare metri, `min` minuti, `K` kelvin, `mi` miglia; `M`/`MI`/`MIN` maiuscoli si normalizzano allo stesso simbolo.
4. Il server muore a metà chat (processo terminato): la chiamata restituisce un `Errore:` entro il timeout, la chat continua.
5. Chiusura del programma (Ctrl+C, `esci`, EOF): il processo del server viene chiuso, nessun processo orfano né traceback.

Ognuno ha un test nel task che possiede il codice (Task 1: 1–3; Task 3: 4–5).

---

### Task 1: logica e schema del convertitore (senza MCP)

**Files:**
- Create: `convertitore.py` (sezioni: unità, sinonimi, schema, conversione, messaggi; lo strato MCP arriva nel Task 2)
- Test: `tests/test_convertitore.py`

**Interfaces:**
- Produces:
  - `GRANDEZZE: dict[str, str]` simbolo → nome grandezza (`"km": "lunghezza"`, …); `UNITA: tuple[str, ...]` i 23 simboli nell'ordine della tabella.
  - `Unita = Literal[...]` con i 23 simboli.
  - `normalizza_unita(testo: object) -> object` (validatore «before»: simbolo canonico, o `ValueError` italiano).
  - `class RichiestaConversione(BaseModel)`: `value: float` (`allow_inf_nan=False`, `strict` disattivato ma bool rifiutato), `from_unit: Unita`, `to_unit: Unita`, con descrizioni dei campi; `model_validator(mode="after")` per compatibilità e zero assoluto.
  - `converti(richiesta: RichiestaConversione) -> float`
  - `formatta_risultato(richiesta: RichiestaConversione, risultato: float) -> str`
  - `messaggio_errore(errore: ValidationError) -> str` (inizia con `Errore: `)
  - `esegui_conversione(argomenti: dict) -> tuple[str, bool]` → (testo, è_errore): valida, converte, formatta; unico punto usato dal Task 2.

**Testi esatti** (i test li confrontano):
- unità sconosciuta: `unità 'X' non ammessa. Unità ammesse: mm, cm, m, km, in, ft, mi, g, kg, lb, oz, s, min, h, °C, °F, K, ml, l, gal, m/s, km/h, mph`
- incompatibili: `impossibile convertire 'kg' (massa) in 'm' (lunghezza): grandezze diverse`
- zero assoluto: `-300 °C è sotto lo zero assoluto (-273.15 °C)` (valore con `:g`, limite nell'unità di partenza: `0 K`, `-273.15 °C`, `-459.67 °F`)
- valore non numerico/non finito/bool/null: `il valore deve essere un numero finito`
- argomento mancante: `argomento 'to_unit' mancante`
- altro errore non previsto: `argomento '<loc>' non valido`
- più errori: uniti con `; ` dopo un unico prefisso `Errore: `
- risultato: `f"{value:g} {from_unit} = {risultato:.6g} {to_unit}"`, es. `10 km = 6.21371 mi`

**Sinonimi** (confronto dopo `strip()`; prima simbolo esatto, poi simbolo in minuscolo — `KM`→`km`, `L`→`l`, `MPH`→`mph` — poi tabella sinonimi in minuscolo):
metri/metro/meter/meters→m; millimetri/millimetro→mm; centimetri/centimetro→cm; chilometri/chilometro/kilometri/kilometer/kilometers→km; pollici/pollice/inch/inches→in; piedi/piede/foot/feet→ft; miglia/miglio/mile/miles→mi; grammi/grammo/gram/grams→g; chilogrammi/chilogrammo/chili/kilo/kilogram/kilograms→kg; libbre/libbra/pound/pounds/lbs→lb; once/oncia/ounce/ounces→oz; secondi/secondo/sec/second/seconds→s; minuti/minuto/minute/minutes→min; ore/ora/hour/hours→h; c/celsius/gradi celsius/°c→°C; f/fahrenheit/gradi fahrenheit/°f→°F; kelvin→K; millilitri/millilitro→ml; litri/litro/liter/liters/litre/litres→l; galloni/gallone/gallon/gallons→gal; mps/metri al secondo→m/s; kmh/kph/chilometri orari/chilometri all'ora→km/h; miglia orarie/miles per hour→mph.

- [ ] **Step 1: scrivere i test che falliscono** in `tests/test_convertitore.py`:
  - `test_unita_sono_23_in_6_grandezze`: `len(UNITA) == 23`, `set(GRANDEZZE.values()) == {"lunghezza","massa","tempo","temperatura","volume","velocità"}`.
  - `test_schema_elenca_unita_chiuse`: in `RichiestaConversione.model_json_schema()["properties"]["from_unit"]["enum"]` (e `to_unit`) c'è esattamente `list(UNITA)`; `required == ["value","from_unit","to_unit"]`.
  - `test_conversioni` parametrico (`pytest.approx(rel=1e-9)`): 10 km→mi 6.213711922373339; 1 mi→m 1609.344; 1 lb→g 453.59237; 16 oz→lb 1; 90 min→h 1.5; 100 °C→°F 212; 32 °F→°C 0; 0 K→°C -273.15; 1 gal→l 3.785411784; 1000 ml→l 1; 36 km/h→m/s 10; 60 mph→km/h 96.56064; 5 km→km 5; -10 m→ft -32.808398950131235.
  - `test_formatta_risultato`: `esegui_conversione({"value": 10, "from_unit": "km", "to_unit": "mi"}) == ("10 km = 6.21371 mi", False)`.
  - `test_sinonimi` parametrico: `KM`→km, `miglia`→mi, `celsius`→°C, `C`→°C, `kph`→km/h, `L`→l, `MPH`→mph, `M`→m, `MIN`→min, `MI`→mi, `K`→K, ` kg `→kg (verifica sul campo validato di `RichiestaConversione`).
  - `test_unita_sconosciuta`: `esegui_conversione` con `from_unit="anni luce"` → `("Errore: unità 'anni luce' non ammessa. Unità ammesse: mm, …, mph", True)` (stringa completa).
  - `test_grandezze_incompatibili`: 5 kg→m → `("Errore: impossibile convertire 'kg' (massa) in 'm' (lunghezza): grandezze diverse", True)`.
  - `test_sotto_zero_assoluto`: -300 °C→K → testo esatto sopra; `-1 K`, `-460 °F` errore; `-273.15 °C` ammesso.
  - `test_valore_non_valido` parametrico su `"dieci"`, `float("nan")`, `float("inf")`, `True`, `None`: testo `Errore: il valore deve essere un numero finito`; `"10"` invece è accettato.
  - `test_argomento_mancante`: `{"value": 5, "from_unit": "km"}` → `Errore: argomento 'to_unit' mancante`.
  - `test_piu_errori`: `{"value": "x", "from_unit": "ly"}` → un solo prefisso `Errore: `, tre messaggi separati da `; `.
- [ ] **Step 2: eseguire e vedere fallire**: `.\venv\Scripts\python.exe -m pytest tests/test_convertitore.py -q` → errore di import di `convertitore`.
- [ ] **Step 3: implementare `convertitore.py`.** Fattori verso unità base (m, kg, s, l, m/s); temperatura via conversione a kelvin. Il bool va rifiutato con un validatore «before» su `value` (Pydantic lax converte `True` in `1.0`). `messaggio_errore` usa `err["type"]`: `value_error` → testo del `ValueError` originale (`err["ctx"]["error"]`, senza il prefisso «Value error,»); `missing` → argomento mancante; tipi su `value` (`float_parsing`, `float_type`, `finite_number`, …) → numero finito. I messaggi della `model_validator` hanno `loc` vuota.
- [ ] **Step 4: test verdi**: stesso comando → tutti PASS; poi suite completa `.\venv\Scripts\python.exe -m pytest -q` → PASS (nessun test esistente toccato).

### Task 2: server MCP stdio in `convertitore.py` + dipendenza `mcp`

**Files:**
- Modify: `convertitore.py` (sezione finale «server MCP»)
- Modify: `requirements.txt` (aggiungere `mcp==2.3.0` e tutte le dipendenze transitive fissate, come già fatto per le altre)
- Test: `tests/test_convertitore_mcp.py`

**Interfaces:**
- Consumes: `esegui_conversione`, `RichiestaConversione` (Task 1).
- Produces:
  - `NOME_STRUMENTO = "convert_units"`, `DESCRIZIONE: str` (cosa fa, che usa i simboli dello schema, che accetta alcune varianti, che `gal` è il gallone USA, che le grandezze diverse non si convertono).
  - `crea_server() -> mcp.server.lowlevel.Server` con `on_list_tools` (un solo `Tool`, `input_schema=RichiestaConversione.model_json_schema()`) e `on_call_tool` (nome diverso → `CallToolResult` con `is_error=True`, `Errore: strumento 'X' non disponibile`; altrimenti `esegui_conversione` → `TextContent`, `is_error` dal secondo elemento).
  - `main() -> None` che esegue il server su `stdio_server()` con `anyio.run`; `if __name__ == "__main__": main()`. Avvio: `python convertitore.py`.

- [ ] **Step 1: installare la dipendenza**: `.\venv\Scripts\python.exe -m pip install mcp==2.3.0`, poi aggiornare `requirements.txt` con le versioni effettivamente installate (`pip freeze`), aggiungendo il marcatore win32 a `pywin32`. Verificare che la suite esistente resti verde (`anyio` potrebbe salire di versione).
- [ ] **Step 2: test che falliscono** in `tests/test_convertitore_mcp.py`, con `mcp.Client(crea_server())` in-process (dentro `anyio.run` o `asyncio.run` nel test sincrono):
  - `test_un_solo_strumento_con_schema`: `list_tools` → un solo strumento `convert_units`; `input_schema["properties"]["to_unit"]["enum"] == list(UNITA)`.
  - `test_chiamata_riuscita`: 10 km→mi → `is_error False`, testo `10 km = 6.21371 mi`.
  - `test_chiamata_incompatibile`: 5 kg→m → `is_error True`, testo dell'errore del Task 1.
  - `test_unita_fuori_elenco_messaggio_italiano`: `anni luce` → `is_error True`, testo inizia con `Errore: unità 'anni luce' non ammessa`.
  - `test_sinonimo_accettato`: 10 `KM`→`miglia` → testo `10 km = 6.21371 mi` (nel risultato compaiono i simboli normalizzati).
  - `test_strumento_sconosciuto`: nome `pippo` → `is_error True`.
  - `test_server_vero_via_stdio`: `Client(StdioServerParameters(command=sys.executable, args=[<percorso assoluto di convertitore.py>]))`: 100 `°C`→`°F` → `100 °C = 212 °F` (il `°` attraversa intatto il trasporto stdio) e 5 kg→m con `is_error True`.
- [ ] **Step 3: vedere fallire** (`crea_server` assente).
- [ ] **Step 4: implementare lo strato MCP** (come sopra; nessuna logica di conversione qui).
- [ ] **Step 5: test verdi** + suite completa verde.

### Task 3: ponte sincrono `assistente/mcp_remoto.py`

**Files:**
- Create: `assistente/mcp_remoto.py`
- Create: `tests/server_che_muore.py` (server di prova per il Review Focus 4)
- Test: `tests/test_mcp_remoto.py`

**Interfaces:**
- Consumes: `convertitore.py` avviabile come script (Task 2).
- Produces:
  - `FILE_CONVERTITORE: Path` = cartella del progetto / `convertitore.py`.
  - `parametri_convertitore() -> StdioServerParameters` (`command=sys.executable`, `args=[str(FILE_CONVERTITORE)]`).
  - `class ErroreMCP(Exception)`: il server non si avvia o non risponde all'apertura.
  - `class ClientMCP`:
    - `@classmethod apri(cls, parametri: StdioServerParameters, timeout: float = 20.0) -> ClientMCP` — avvia un thread daemon con `asyncio.run`, dentro `async with mcp.Client(parametri)`, legge `list_tools`, segnala pronto (`threading.Event`), poi attende un `asyncio.Event` di stop. Fallimento o timeout → chiude il thread e solleva `ErroreMCP`.
    - `strumenti(self) -> list[BaseTool]` — uno `StructuredTool` per strumento remoto: `name`, `description`, `args_schema=<input_schema dict grezzo>` (LangChain allora non rivalida: verificato), `func` che chiama `chiama`.
    - `chiama(self, nome: str, argomenti: dict, timeout: float = 30.0) -> str` — `asyncio.run_coroutine_threadsafe(client.call_tool(...), loop).result(timeout)`; testo dei `TextContent` uniti; se `is_error` e il testo non inizia con `Errore:`, aggiunge il prefisso; qualsiasi eccezione (server morto, timeout) → log `WARNING` sul logger `"mcp"` e ritorno `Errore: server MCP non raggiungibile`.
    - `chiudi(self) -> None` — idempotente; imposta lo stop, `join` del thread con timeout; il `Client` chiude il processo figlio.
- [ ] **Step 1: test che falliscono** (usano il server vero via stdio, nessun modello):
  - `test_apre_e_espone_convert_units`: `apri(parametri_convertitore())`, `strumenti()` → un tool `convert_units`; `convert_to_openai_tool(tool)["function"]["parameters"]["properties"]["from_unit"]["enum"]` contiene `"°C"`; `chiudi()`.
  - `test_invoke_passa_argomenti_intatti`: `tool.invoke({"value": 10, "from_unit": "KM", "to_unit": "miglia"}) == "10 km = 6.21371 mi"` (il sinonimo arriva al server senza essere rifiutato da LangChain).
  - `test_errore_dal_server`: kg→m → stringa che inizia con `Errore: impossibile convertire`.
  - `test_server_che_non_parte`: parametri con `args=["-c", "import sys; sys.exit(1)"]` → `ErroreMCP` entro il timeout.
  - `test_server_morto_a_meta` (Review Focus 4): server di prova `tests/server_che_muore.py` (Server di basso livello con uno strumento `muori` il cui handler esegue `os._exit(1)`); `apri` riesce, `chiama("muori", {}, timeout=5)` ritorna `Errore: server MCP non raggiungibile` entro il timeout, e una seconda chiamata ritorna lo stesso errore senza bloccarsi.
  - `test_chiudi_idempotente_e_thread_finito` (Review Focus 5): `chiudi()` due volte senza errori; il thread non è più vivo.
- [ ] **Step 2: vedere fallire.**
- [ ] **Step 3: implementare** come da interfaccia.
- [ ] **Step 4: test verdi** + suite completa verde.

### Task 4: collegamento nell'assistente, prompt, Docker, documentazione

**Files:**
- Modify: `assistente/terminale.py` (`main`)
- Modify: `assistente/sessione.py` (`PROMPT_SISTEMA`)
- Modify: `Dockerfile` (`COPY convertitore.py .`)
- Modify: `README.md`, `CLAUDE.md`
- Modify: `tests/test_terminale.py`, `tests/test_sessione.py` (solo aggiunte), `tests/test_reale.py` (due casi reali)

**Interfaces:**
- Consumes: `ClientMCP`, `ErroreMCP`, `parametri_convertitore` (Task 3).
- Produces: `collega_convertitore(parametri: StdioServerParameters | None = None) -> ClientMCP | None` in `terminale.py`: `None` e log `WARNING` «convertitore MCP non disponibile: …» se `ErroreMCP`.

- [ ] **Step 1: test che falliscono**:
  - `test_collega_convertitore_fallito`: parametri che escono subito → `None`, warning nel log (`caplog`).
  - `test_collega_convertitore_riuscito`: `parametri_convertitore()` → istanza con `convert_units`; `chiudi()`.
  - `test_prompt_cita_convertitore`: `"convert_units" in PROMPT_SISTEMA` e il prompt dice di non calcolare a mente.
  - In `test_reale.py` (marker `reale`, attivati con `RUN_REAL_TESTS=1`): «converti 10 km in miglia» → la risposta contiene `6,2` o `6.2`; «converti 5 kg in metri» → la risposta non contiene numeri inventati per i metri e il log/la cronologia mostra la chiamata a `convert_units` con errore. Usare l'assistente vero con `collega_convertitore()`.
- [ ] **Step 2: vedere fallire.**
- [ ] **Step 3: implementare**:
  - `main`: dopo `configura_log`, `remoto = collega_convertitore()`; `strumenti = [crea_orologio(), *(remoto.strumenti() if remoto else [])]`; intestazione con una seconda riga `Convertitore di unità (MCP): attivo` / `non disponibile`; `esegui_chat` dentro `try/finally` che chiama `remoto.chiudi()`.
  - `PROMPT_SISTEMA`: aggiungere «Per convertire unità di misura usa sempre lo strumento convert_units e non fare i calcoli a mente. Se lo strumento restituisce un errore, spiegalo all'utente senza inventare un risultato.»
  - `Dockerfile`: copiare `convertitore.py` accanto ad `assistente/`.
  - `README.md`: sezione sul convertitore (cosa fa, unità ammesse, avvio isolato `python convertitore.py`, diagnosi «non disponibile»); `CLAUDE.md`: struttura (`convertitore.py`, `assistente/mcp_remoto.py`), obiettivo con il convertitore MCP, togliere «MCP … non anticiparli» e la regola sul branch (ora si lavora su `feature/nuove-funzionalita`).
- [ ] **Step 4: test automatici verdi**: `.\venv\Scripts\python.exe -m pytest -q`.

### Task 5: prove reali (LM Studio e Docker)

- [ ] **Step 1: LM Studio**: `$env:RUN_REAL_TESTS="1"; .\venv\Scripts\python.exe -m pytest -m reale -v -s` → PASS dei casi nuovi e vecchi; poi chat a mano con `.\venv\Scripts\python.exe -m assistente`: «converti 10 km in miglia», «converti 5 kg in metri», «quanti gradi Fahrenheit sono 30 gradi?». Annotare l'esito nel resoconto (una risposta simulata non vale come prova).
- [ ] **Step 2: Docker**: `docker compose build`, poi `docker compose run --rm assistente` con le stesse domande; l'intestazione deve dire «attivo».
- [ ] **Step 3: resoconto** all'utente: cosa è stato eseguito, con quale esito, cosa resta da provare. Nessun commit: si aspetta l'indicazione dell'utente.
