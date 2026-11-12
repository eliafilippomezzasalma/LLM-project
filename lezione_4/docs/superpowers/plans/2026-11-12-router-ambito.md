# Router d'ambito — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un nodo LLM `router` prima dell'agente classifica ogni domanda (`conversazione` | `fuori_ambito`, con motivo) in base all'ambito della configurazione; le domande fuori ambito ricevono la frase fissa di rifiuto senza che il nodo `agente` venga eseguito.

**Architecture:** nuovo modulo `assistente/router.py` (schema Pydantic, istruzioni, riduzione della cronologia, chiamata con fail-open, costruzione del client con output strutturato). `grafo.py` passa da due a quattro nodi: `router` → (`agente` ⇄ `strumenti`) | `rifiuto`; il nodo `modello` si rinomina `agente` ed è invariato nel comportamento. Categoria e motivo stanno nello stato, non nei messaggi; `Sessione` non cambia.

**Tech Stack:** Python 3.12, LangGraph Graph API, `langchain-openai` (`ChatOpenAI.with_structured_output`, `method="json_schema"`), Pydantic, pytest. Nessuna dipendenza nuova.

**Spec:** `specs.md` §17 (approvata il 2026-11-12); contesto §6.3, §6.4, §6.7.

## Global Constraints

- Solo in `lezione_4/`, branch `feature/nuove-funzionalita`. La §16 non committata di `specs.md` e `COPIONE.md` non si toccano.
- **Nessun commit né push: lo decide l'utente.** Al posto del commit, ogni task finisce con la suite completa verde.
- Comandi da `lezione_4/` in PowerShell: test `.\venv\Scripts\python.exe -m pytest -q`; reali `$env:RUN_REAL_TESTS="1"; .\venv\Scripts\python.exe -m pytest -m reale -v -s`.
- Categorie esatte: `"conversazione"`, `"fuori_ambito"`. Variabili: `AMBITO_ASSISTENTE`, `MESSAGGIO_RIFIUTO`, obbligatorie, **nessun valore di riserva nel codice**.
- Router: stesso `LM_BASE_URL`/`LM_MODEL`, nessuno strumento collegato, `extra_body=RAGIONAMENTO_DISATTIVATO`, timeout `TIMEOUT_ROUTER_SECONDI = 60`, output strutturato `method="json_schema"`. **Mai `function_calling`.**
- Il prompt del router non nomina strumenti né dà istruzioni su come rispondere.
- Fail-open: qualunque errore o output non valido del router → agente + `WARNING`.
- Log a INFO (logger tra parentesi): `router` → `categoria=<c> motivo="<m>" -> agente|rifiuto`; `agente` → `chiamata <n>` a ogni esecuzione del nodo; `rifiuto` → `risposta fissa`.
- Il motivo non entra mai nei messaggi dello stato né in cronologia.
- Agente, `instrada`, `strumenti.py`, `sessione.py` (prompt incluso) invariati nel comportamento.

## Review Focus

