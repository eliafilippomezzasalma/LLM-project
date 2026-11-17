# Riassunto della cronologia — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un nodo LLM `riassunto`, primo del grafo, che sopra una soglia configurabile (messaggi o token stimati) sostituisce i turni vecchi con un riassunto tenuto nel campo `riassunto` dello stato, conservando interi la domanda nuova e gli ultimi N turni e senza mai separare una chiamata dal suo `ToolMessage`.

**Architecture:** nuovo modulo `assistente/riassunto.py` (conteggio, taglio, presentazione dei messaggi tolti, chiamata con fail-open, client, aggiunta del riassunto a un testo di sistema), sul modello di `router.py`/`revisore.py`. `grafo.py` aggiunge il nodo `riassunto` tra START e `router`, il campo `riassunto` nello stato, e passa il riassunto ad agente, router e revisore. `Sessione` conserva cronologia **e** riassunto, li passa al grafo e li sostituisce solo se il turno riesce, ricavando la cronologia nuova dai messaggi del grafo (strada A, §19.2).

**Tech Stack:** Python 3.12, LangGraph Graph API (`RemoveMessage` con `add_messages`), `langchain-openai`, Pydantic, pytest. Nessuna dipendenza nuova.

**Spec:** `specs.md` §19 (approvata il 2026-11-16); contesto §6.2, §17, §18.

## Global Constraints

- Solo in `lezione_4/`, branch `feature/nuove-funzionalita`, partendo da `2eea005`. La §16 di `specs.md` e `COPIONE.md` non si toccano.
- **Nessun commit né push: lo decide l'utente.** Ogni task finisce con la suite completa verde al posto del commit.
- Comandi da `lezione_4/` (PowerShell): `.\venv\Scripts\python.exe -m pytest -q`; reali `$env:RUN_REAL_TESTS="1"; .\venv\Scripts\python.exe -m pytest -m reale -v -s`.
- Configurazione: `RIASSUNTO_SOGLIA_TIPO` ∈ {`messaggi`, `token`} (predefinito `messaggi`), `RIASSUNTO_SOGLIA` intero ≥ 1 (predefinito `10`), `RIASSUNTO_TURNI_DA_TENERE` intero ≥ 1 (predefinito `2`); non valido → `ErroreConfigurazione` che nomina la variabile.
- Conteggio: messaggi esclusi i `SystemMessage`, domanda nuova compresa; token stimati = `ceil(caratteri / 4)` su testo dei messaggi + `json.dumps(args, ensure_ascii=False)` delle chiamate. Si riassume solo se conteggio **>** soglia.
- Taglio sempre su un `HumanMessage`; conservati la domanda nuova + gli ultimi N turni completi.
- Modello del riassunto: stesso `LM_BASE_URL`/`LM_MODEL`, nessuno strumento, `extra_body=RAGIONAMENTO_DISATTIVATO`, `timeout=TIMEOUT_RIASSUNTO_SECONDI = 60`, `max_retries=0`, testo libero ripulito con `pulisci_ragionamento`.
- Fail-open: eccezione, testo vuoto o controllo delle coppie fallito → nessun messaggio tolto, riassunto invariato, WARNING, il turno prosegue.
- Log (logger `riassunto`, INFO salvo dove indicato), con `S` = soglia e unità `""` in modalità messaggi o `" token"` in modalità token:
  - `<n> messaggi, sotto la soglia (<S><unità>), nessuna chiamata`
  - `<n> messaggi, sopra la soglia (<S><unità>) ma niente da togliere, nessuna chiamata`
  - `<prima> -> <dopo> messaggi (tolti <k>, conservati <N> turni)`
  - in modalità token, dopo `<n> messaggi` / `<dopo> messaggi` si aggiunge ` (~<t> token stimati)`
  - WARNING `risposta non valida (<errore>), cronologia invariata`; WARNING `taglio non valido (chiamata separata dal suo risultato), cronologia invariata`
  - DEBUG: messaggi inviati e testo del riassunto nuovo.
