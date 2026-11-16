# Revisore della risposta — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un nodo LLM `revisore` giudica ogni risposta finale dell'agente (motivo, coerente); se non è coerente la rimanda all'agente con il motivo come indicazione, fino a coerenza o al limite `MAX_REVISIONI`, dopo il quale si restituisce l'ultima risposta con un WARNING.

**Architecture:** nuovo modulo `assistente/revisore.py` (schema `Giudizio`, istruzioni con l'ambito, presentazione del turno, chiamata con fail-open, client con output strutturato), sul modello di `router.py`. `grafo.py` aggiunge i nodi `revisore` e `ultima_risposta`; `instrada` diventa a tre uscite; lo stato riceve `inizio_turno`, `revisioni`, `coerente`, `ultima_proposta`. In `sessione.py` cambia solo `_chiamate_da_conservare` (scarta le chiamate senza risposta).

**Tech Stack:** Python 3.12, LangGraph Graph API, `langchain-openai` (`with_structured_output`, `method="json_schema"`), Pydantic, pytest. Nessuna dipendenza nuova.

**Spec:** `specs.md` §18 (approvata il 2026-11-14); contesto §6.2–§6.4, §15.10, §17.

## Global Constraints

- Solo in `lezione_4/`, branch `feature/nuove-funzionalita`, partendo da `96d46a2`. La §16 di `specs.md` e `COPIONE.md` non si toccano.
- **Nessun commit né push: lo decide l'utente.** Ogni task finisce con la suite completa verde al posto del commit.
- Comandi da `lezione_4/` (PowerShell): `.\venv\Scripts\python.exe -m pytest -q`; reali `$env:RUN_REAL_TESTS="1"; .\venv\Scripts\python.exe -m pytest -m reale -v -s`.
- Revisore: stesso `LM_BASE_URL`/`LM_MODEL`, nessuno strumento, `extra_body=RAGIONAMENTO_DISATTIVATO`, `timeout=TIMEOUT_REVISORE_SECONDI = 60`, `max_retries=0`, `method="json_schema"`. Mai `function_calling`.
- Schema: `motivo` **prima** di `coerente`.
- `MAX_REVISIONI`: intero ≥ 0, predefinito `2`; non valido → `ErroreConfigurazione` che nomina la variabile.
- Fail-open: errore o output non valido del revisore → la risposta passa + `WARNING`.
- Log (logger `revisore`): INFO `coerente=no motivo="<m>" -> agente (revisione <n>/<max>)` | `coerente=sì motivo="<m>" -> fine` | al limite `coerente=no motivo="<m>" -> fine` seguito da WARNING `limite di <max> revisioni raggiunto, restituita l'ultima risposta`; WARNING `risposta non valida (<errore>) -> fine`; WARNING `limite degli strumenti nel tentativo dopo la revisione, restituita l'ultima risposta`; DEBUG messaggi inviati. Motivo sempre su una riga (`" ".join(m.split())`).
- Indicazione all'agente: `HumanMessage` che inizia con `PREFISSO_INDICAZIONE = "[Revisione]"` (formato confermato dal Task 1).
- Rifiuto del router e limite strumenti al primo tentativo non passano dal revisore. Router, agente, strumenti e prompt dell'agente invariati.
- Risposte rifiutate e indicazioni mai nella cronologia di sessione né nella risposta all'utente.

## Review Focus

1. Limite strumenti dopo una revisione: l'`AIMessage` con tool_call senza risposta resta nei messaggi del turno; se `_chiamate_da_conservare` lo conservasse, il turno successivo darebbe HTTP 400 → test nel Task 4 (sessione).
2. Turno successivo a uno con revisione: il router e il revisore non devono vedere né la risposta rifiutata né l'indicazione → test nel Task 4.
3. Più turni con chiamate conservate in cronologia (`get_current_time` del turno prima): il revisore deve mettere nel «turno corrente» solo le chiamate di questo turno → test nel Task 3.
4. Risposta proposta con blocco `<think>` o vuota: il revisore riceve il testo ripulito con `pulisci_ragionamento` (vuota → `(nessuna risposta dal modello)`), senza eccezioni → test nel Task 3.
5. Motivo con a capo e virgolette: una sola riga nel log e indicazione leggibile → test nel Task 4.

---

### Task 0: verifica di partenza (controllore, in sessione)

- [ ] **Step 1:** `git log -1 --oneline` → `96d46a2`; `git status --short` → solo `M specs.md`, `?? COPIONE.md`, il piano.
- [ ] **Step 2:** suite → atteso `362 passed, 11 skipped`.
- [ ] **Step 3:** reali → atteso `11 passed` (in passato 10/11 con rilancio riuscito: annotare).
- [ ] **Step 4:** ricostruire nella scratchpad la prova di regressione di §17.9 (almeno una domanda per strumento, «e a Roma?», «che giorno è oggi?», un saluto, una fuori ambito, più due domande in due parti) ed eseguirla con l'app vera via stdin (`PYTHONIOENCODING=utf-8 LOG_LEVEL=INFO`); salvare stdout/stderr come **riferimento**.

### Task 1: verifiche su LM Studio prima del codice (controllore, usa-e-getta)

- [ ] **Step 1:** script nella scratchpad con `ChatOpenAI(..., timeout=60, max_retries=0, extra_body={"reasoning_effort": "none"}).with_structured_output(Schema, method="json_schema")`, `Schema` = `motivo: str`, `coerente: bool`. Tre casi: risposta completa, risposta parziale, valore a mente → tre oggetti validi.
- [ ] **Step 2:** con il modello dell'agente (`crea_modello` con gli strumenti veri) inviare `[System(PROMPT_SISTEMA), Human("Converti 10 miglia in km e calcola 15 per 4"), <chiamata e risultato di convert_units>, AI("10 miglia sono 16,09 km."), Human("[Revisione] La risposta precedente non va bene: manca il calcolo 15 per 4. Correggila: rispondi di nuovo all'ultima domanda dell'utente.")]` → nessun errore HTTP del template; atteso: chiamata a `calculate` o risposta completa.
- [ ] **Step 3:** se uno dei due fallisce, **fermarsi e riportarlo all'utente** con un ripiego proposto; si prosegue solo dopo il suo assenso.

### Task 2: configurazione `MAX_REVISIONI`

**Files:** Modify `assistente/config.py`, `.env.example`; Test `tests/test_config.py`

**Interfaces:**
- Produces: `Config.max_revisioni: int` (ultimo campo, valore predefinito `2` nel dataclass, così le `Config(...)` esistenti nei test restano valide).

- [ ] **Step 1: test che falliscono:** `test_max_revisioni_predefinito` (assente → `2`); `test_max_revisioni_zero_ammesso` (`"0"` → `0`); `test_max_revisioni_non_valido` per `"-1"`, `"due"`, `"1.5"` → `pytest.raises(ErroreConfigurazione, match="MAX_REVISIONI")`; `test_valori_completi` include `max_revisioni`.
- [ ] **Step 2:** `pytest tests/test_config.py -q` → FAIL.
- [ ] **Step 3:** `_max_revisioni(env) -> int` sul modello di `_max_tool_steps` (soglia ≥ 0, messaggio «MAX_REVISIONI deve essere un intero maggiore o uguale a 0, trovato: …»). In `.env.example`: commento + `MAX_REVISIONI=2`.
- [ ] **Step 4:** suite completa verde.

### Task 3: modulo `revisore.py`

**Files:** Create `assistente/revisore.py`, `tests/test_revisore.py`; Modify `tests/finti.py`

**Interfaces:**
- Consumes: `Config`; `CHIAVE_SEGNAPOSTO`, `RAGIONAMENTO_DISATTIVATO`, `pulisci_ragionamento` da `modello.py`.
- Produces:
  - `class Giudizio(BaseModel)`: `motivo: str = Field(min_length=1)`, poi `coerente: bool`.
  - `TIMEOUT_REVISORE_SECONDI = 60`; `PREFISSO_INDICAZIONE = "[Revisione]"`; `ISTRUZIONI_REVISORE: str` con segnaposto `{ambito}`.
  - `indicazione(motivo: str) -> HumanMessage` — testo `"[Revisione] La risposta precedente non va bene: <motivo su una riga> Correggila: rispondi di nuovo all'ultima domanda dell'utente."`.
  - `messaggi_per_revisore(messaggi: list[AnyMessage], inizio_turno: int, ambito: str) -> list[BaseMessage]`
  - `rivedi(revisore: Runnable, messaggi: list[AnyMessage], inizio_turno: int, ambito: str) -> Giudizio | None`
  - `crea_revisore(config: Config) -> Runnable`
  - in `tests/finti.py`: `RevisoreFinto(esiti: list)` con lo stesso comportamento di `RouterFinto` (ordine, ripete l'ultimo, solleva le eccezioni, `.chiamate`); `APPROVATA = Giudizio(motivo="risponde a tutto", coerente=True)`, `RESPINTA = Giudizio(motivo="manca la seconda parte", coerente=False)`.

`messaggi_per_revisore` restituisce: `SystemMessage(ISTRUZIONI_REVISORE.format(ambito=ambito))`; poi, da `messaggi[:inizio_turno]`, i soli `HumanMessage` e `AIMessage` senza tool_calls con testo (niente `SystemMessage` dell'agente, niente chiamate né `ToolMessage`); infine **un** `HumanMessage` che presenta il turno `messaggi[inizio_turno:]` in testo:
```
Domanda dell'utente: <testo>
Strumenti chiamati in questo turno:
- <nome>(<argomenti JSON>) -> <risultato>      (oppure: "nessuno")
Indicazioni già date in questo turno: <testi delle indicazioni>   (solo se presenti)
Risposta proposta: <pulisci_ragionamento(testo dell'ultimo AIMessage) o "(nessuna risposta dal modello)">
```
Le chiamate si abbinano ai risultati con `tool_call_id`; si includono quelle di tutti i tentativi del turno.

Istruzioni (in italiano, da affinare nel Task 6): giudicare solo l'ultima risposta proposta; coerente solo se completa (tutte le parti **in ambito**), in tema (seguiti letti nel contesto), fedele ai risultati degli strumenti, senza valori che andavano presi da uno strumento (ora, conversione, calcolo, data, conteggio di giorni) ma non compaiono in nessun risultato, anche se giusti; un valore già dato in una risposta precedente e ripetuto tale e quale va bene; le parti fuori ambito si ignorano e non vanno mai chieste; saluti, ringraziamenti, «cosa sai fare?» e spiegazioni di errori degli strumenti si giudicano solo per completezza e tema; non pretendere note o avvertenze; prima il motivo (una frase breve che, se non coerente, dice all'agente che cosa manca o è sbagliato), poi `coerente`. Le istruzioni non nominano singoli strumenti.

- [ ] **Step 1: test che falliscono** in `tests/test_revisore.py`:
  - `test_istruzioni_contengono_l_ambito`.
  - `test_istruzioni_non_nominano_strumenti`: nessuno tra `get_current_time`, `convert_units`, `calculate`, `days_between`, `compute_deadline`.
  - `test_schema_motivo_prima_di_coerente`: `list(Giudizio.model_fields) == ["motivo", "coerente"]`.
  - `test_contesto_solo_domande_e_risposte` (Review Focus 3): cronologia `[System(agente), Human("che ore sono a Tokyo?"), AI("", tool_calls=[get_current_time c0]), Tool("…09:00…", c0), AI("Sono le 09:00."), Human("converti 2 km in miglia"), AI("", tool_calls=[convert_units c1]), Tool("2 km = 1,2427 mi", c1), AI("2 km sono 1,2427 miglia.")]`, `inizio_turno=5` → dopo il System del revisore: `Human("che ore sono a Tokyo?")`, `AI("Sono le 09:00.")`, poi un solo `HumanMessage` che contiene `"converti 2 km in miglia"`, `"convert_units"`, `"1,2427 mi"`, `"Risposta proposta: 2 km sono 1,2427 miglia."` e **non** contiene `"get_current_time"`.
  - `test_turno_con_indicazione`: turno con risposta parziale, `indicazione("manca il calcolo")`, chiamata `calculate`, risposta completa → il messaggio del turno elenca entrambe le chiamate, l'indicazione e come risposta proposta l'ultima.
  - `test_risposta_con_think_o_vuota` (Review Focus 4): `AI("<think>x</think>Sono le 9.")` → `"Risposta proposta: Sono le 9."`; `AI("")` → `"(nessuna risposta dal modello)"`.
  - `test_indicazione_su_una_riga` (Review Focus 5): `indicazione('manca\n"x"')` inizia con `"[Revisione]"` e non contiene `"\n"`.
  - `test_rivedi_restituisce_il_giudizio`; `test_rivedi_eccezione_fail_open(caplog)` → `None` + WARNING `revisore` con `"-> fine"`; `test_rivedi_output_non_valido` per `None`, `{"coerente": False}`, `"no"` → `None` + WARNING.
  - `test_crea_revisore_usa_config`: come `test_crea_router_usa_config` (`request_timeout == 60`, `max_retries == 0`, `extra_body`, nessuno strumento).
- [ ] **Step 2:** `pytest tests/test_revisore.py -q` → FAIL.
- [ ] **Step 3:** implementare come descritto sopra.
- [ ] **Step 4:** suite completa verde.

### Task 4: grafo con revisore e cronologia

**Files:** Modify `assistente/grafo.py` (docstring di testa con il disegno di §18.3, stato, nodi, archi), `assistente/sessione.py` (`_chiamate_da_conservare`), `tests/finti.py`, `tests/test_grafo.py`, `tests/test_sessione.py`

**Interfaces:**
- Consumes: `rivedi`, `indicazione`, `Giudizio` (Task 3); `RevisoreFinto`, `APPROVATA`, `RESPINTA`.
- Produces:
  - `StatoAssistente` + `inizio_turno: NotRequired[int]` (impostato dal nodo `router` a `len(messages) - 1`), `revisioni: NotRequired[int]` (rifiuti nel turno; il router lo azzera), `coerente: NotRequired[bool | None]`, `ultima_proposta: NotRequired[AIMessage | None]`.
  - `instrada(stato, max_passi) -> Literal["strumenti", "revisore", "ultima_risposta", "fine"]`: strumenti se li chiede e `passi_strumento < max_passi`; se li chiede al limite → `ultima_risposta` se `stato.get("ultima_proposta")` altrimenti `fine`; risposta finale → `revisore`.
  - `dopo_revisore(stato, max_revisioni) -> Literal["agente", "fine"]`: `agente` solo se `coerente is False` e `revisioni <= max_revisioni`.
  - `costruisci_grafo(modello, registro, max_passi, *, router, ambito, messaggio_rifiuto, revisore, max_revisioni)`; nodi `router`, `agente`, `strumenti`, `rifiuto`, `revisore`, `ultima_risposta`; `recursion_limit = (max_revisioni + 1) * (2 * max_passi + 2) + 6`.
  - Nodo `revisore`: `rivedi(...)`; `None` → `{"coerente": None}`; coerente → INFO `-> fine`; non coerente → `revisioni + 1`; se `<= max_revisioni`: INFO `-> agente (revisione n/max)` e restituisce `messages=[indicazione(motivo)]`, `passi_strumento=0`, `ultima_proposta=<ultimo AIMessage>`; altrimenti INFO `-> fine` + WARNING del limite.
  - Nodo `ultima_risposta`: WARNING (§ Global Constraints) e `messages=[ultima_proposta senza id]`.
  - `finti.grafo_in_ambito(modello, registro, max_passi=3, revisore=None, max_revisioni=2)`: `revisore` predefinito `RevisoreFinto([APPROVATA])`.
  - `sessione._chiamate_da_conservare`: conserva solo le chiamate il cui id ha un `ToolMessage` nei passaggi.

- [ ] **Step 1: test che falliscono** in `tests/test_grafo.py` (i `costruisci_grafo` diretti ricevono `revisore`/`max_revisioni`; `test_grafo_ha_nodi_espliciti` aggiornato):
  - `test_instrada` e `test_dopo_revisore` per ogni uscita (incluso `max_revisioni=0`).
  - `test_coerente_al_primo_passaggio(caplog)` (evidenza 2): un solo record `revisore` con `coerente=sì` e `-> fine`; risposta invariata; agente chiamato una volta.
  - `test_risposta_parziale_rimandata(caplog)` (evidenza 1): revisore `[RESPINTA, APPROVATA]`, modello `[AI("parte 1"), AI("parte 1 e parte 2")]` → finale `"parte 1 e parte 2"`; la seconda chiamata del modello vede `AI("parte 1")` seguito da un `HumanMessage` che inizia con `"[Revisione]"` e contiene `"manca la seconda parte"`; log `-> agente (revisione 1/2)` poi `coerente=sì`.
  - `test_limite_revisioni(caplog)` (evidenza 3): revisore `[RESPINTA]` sempre, modello `[AI("r1"), AI("r2"), AI("r3")]` → esattamente 3 record INFO `revisore`, finale `"r3"`, WARNING `limite di 2 revisioni`; con `max_revisioni=0` → 1 revisione, finale `"r1"`.
  - `test_valore_a_mente_rimandato`: revisore `[Giudizio(motivo="valore non preso da uno strumento", coerente=False), APPROVATA]`, modello `[AI("Mancano 41 giorni."), chiede_ora("Europe/Rome"), AI("Mancano 41 giorni.")]` → l'orologio viene eseguito dopo la revisione.
  - `test_strumenti_dopo_la_revisione_contatore_azzerato`: `max_passi=1`, modello: strumento, risposta, (revisione respinta), strumento, risposta → secondo strumento eseguito.
  - `test_limite_strumenti_dopo_revisione`: `max_passi=1`, dopo la revisione il modello chiede strumenti due volte → finale = prima risposta proposta, WARNING; `limite_raggiunto(stato)` falso.
  - `test_limite_strumenti_primo_tentativo`: come oggi, nessun record `revisore`, `limite_raggiunto(stato)` vero.
  - `test_revisore_in_errore_fail_open`: `RevisoreFinto([ConnectionError()])` → risposta passa, WARNING.
  - `test_rifiuto_non_passa_dal_revisore`: router `[FUORI]` → `revisore.chiamate == []`.
  - `test_revisore_riceve_l_ambito`.
  - `test_motivo_su_una_riga_nel_log` (Review Focus 5).
  - `test_limite_alto_non_supera_ricorsione`: `max_passi=20`, `max_revisioni=2`, revisore sempre `RESPINTA`, ogni tentativo usa 20 strumenti poi risponde → nessun `GraphRecursionError`.
- [ ] **Step 2: test che falliscono** in `tests/test_sessione.py`:
  - `test_revisione_fuori_dalla_cronologia` (Review Focus 2): turno con `[RESPINTA, APPROVATA]` → cronologia `[System, Human, AI(finale)]`; nessun messaggio con `"[Revisione]"` né la risposta rifiutata; al turno dopo il router finto riceve solo domande e risposte finali.
  - `test_chiamata_senza_risposta_non_conservata` (Review Focus 1): limite strumenti dopo revisione con `get_current_time` → nessun `AIMessage` in cronologia con tool_call priva del suo `ToolMessage`.
  - `test_chiamate_di_tutti_i_tentativi_conservate`: `get_current_time` nel primo tentativo e `days_between` nel secondo → entrambe in cronologia con le risposte.
- [ ] **Step 3:** `pytest tests/test_grafo.py tests/test_sessione.py -q` → FAIL.
- [ ] **Step 4:** implementare.
- [ ] **Step 5:** suite completa verde (reali saltati).

### Task 5: collegamento, test reali e documentazione

**Files:** Modify `assistente/terminale.py` (`main`), `tests/test_reale.py`, `tests/test_terminale.py` (se serve), `README.md`, `CLAUDE.md`

**Interfaces:** Consumes `crea_revisore(config)`, `config.max_revisioni`, `costruisci_grafo(..., revisore=, max_revisioni=)`, `rivedi`.

- [ ] **Step 1:** `main` passa `revisore=crea_revisore(config)`, `max_revisioni=config.max_revisioni`.
- [ ] **Step 2:** `tests/test_reale.py`: i grafi esistenti ricevono il revisore vero. Nuovi reali:
  - `test_revisore_respinge_risposta_parziale_reale`: chiamata diretta a `rivedi` con il turno «Converti 10 miglia in km e calcola 15 per 4», risultato di `convert_units`, risposta solo sulla conversione → `coerente is False`.
  - `test_revisore_respinge_valore_a_mente_reale`: «Quanti giorni mancano a Natale?» senza strumenti, risposta «Mancano 41 giorni.» → `False`.
  - `test_revisore_approva_risposta_completa_reale`: stessa domanda di Natale con `get_current_time` e `days_between` e risposta fedele → `True`.
  - `test_revisore_ignora_parte_fuori_ambito_reale`: «converti 5 miglia in km e dammi una ricetta», `convert_units`, risposta con la conversione e «non posso dare ricette» → `True`.
  - `test_parziale_poi_completa_reale(caplog)` (evidenza 1): grafo con revisore vero e un modello misto (prima chiamata: `convert_units`; seconda: risposta con il solo risultato della conversione preso dal `ToolMessage`; dalla terza: modello vero) → almeno un record `coerente=no`, l'ultimo `coerente=sì`, risposta finale con `"60"`.
  - `test_coerente_al_primo_passaggio_reale(caplog)` (evidenza 2): «Quanti km sono 5 miglia?» con agente vero → un solo record `revisore`, `coerente=sì`.
- [ ] **Step 3:** `README.md`: `MAX_REVISIONI`, grafo con il revisore, righe di log `revisore`, paragrafo «Misure del revisore» da riempire nel Task 6. `CLAUDE.md`: `revisore` nella struttura e una riga nell'obiettivo (§18). Docstring di `grafo.py` già aggiornata nel Task 4.
- [ ] **Step 4:** suite completa verde.

### Task 6: prove reali, misure, regressione e Docker (controllore, in sessione)

- [ ] **Step 1:** `MAX_REVISIONI=2` nel `.env` locale (dirlo all'utente).
- [ ] **Step 2:** reali → atteso `17 passed` (11 + 6); annotare eventuali rilanci.
- [ ] **Step 3: evidenze:** estratti di log reali per 1 e 2; per 3, app vera con agente vero e `RevisoreFinto` sempre `RESPINTA` (script nella scratchpad) → 3 righe `revisore`, WARNING, ultima risposta.
- [ ] **Step 4: misure**, app vera via stdin, `LOG_LEVEL=INFO`, al massimo 2 sessioni in parallelo, 3 sessioni per giro, almeno 20 domande: semplici per ogni strumento, in due parti, seguiti, saluti, «cosa sai fare?», una mista con parte fuori ambito, parole diverse dagli esempi del prompt. Contare: falsi rifiuti (grave), parziali o valori a mente approvati, limiti raggiunti, WARNING, tempo per turno.
- [ ] **Step 5:** se servono, ritocchi di `ISTRUZIONI_REVISORE` e nuova misura; massimo 3 giri, tenere il migliore (aggiornando i test del Task 3 se cambia il testo).
- [ ] **Step 6: contesto:** con `LOG_LEVEL=DEBUG` o dai log del server LM Studio, token della richiesta al revisore dopo 6–8 turni; se si avvicina a 8192, riportarlo all'utente.
- [ ] **Step 7: regressione:** prova del Task 0 → esiti non peggiori del riferimento.
- [ ] **Step 8: Docker:** `docker compose build`; `docker compose run --rm -T assistente` con una domanda in due parti → righe `revisore` nel log.
- [ ] **Step 9:** numeri nel README, stato di §18 → «implementata (data)», resoconto all'utente con le evidenze di §18.8 e cosa resta; commit solo su sua richiesta.