1. Seguito di una domanda rifiutata («e quella dell'amatriciana?» dopo un rifiuto): il router deve vedere la coppia domanda + frase di rifiuto precedente, altrimenti non può giudicare nel contesto → test nel Task 3.
2. Cronologia con chiamate agli strumenti (`AIMessage` con `tool_calls` e testo vuoto, `ToolMessage`) e prompt di sistema dell'agente: nessuno di questi arriva al router → test nel Task 3.
3. Router che restituisce qualcosa che non è una `Classificazione` (None, dict, testo) invece di sollevare: va trattato come non valido → agente + WARNING → test nel Task 3.
4. Dopo un rifiuto la sessione non deve aggiungere la nota non normativa né sollevare `LimitePassaggiRaggiunto`, anche se prima c'era stata una scadenza → test nel Task 4.
5. Un motivo con a capo o virgolette non deve spezzare la riga di log del router (una sola riga) → test nel Task 4.

---

### Task 0: verifica di partenza (controllore, in sessione)

Nessun codice di prodotto. Il controllore (Claude nella sessione principale) esegue e annota i numeri.

- [ ] **Step 1:** `git log -1 --oneline` → `f50307c`; `git status --short` → solo `M specs.md`, `?? COPIONE.md`, il piano.
- [ ] **Step 2:** suite → atteso `336 passed, 9 skipped`.
- [ ] **Step 3:** reali con LM Studio → atteso `9 passed`.
- [ ] **Step 4:** ricostruire nella scratchpad la prova guidata (15 domande: almeno una per orologio, convertitore, calcolatrice, ognuno dei sei strumenti delle scadenze, più i casi dei limiti noti: «e a Roma?», «che giorno è oggi?», «quanti giorni sono passati dal…»), eseguirla con `python -m assistente < file` e `LOG_LEVEL=INFO`, salvare stdout/stderr come **riferimento**: per ogni domanda strumenti chiamati e risposta.

### Task 1: verifica dell'output strutturato su LM Studio (controllore, usa-e-getta)

- [ ] **Step 1:** script nella scratchpad: `ChatOpenAI(base_url, model, api_key="lm-studio", timeout=60, extra_body={"reasoning_effort": "none"}).with_structured_output(Schema, method="json_schema")` con uno schema `categoria: Literal[...]`, `motivo: str`; 3 domande (una in ambito, una fuori, un saluto).
- [ ] **Step 2:** atteso: tre oggetti Pydantic validi. Se `json_schema` fallisce, **fermarsi e riportarlo all'utente** proponendo il ripiego di §17.4 (prompt + validazione Pydantic del testo); i task successivi si adeguano solo dopo il suo assenso.

### Task 2: configurazione

**Files:**
- Modify: `assistente/config.py`, `.env.example`
- Test: `tests/test_config.py`, `tests/test_modello.py` (solo la costante `CONFIG`)

**Interfaces:**
- Produces: `Config` con i campi nuovi `ambito_assistente: str`, `messaggio_rifiuto: str` (dopo `log_level`).

- [ ] **Step 1: test che falliscono** in `tests/test_config.py`: `BASE` riceve `"AMBITO_ASSISTENTE": "orari e calcoli"` e `"MESSAGGIO_RIFIUTO": "Non posso aiutarti."`; `test_valori_completi` confronta anche i due campi; nuovi `test_manca_ambito_assistente` e `test_manca_messaggio_rifiuto` (`pytest.raises(ErroreConfigurazione, match="AMBITO_ASSISTENTE")` / `"MESSAGGIO_RIFIUTO"`), `test_ambito_vuoto_conta_come_mancante` (`"  "`). Aggiornare `CONFIG` in `tests/test_modello.py` con i due campi.
- [ ] **Step 2:** `pytest tests/test_config.py -q` → FAIL.
- [ ] **Step 3:** in `carica_config` leggere le due variabili con `_obbligatoria`. In `.env.example`, con un commento ciascuna, una riga d'esempio (§17.2):
  `AMBITO_ASSISTENTE=Orari e fusi orari, conversioni di unità di misura, calcoli aritmetici, date, giorni lavorativi, festività e scadenze; anche saluti, ringraziamenti e domande su cosa sa fare l'assistente.`
  `MESSAGGIO_RIFIUTO=Mi dispiace, posso aiutarti solo con orari, conversioni, calcoli e scadenze.`
- [ ] **Step 4:** suite completa verde (nota: finché il Task 5 non tocca `main`, i test di `test_terminale` che usano `carica_config` con l'ambiente reale non devono rompersi; se qualcuno lo fa, aggiungere le due variabili nel suo ambiente finto).

### Task 3: modulo `router.py`

**Files:**
- Create: `assistente/router.py`, `tests/test_router.py`
- Modify: `tests/finti.py`

**Interfaces:**
- Consumes: `Config` (Task 2), `RAGIONAMENTO_DISATTIVATO`, `CHIAVE_SEGNAPOSTO` da `modello.py`.
- Produces:
  - `class Classificazione(BaseModel)`: `categoria: Literal["conversazione", "fuori_ambito"]`, `motivo: str` (non vuoto, `Field(min_length=1)`).
  - `CONVERSAZIONE = "conversazione"`, `FUORI_AMBITO = "fuori_ambito"`, `TIMEOUT_ROUTER_SECONDI = 60`.
  - `ISTRUZIONI_ROUTER: str` con il segnaposto `{ambito}`.
  - `messaggi_per_router(messaggi: list[AnyMessage], ambito: str) -> list[BaseMessage]`
  - `classifica(router: Runnable, messaggi: list[AnyMessage], ambito: str) -> Classificazione | None`
  - `crea_router(config: Config) -> Runnable`
  - in `tests/finti.py`: `RouterFinto(esiti: list)` con `.chiamate: list[list]`; `invoke(messaggi, config=None, **kw)` restituisce l'esito successivo (ripete l'ultimo), lo solleva se è un'eccezione. Costanti `IN_AMBITO = Classificazione(categoria="conversazione", motivo="domanda su orari")`, `FUORI = Classificazione(categoria="fuori_ambito", motivo="ricetta di cucina")`.

- [ ] **Step 1: test che falliscono** in `tests/test_router.py`:
  - `test_istruzioni_contengono_l_ambito`: il primo messaggio di `messaggi_per_router([HumanMessage("ciao")], "orari e calcoli")` è `SystemMessage` e contiene `"orari e calcoli"`.
  - `test_istruzioni_non_nominano_strumenti`: `ISTRUZIONI_ROUTER.lower()` non contiene `"strument"`, `"tool"`, `"get_current_time"`, `"convert_units"`, `"calculate"`.
  - `test_istruzioni_seguiti_nel_contesto`: le istruzioni parlano di seguiti e della categoria della domanda precedente (contiene `"precedente"`).
  - `test_solo_domande_e_risposte` (Review Focus 2): input `[SystemMessage(prompt agente), HumanMessage("converti 2 km"), AIMessage("", tool_calls=[…]), ToolMessage("2 km = …", tool_call_id=…), AIMessage("Sono 1,24 mi."), HumanMessage("e 3 km?")]` → dopo il `SystemMessage` del router restano esattamente `[HumanMessage("converti 2 km"), AIMessage("Sono 1,24 mi."), HumanMessage("e 3 km?")]`; nessun `ToolMessage`, nessun `tool_calls`, il prompt dell'agente assente.
  - `test_seguito_di_un_rifiuto_vede_il_rifiuto` (Review Focus 1): cronologia `[Human("ricetta della carbonara"), AI("<frase di rifiuto>"), Human("e quella dell'amatriciana?")]` → tutte e tre presenti, in ordine.
  - `test_classifica_restituisce_la_classificazione`: `classifica(RouterFinto([FUORI]), [...], "x") == FUORI`.
  - `test_classifica_eccezione_fail_open(caplog)`: `RouterFinto([ConnectionError("giù")])` → `None`, un record `WARNING` del logger `router` che contiene `"-> agente"`.
  - `test_classifica_output_non_valido` (Review Focus 3): per ciascuno di `None`, `{"categoria": "fuori_ambito"}`, `"fuori_ambito"` → `None` + WARNING.
  - `test_crea_router_usa_config`: sull'oggetto restituito (o sul `ChatOpenAI` interno, come fa `test_crea_modello_usa_config`) `base_url`, `model_name`, `request_timeout == 60`, `extra_body == RAGIONAMENTO_DISATTIVATO`; nessuno strumento collegato.
- [ ] **Step 2:** `pytest tests/test_router.py -q` → FAIL (modulo assente).
- [ ] **Step 3:** implementare. `messaggi_per_router` tiene `HumanMessage` e gli `AIMessage` senza `tool_calls` con testo non vuoto, in ordine, preceduti da `SystemMessage(ISTRUZIONI_ROUTER.format(ambito=ambito))`. `classifica` cattura `Exception`, accetta solo istanze di `Classificazione`, altrimenti `log.warning("router: risposta non valida (%s) -> agente", …)` e `None`; logga a DEBUG i messaggi inviati. `crea_router` = `ChatOpenAI(..., timeout=TIMEOUT_ROUTER_SECONDI, extra_body=RAGIONAMENTO_DISATTIVATO).with_structured_output(Classificazione, method="json_schema")`. Le istruzioni (in italiano): classificare **solo** se la domanda rientra nell'ambito; saluti, ringraziamenti e «cosa sai fare?» sono `conversazione`; un seguito prende la categoria della domanda precedente a cui si riferisce; una domanda mista con una parte in ambito è `conversazione`; motivo in una frase breve.
- [ ] **Step 4:** suite completa verde.

### Task 4: grafo con router, agente e rifiuto

**Files:**
- Modify: `assistente/grafo.py` (docstring di testa, stato, nodi, archi), `tests/test_grafo.py`, `tests/test_sessione.py`, `tests/finti.py`
- Test: `tests/test_grafo.py`, `tests/test_sessione.py`

**Interfaces:**
- Consumes: `classifica`, `Classificazione`, `FUORI_AMBITO` (Task 3); `RouterFinto`, `IN_AMBITO`, `FUORI` (Task 3).
- Produces:
  - `StatoAssistente` con `categoria: NotRequired[str | None]`, `motivo: NotRequired[str | None]`.
  - `dopo_router(stato: StatoAssistente) -> Literal["agente", "rifiuto"]` (`"rifiuto"` solo se `stato.get("categoria") == "fuori_ambito"`).
  - `costruisci_grafo(modello, registro, max_passi, *, router: Runnable, ambito: str, messaggio_rifiuto: str)`; nodi `router`, `agente`, `strumenti`, `rifiuto`; `recursion_limit = 2 * max_passi + 7`.
  - in `tests/finti.py`: `grafo_in_ambito(modello, registro, max_passi=3)` = `costruisci_grafo(..., router=RouterFinto([IN_AMBITO]), ambito="ambito di prova", messaggio_rifiuto=RIFIUTO)` con `RIFIUTO = "Non posso aiutarti."`, per i test esistenti.

- [ ] **Step 1: test che falliscono** in `tests/test_grafo.py` (i test esistenti passano a `grafo_in_ambito`; `test_grafo_ha_nodi_espliciti` → `{"router", "agente", "strumenti", "rifiuto"}`; i caplog di DEBUG passano dal logger `modello` al logger `agente`; `test_giro_completo` conta i soli INFO del logger `strumenti`):
  - `test_dopo_router`: `{"categoria": "fuori_ambito"}` → `"rifiuto"`; `"conversazione"` → `"agente"`; `None` / chiave assente → `"agente"`.
  - `test_in_ambito_passa_all_agente(caplog)` (evidenza 1): router `[IN_AMBITO]`, modello `[chiede_ora("Asia/Tokyo"), AIMessage("Sono le 20:30.")]` → risposta finale dell'agente; log INFO `router` con `categoria=conversazione`, `motivo="domanda su orari"`, `-> agente`; due righe INFO `agente` (`chiamata 1`, `chiamata 2`); `stato["categoria"] == "conversazione"`.
  - `test_fuori_ambito_rifiuta_senza_agente(caplog)` (evidenza 2): router `[FUORI]` → `stato["messages"][-1]` è `AIMessage(RIFIUTO)`; `modello.chiamate == []`; nessun record del logger `agente`; riga `router` con `-> rifiuto`; riga INFO `rifiuto`; nessun messaggio dello stato contiene `"ricetta di cucina"`.
  - `test_router_in_errore_passa_all_agente(caplog)`: router `[ConnectionError("giù")]` → agente eseguito, WARNING `router`.
  - `test_motivo_su_una_riga(caplog)` (Review Focus 5): motivo `'riga uno\nriga "due"'` → il messaggio del record `router` non contiene `"\n"`.
  - `test_router_riceve_l_ambito`: `RouterFinto.chiamate[0][0]` è il `SystemMessage` con l'ambito passato a `costruisci_grafo`.
  - `test_limite_alto_non_supera_ricorsione` resta con `max_passi=20`.
- [ ] **Step 2: test che falliscono** in `tests/test_sessione.py` (i `costruisci_grafo` esistenti passano a `grafo_in_ambito`):
  - `test_rifiuto_in_cronologia_senza_motivo`: sessione con router `[FUORI]` → `chiedi("ricetta della carbonara") == RIFIUTO`; cronologia `[System, Human("ricetta della carbonara"), AI(RIFIUTO)]`; `"ricetta di cucina"` assente.
  - `test_rifiuto_dopo_una_scadenza_senza_nota` (Review Focus 4): con `_sessione_con_nota` adattata a ricevere un router `RouterFinto([IN_AMBITO, FUORI])`, primo turno con scadenza e nota, secondo turno rifiutato → risposta esattamente `RIFIUTO`, nessuna eccezione.
- [ ] **Step 3:** `pytest tests/test_grafo.py tests/test_sessione.py -q` → FAIL.
- [ ] **Step 4:** implementare. Logger `agente` (sostituisce `modello`, stessi DEBUG); nodo `agente` = il vecchio `nodo_modello` più `log.info("chiamata %d", stato["passi_strumento"] + 1)`; nodo `router` chiama `classifica(router, stato["messages"], ambito)` e restituisce `{"categoria": …, "motivo": …}` (None/None se non valido), log INFO con il motivo reso su una riga (`" ".join(motivo.split())`); nodo `rifiuto` restituisce `{"messages": [AIMessage(messaggio_rifiuto)]}` e logga `risposta fissa`. Archi: `START → router`; `add_conditional_edges("router", dopo_router, {"agente": "agente", "rifiuto": "rifiuto"})`; `rifiuto → END`; il resto come prima con `agente` al posto di `modello`. Docstring di testa con il nuovo disegno (§17.3).
- [ ] **Step 5:** suite completa verde (i reali restano saltati).

### Task 5: collegamento in `main`, test reali e documentazione

**Files:**
- Modify: `assistente/terminale.py` (`main`), `tests/test_terminale.py` (se serve), `tests/test_reale.py`, `README.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: `crea_router(config)` (Task 3), `costruisci_grafo(..., router=, ambito=, messaggio_rifiuto=)` (Task 4).

- [ ] **Step 1:** `main` costruisce `crea_router(config)` e lo passa a `costruisci_grafo` con `config.ambito_assistente` e `config.messaggio_rifiuto`. Intestazione invariata.
- [ ] **Step 2:** `tests/test_reale.py`: ogni `costruisci_grafo` riceve `router=crea_router(config)` e i due testi dalla config. Nuovi reali:
  - `test_router_in_ambito_reale`: «Che ore sono a Tokyo?» → `classifica(...)` restituisce `categoria == "conversazione"`.
  - `test_router_fuori_ambito_reale`: «Dammi la ricetta della carbonara» → `categoria == "fuori_ambito"`, e il grafo completo risponde con `config.messaggio_rifiuto` senza chiamare l'agente (modello spia o conteggio dei record `agente`).
- [ ] **Step 3:** `README.md`: le due variabili nuove (anche per Docker: vanno nel `.env`), il grafo a quattro nodi, le righe di log `router`/`agente`/`rifiuto`, un paragrafo «Misure del router» da riempire nel Task 6. `CLAUDE.md`: `router` nella struttura di `assistente/` e una riga sull'obiettivo (router d'ambito, §17).
- [ ] **Step 4:** suite completa verde.

### Task 6: prove reali, misure, regressione e Docker (controllore, in sessione)

- [ ] **Step 1:** aggiungere le due variabili al `.env` locale (valori di `.env.example`) e dirlo all'utente.
- [ ] **Step 2:** reali → atteso `11 passed` (9 esistenti + 2 nuovi).
- [ ] **Step 3: misure del router**, app vera via stdin, `LOG_LEVEL=INFO`, 3 sessioni per giro. Insieme di almeno 24 domande: 8 in ambito (orari, conversioni, calcoli, scadenze, con parole diverse dagli esempi), 6 di conversazione (saluti, grazie, «cosa sai fare?», «e a Roma?» dopo un orario, «e in miglia?» dopo una conversione), 8 fuori ambito (ricette, politica, sport, codice, meteo…), 2 seguiti di un rifiuto («e quella dell'amatriciana?»). Contare per domanda le righe `router:` (categoria) e `agente:`. Errori: in ambito rifiutata (grave), fuori ambito passata, WARNING del router.
- [ ] **Step 4:** se ci sono errori, ritoccare `ISTRUZIONI_ROUTER` e rimisurare; massimo 3 giri, tenere il migliore (aggiornando i test del Task 3 se il testo cambia).
- [ ] **Step 5: regressione:** rieseguire la prova guidata del Task 0 → nessuna riga `-> rifiuto`, strumenti chiamati non peggiori del riferimento.
- [ ] **Step 6: Docker:** `docker compose build`; `docker compose run --rm -T assistente` con una domanda in ambito e una fuori → log con `-> agente` + `agente: chiamata`, e `-> rifiuto` senza `agente:`.
- [ ] **Step 7:** numeri nel README (Misure del router), stato di §17 → «implementata (data)»; resoconto all'utente con le evidenze di §17.8 (estratti di log reali) e cosa resta; commit solo su sua richiesta.