- Il riassunto **non** è un messaggio: vive in `stato["riassunto"]` (stringa, `""` = nessuno). Ad agente, router e revisore arriva in coda al loro **unico** messaggio di sistema come `"\n\nRiassunto della conversazione precedente: <testo>"`. Con riassunto vuoto i messaggi inviati sono **identici** a oggi.
- Il riassunto non riporta i risultati degli strumenti (i `ToolMessage` non vengono presentati al modello del riassunto).

## Review Focus

1. Due compressioni in turni consecutivi della stessa `Sessione`: i messaggi conservati hanno già un id dal turno prima, quelli nuovi no; `RemoveMessage` deve togliere esattamente quelli giusti → test nel Task 4.
2. Dopo la compressione il revisore deve vedere nel «turno corrente» solo le chiamate di questo turno (`inizio_turno` calcolato dopo il taglio) → test nel Task 3.
3. Turno che fallisce dopo una compressione (limite strumenti, errore del modello): cronologia e riassunto di `Sessione` invariati, e al turno dopo la compressione si rifà → test nel Task 4.
4. Turni di rifiuto del router (`[Human, AI(rifiuto)]`) nella parte tolta: presentati come scambio normale, il riassunto li annota come rifiutati (istruzioni) → test nel Task 2 sulle istruzioni e sulla presentazione.
5. Riassunto con `<think>` o solo spazi → ripulito; vuoto → fail-open → test nel Task 2.

---

### Task 0: verifica di partenza e regressione «prima» (controllore, in sessione)

- [ ] **Step 1:** `git log -1 --oneline` → `2eea005`; `git status --short` → solo `M lezione_4/specs.md`, `?? lezione_4/COPIONE.md`, il piano.
- [ ] **Step 2:** suite → atteso `436 passed, 21 skipped` (annotare il numero reale).
- [ ] **Step 3:** ricostruire la regressione di §17.9 (15 domande in ambito: almeno una per strumento, «e a Roma?», «che giorno è oggi?», un saluto, una fuori ambito, due domande in due parti) e salvarla in `repo-lab-llm/.superpowers/sdd/2026-11-16-riassunto-cronologia/regressione.txt` (così resta). Eseguirla **prima di toccare il codice** con l'app vera via stdin (`PYTHONIOENCODING=utf-8 LOG_LEVEL=INFO`), una sessione sola; salvare l'uscita accanto come `regressione_prima.txt`.

### Task 1: configurazione e ambito allargato

**Files:** Modify `assistente/config.py`, `.env.example`, `.env` (locale, fuori da Git: dirlo all'utente); Test `tests/test_config.py`

**Interfaces:**
- Produces: in `config.py` `@dataclass(frozen=True) class SogliaRiassunto: tipo: Literal["messaggi", "token"] = "messaggi"; valore: int = 10; turni_da_tenere: int = 2`; `Config.riassunto: SogliaRiassunto = SogliaRiassunto()` (ultimo campo, con predefinito, così le `Config(...)` dei test restano valide).

- [ ] **Step 1: test che falliscono:** `test_riassunto_predefinito` (nessuna variabile → `SogliaRiassunto("messaggi", 10, 2)`); `test_riassunto_token` (`token`, `5000`, `3`); `test_riassunto_tipo_maiuscolo_e_spazi` (`" Token "` → `"token"`); `test_riassunto_non_valido` parametrico: `RIASSUNTO_SOGLIA_TIPO="parole"`, `RIASSUNTO_SOGLIA` ∈ {`"0"`, `"-1"`, `"dieci"`}, `RIASSUNTO_TURNI_DA_TENERE` ∈ {`"0"`, `"1.5"`} → `pytest.raises(ErroreConfigurazione, match=<nome variabile>)`; `test_valori_completi` include `riassunto`.
- [ ] **Step 2:** `pytest tests/test_config.py -q` → FAIL.
- [ ] **Step 3:** implementare sul modello di `_max_tool_steps`. `.env.example`: blocco commentato con le tre variabili e i predefiniti; `AMBITO_ASSISTENTE` allargato (stesso testo di oggi + «, e domande su ciò che l'utente ha detto nella conversazione, come il suo nome o le sue preferenze»), su una riga; stessa riga nel `.env` locale.
- [ ] **Step 4:** suite completa verde.

### Task 2: modulo `riassunto.py`

**Files:** Create `assistente/riassunto.py`, `tests/test_riassunto.py`; Modify `tests/finti.py`

**Interfaces:**
- Consumes: `Config`, `SogliaRiassunto` (Task 1); `CHIAVE_SEGNAPOSTO`, `RAGIONAMENTO_DISATTIVATO`, `pulisci_ragionamento` (`modello.py`).
- Produces:
  - `TIMEOUT_RIASSUNTO_SECONDI = 60`; `PREFISSO_RIASSUNTO = "Riassunto della conversazione precedente:"`; `ISTRUZIONI_RIASSUNTO: str`.
  - `conversazione(messaggi: list[AnyMessage]) -> list[AnyMessage]` — i messaggi senza i `SystemMessage`.
  - `stima_token(messaggi: list[AnyMessage]) -> int`
  - `misura(messaggi: list[AnyMessage], tipo: str) -> int` — su `conversazione(messaggi)`.
  - `punto_di_taglio(conversazione: list[AnyMessage], turni_da_tenere: int) -> int` — indice (nella conversazione) del primo messaggio conservato; `0` = niente da togliere. Indici degli `HumanMessage` = inizi dei turni; l'ultimo è la domanda nuova; taglio = `inizi[-(turni_da_tenere + 1)]` se `len(inizi) > turni_da_tenere + 1`, altrimenti `0`.
  - `coppie_complete(messaggi: list[AnyMessage]) -> bool` — ogni tool_call ha un `ToolMessage` con lo stesso id e ogni `ToolMessage` ha la sua chiamata.
  - `testo_con_riassunto(testo_sistema: str, riassunto: str) -> str` — invariato se `riassunto` è vuoto o solo spazi, altrimenti `f"{testo_sistema}\n\n{PREFISSO_RIASSUNTO} {riassunto}"`.
  - `messaggi_con_riassunto(messaggi: list[AnyMessage], riassunto: str) -> list[AnyMessage]` — sostituisce il **primo** `SystemMessage` con uno che ha `testo_con_riassunto(...)`; stessa lista (stessi oggetti) se il riassunto è vuoto.
  - `messaggi_per_riassunto(precedente: str, tolti: list[AnyMessage]) -> list[BaseMessage]` — `SystemMessage(ISTRUZIONI_RIASSUNTO)` + un `HumanMessage` con `Riassunto precedente: <testo o "(nessuno)">`, poi `Messaggi da riassumere:` e una riga per messaggio: `Utente: <testo>` / `Assistente: <testo ripulito>` (solo se non vuoto) / `Assistente (chiamata a strumento): <nome>(<argomenti JSON>)` per ogni tool_call. I `ToolMessage` non compaiono.
  - `riassumi(modello: Runnable, precedente: str, tolti: list[AnyMessage]) -> str | None` — testo ripulito; `None` + WARNING se eccezione o testo vuoto.
  - `crea_riassuntore(config: Config) -> Runnable` — `ChatOpenAI` senza strumenti, senza output strutturato.
  - in `tests/finti.py`: `RiassuntoreFinto(testi: list[str | Exception])` — stesso comportamento di `RouterFinto` ma restituisce `AIMessage(testo)`; `SOGLIA_ALTA = SogliaRiassunto("messaggi", 1000, 2)`.

Istruzioni (da affinare nel Task 5, max 3 giri): componente di memoria; riceve riassunto precedente e messaggi vecchi; scrive **un unico** riassunto aggiornato che sostituisce il precedente e ne conserva le informazioni ancora utili; italiano, terza persona, al massimo ~120 parole; conserva nome e altri dati personali, preferenze (per esempio le unità), che cosa ha chiesto con i dati della domanda («ha chiesto di convertire 5 miglia in km»), le richieste fuori ambito **annotate come rifiutate**; **non** riporta risultati degli strumenti né valori delle risposte (orari, conversioni, risultati di calcoli, date, conteggi di giorni); solo il riassunto, senza titoli né commenti.

- [ ] **Step 1: test che falliscono** in `tests/test_riassunto.py` (aiuto locale `_turno(domanda, risposta, chiamate=())` che costruisce `[Human, (AI con tool_calls, ToolMessage)…, AI(risposta)]`):
  - `test_conta_messaggi_senza_sistema`: `[System, H, A, H]` → `misura(..., "messaggi") == 3`.
  - `test_stima_token`: `[System("x"*400), H("a"*10), AI("", tool_calls=[{"name": "calculate", "args": {"expression": "2+2"}, ...}])]` → `ceil((10 + len('{"expression": "2+2"}')) / 4)`.
  - `test_taglio_tiene_domanda_e_ultimi_n_turni`: 4 turni + domanda, N=2 → taglio all'inizio del 3° turno.
  - `test_taglio_niente_da_togliere`: 2 turni + domanda, N=2 → `0`; 1 turno + domanda → `0`.
  - `test_taglio_mai_tra_chiamata_e_risultato`: turni con più tool_call in un messaggio e più giri di strumenti; per ogni N da 1 a 4, `coppie_complete(conv[taglio:])` e `coppie_complete(conv[:taglio])` veri.
  - `test_coppie_complete`: vero sui turni normali; falso per chiamata senza `ToolMessage` e per `ToolMessage` orfano.
  - `test_testo_con_riassunto`: vuoto/spazi → invariato; altrimenti termina con `"Riassunto della conversazione precedente: Si chiama Elia."`.
  - `test_messaggi_con_riassunto`: vuoto → `is` la stessa lista; con testo → un solo `SystemMessage`, in testa, che contiene prompt e riassunto; gli altri messaggi identici.
  - `test_presentazione_dei_tolti` (Review Focus 4): turno con `convert_units` + `ToolMessage("5 mi = 8,0467 km")` e turno di rifiuto `[H("ricetta della carbonara"), AI("Non posso aiutarti.")]` → il testo contiene `"Utente: ricetta della carbonara"`, `"Assistente: Non posso aiutarti."`, `'convert_units({"value": 5'` e **non** contiene `"8,0467"`; riassunto precedente presente o `"(nessuno)"`.
  - `test_istruzioni`: contengono «nome», «preferenze», «rifiutat», «non riportare» (o forma equivalente decisa, fissata nel test).
  - `test_riassumi_ripulisce` (Review Focus 5): `RiassuntoreFinto(["<think>x</think> Si chiama Elia. "])` → `"Si chiama Elia."`.
  - `test_riassumi_fail_open(caplog)`: eccezione, `""`, `"   "`, `"<think>x</think>"` → `None` + WARNING `riassunto` con `"cronologia invariata"`.
  - `test_crea_riassuntore_usa_config`: come `test_crea_router_usa_config` (`request_timeout == 60`, `max_retries == 0`, `extra_body`, nessuno strumento).
- [ ] **Step 2:** `pytest tests/test_riassunto.py -q` → FAIL.
- [ ] **Step 3:** implementare come descritto sopra.
- [ ] **Step 4:** suite completa verde.

### Task 3: nodo `riassunto` nel grafo e riassunto ai tre nodi

**Files:** Modify `assistente/grafo.py` (docstring di testa con il disegno di §19.3, stato, nodo, archi, limite di ricorsione), `assistente/router.py`, `assistente/revisore.py`, `tests/finti.py`, `tests/test_grafo.py`, `tests/test_router.py`, `tests/test_revisore.py`, i `costruisci_grafo` diretti in `tests/test_sessione.py` e `tests/test_reale.py`

**Interfaces:**
- Consumes: Task 2; `SogliaRiassunto` (Task 1).
- Produces:
  - `StatoAssistente` + `riassunto: NotRequired[str]`.
  - `costruisci_grafo(modello, registro, max_passi, *, router, ambito, messaggio_rifiuto, revisore, max_revisioni, riassuntore: Runnable, soglia: SogliaRiassunto)`; arco `START → riassunto → router`; `recursion_limit` di oggi `+ 1`.
  - Nodo `riassunto`: `conv = conversazione(messages)`; sotto soglia → log, `{}`; `taglio = punto_di_taglio(conv, soglia.turni_da_tenere)`; `0` → log «niente da togliere», `{}`; `not coppie_complete(conv[taglio:])` → WARNING, `{}`; `riassumi(riassuntore, stato.get("riassunto", ""), conv[:taglio])` `None` → `{}`; altrimenti `{"messages": [RemoveMessage(id=m.id) for m in conv[:taglio]], "riassunto": nuovo}` + log prima/dopo.
  - Agente: `modello.invoke(messaggi_con_riassunto(stato["messages"], stato.get("riassunto", "")))`.
  - Router: `messaggi_per_router(messaggi, ambito, riassunto: str = "")` e `classifica(router, messaggi, ambito, riassunto: str = "")`: le istruzioni passano da `testo_con_riassunto`.
  - Revisore: `messaggi_per_revisore(..., mista=None, riassunto: str = "")` e `rivedi(..., mista=None, riassunto: str = "")`: idem sulle istruzioni del revisore.
  - `finti.grafo_in_ambito(..., riassuntore=None, soglia=SOGLIA_ALTA)`: `riassuntore` predefinito `RiassuntoreFinto(["riassunto di prova"])`. Con `SOGLIA_ALTA` i test esistenti non cambiano comportamento.

- [ ] **Step 1: test che falliscono** in `tests/test_grafo.py` (`test_grafo_ha_nodi_espliciti` aggiornato con `riassunto`):
  - `test_sotto_soglia_nessuna_chiamata(caplog)` (evidenza 3): soglia 10, 2 turni + domanda → `riassuntore.chiamate == []`, messaggi del grafo invariati, record `riassunto` con `"sotto la soglia (10)"` e `"nessuna chiamata"`.
  - `test_sopra_soglia_riassume(caplog)` (evidenza 1): soglia 10, N=2, 5 turni di 2 messaggi + domanda (11) → una chiamata; stato finale: `[System, ultimi 2 turni, domanda, risposta]`; `stato["riassunto"] == "riassunto nuovo"`; record `"11 -> 5 messaggi (tolti 6, conservati 2 turni)"`.
  - `test_riassunto_sostituito_non_accumulato`: ingresso con `riassunto="vecchio"` → il riassuntore riceve `"vecchio"` nel testo; `stato["riassunto"] == "nuovo"` e `"vecchio"` non compare in nessun messaggio.
  - `test_niente_da_togliere(caplog)`: soglia 3, 2 turni + domanda → nessuna chiamata, record «niente da togliere».
  - `test_modalita_token(caplog)`: `SogliaRiassunto("token", 50, 1)` sopra e sotto soglia → riga con `"token stimati"`.
  - `test_riassunto_in_errore_fail_open(caplog)`: `RiassuntoreFinto([ConnectionError()])` → messaggi intatti, riassunto invariato, WARNING, risposta dell'agente regolare.
  - `test_agente_vede_il_riassunto`: con `riassunto="Si chiama Elia."` il primo messaggio della chiamata al modello è l'unico `SystemMessage` e termina con il riassunto; con `""` è identico al prompt.
  - `test_router_e_revisore_vedono_il_riassunto`: le istruzioni ricevute da `RouterFinto` e `RevisoreFinto` contengono il riassunto quando c'è e sono identiche a oggi quando non c'è.
  - `test_revisore_dopo_il_taglio_solo_il_turno_corrente` (Review Focus 2): turni vecchi con `get_current_time`, compressione, turno corrente con `convert_units` → il messaggio del turno al revisore contiene `convert_units` e non `get_current_time`.
  - `test_rifiuto_dopo_compressione`: router `[FUORI]` sopra soglia → riassunto fatto, rifiuto restituito.
- [ ] **Step 2:** test unitari in `tests/test_router.py` e `tests/test_revisore.py`: `messaggi_per_router`/`messaggi_per_revisore` con e senza riassunto (senza: uguali all'uscita di oggi).
- [ ] **Step 3:** `pytest tests/test_grafo.py tests/test_router.py tests/test_revisore.py -q` → FAIL.
- [ ] **Step 4:** implementare; aggiornare gli altri `costruisci_grafo` diretti (`test_sessione.py`, `test_reale.py`: in `test_reale.py` `riassuntore=crea_riassuntore(config)`, `soglia=config.riassunto`).
- [ ] **Step 5:** suite completa verde (reali saltati).

### Task 4: `Sessione` con riassunto e collegamento

**Files:** Modify `assistente/sessione.py`, `assistente/terminale.py` (`main`), `tests/test_sessione.py`

**Interfaces:**
- Consumes: `costruisci_grafo(..., riassuntore=, soglia=)` (Task 3); `crea_riassuntore`, `config.riassunto`.
- Produces: `Sessione.riassunto: str` (iniziale `""`). `chiedi` invoca il grafo con `{"messages": [*cronologia, domanda], "passi_strumento": 0, "riassunto": self.riassunto}`; se il turno riesce: `inizio = stato["inizio_turno"]`, `nuova = stato["messages"][:inizio]` (già accorciata), passaggi e risultati della nota da `stato["messages"][inizio + 1:]`, poi `self.cronologia = [*nuova, domanda, *chiamate, AIMessage(testo)]` e `self.riassunto = stato.get("riassunto", "")`. Turno fallito → nulla cambia. `main` passa `riassuntore=crea_riassuntore(config)`, `soglia=config.riassunto`.

- [ ] **Step 1: test che falliscono** in `tests/test_sessione.py` (grafo con soglia bassa, `SogliaRiassunto("messaggi", 6, 1)`, e `RiassuntoreFinto(["r1", "r2", "r3"])`):
  - `test_cronologia_accorciata_e_riassunto_conservato`: 4 turni → dopo il turno che supera la soglia, `sessione.riassunto == "r1"` e la cronologia è `[System, ultimo turno conservato, turno appena fatto]`.
  - `test_due_compressioni_consecutive` (Review Focus 1): turni fino a due compressioni → `riassunto == "r2"`, il riassuntore della seconda riceve `"r1"`, nessun messaggio duplicato o perso tra quelli da conservare.
  - `test_turno_fallito_non_tocca_riassunto_ne_cronologia` (Review Focus 3): turno sopra soglia che finisce con `LimitePassaggiRaggiunto` (e uno con errore del modello) → cronologia e `riassunto` uguali a prima; il turno dopo riassume di nuovo.
  - `test_cronologia_dopo_compressione_senza_revisioni`: turno con `[RESPINTA, APPROVATA]` dopo una compressione → nessun `"[Revisione]"` né risposta respinta in cronologia.
  - `test_nota_dopo_compressione`: `compute_deadline` al 1° turno (nota consegnata), compressione, `compute_deadline` di nuovo → nota non ripetuta; in una sessione nuova, `compute_deadline` nel turno che comprime → nota aggiunta.
  - `test_chiamate_conservate_dopo_compressione`: le chiamate di `STRUMENTI_IN_CRONOLOGIA` del turno corrente restano con i loro risultati.
- [ ] **Step 2:** `pytest tests/test_sessione.py -q` → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** suite completa verde.

### Task 5: primo controllo reale, test reali e documentazione

**Files:** Modify `tests/test_reale.py`, `README.md`, `CLAUDE.md`, `specs.md` (§6.2 rimando a §19; stato di §19), `assistente/riassunto.py` (solo `ISTRUZIONI_RIASSUNTO`, se serve)

- [ ] **Step 1 (controllore, usa-e-getta):** con l'agente vero, `[System(PROMPT_SISTEMA + riassunto), turni conservati, domanda]` → nessun errore HTTP del template. Se fallisce, **fermarsi e riportarlo all'utente**.
- [ ] **Step 2 (controllore):** `riassumi` vero su 3 casi preparati (nome + conversione + rifiuto; seguito; con riassunto precedente) → leggere i testi: nome, preferenze e argomenti presenti, rifiuto annotato, nessun risultato degli strumenti. Ritocchi delle istruzioni al massimo 3 giri, tenere il migliore (aggiornare `test_istruzioni`).
- [ ] **Step 3:** reali nuovi in `tests/test_reale.py`:
  - `test_nome_del_primo_turno_dopo_la_compressione_reale(caplog)` (evidenza 2): `Sessione` con grafo vero e `SogliaRiassunto("messaggi", 6, 1)`; «Ciao, mi chiamo Elia», due turni con strumenti, «Come mi chiamo?» → record `riassunto` con `" -> "` prima dell'ultima domanda, la cronologia non contiene più «mi chiamo Elia», la risposta contiene `"Elia"`.
  - `test_seguito_dopo_la_compressione_reale`: «Converti 5 miglia in km», turni che lo fanno finire nel riassunto, «e in piedi?» → chiamata a `convert_units` con `value` 5 e unità di partenza miglia.
  - `test_router_domande_sulla_conversazione_reale`: router vero con l'ambito allargato: «come mi chiamo?» e «che unità ti ho chiesto di usare?» → `conversazione`; ricetta, politica, barzelletta → `fuori_ambito`.
- [ ] **Step 4:** `README.md`: le tre variabili, il nodo nel grafo, le righe di log `riassunto`, paragrafo «Misure del riassunto» da riempire nel Task 6. `CLAUDE.md`: `riassunto` nella struttura e una riga nell'obiettivo (§19). `specs.md`: §6.2 rimando a §19.
- [ ] **Step 5:** suite completa verde; reali nuovi verdi.

### Task 6: misure, regressione, Docker e resoconto (controllore, in sessione)

- [ ] **Step 1:** reali completi → annotare n/N e rilanci (attesi i limiti noti del passo 2).
- [ ] **Step 2: misure**, app vera via stdin, `LOG_LEVEL=INFO`, una sessione LM Studio alla volta: almeno 3 conversazioni da ≥ 15 turni con nome al 1° turno, una preferenza, seguiti, strumenti, una domanda fuori ambito e il suo seguito; domande su nome/preferenza dopo la compressione. Contare: informazioni del 1° turno usate bene, seguiti riusciti dopo la compressione, valori a mente o rifiuti del revisore dovuti al riassunto, seguiti fuori ambito ancora rifiutati, guasti del riassunto, tempo aggiunto per turno.
- [ ] **Step 3: regressione «dopo»:** `regressione.txt` del Task 0 → esiti non peggiori di `regressione_prima.txt` (con soglia 10 il riassunto scatterà).
- [ ] **Step 4: Docker:** `docker compose build`; `docker compose run --rm -T assistente` con una conversazione che supera la soglia → righe `riassunto` nel log.
- [ ] **Step 5:** numeri nel README, stato di §19 → «implementata (data)».
- [ ] **Step 6:** resoconto all'utente con le evidenze di §19.8 e cosa resta; **ricordargli i valori realistici** (~5000 token stimati, ultimi 3 turni) da fare se avanza tempo; commit solo su sua richiesta (specs senza §16).
