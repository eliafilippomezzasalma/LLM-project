# Calcolatrice sicura MCP — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un secondo server MCP separato (`calcolatrice.py`) con un solo strumento `calculate`, che calcola espressioni aritmetiche senza `eval` e rifiuta esplicitamente gli input non validi, usato dall'assistente accanto a orologio e convertitore.

**Architecture:** `calcolatrice.py` contiene in sezioni distinte un analizzatore scritto a mano (lettura dei pezzi + discesa ricorsiva sulle regole di precedenza della matematica), il calcolo esatto con `fractions.Fraction` (float solo per potenze con esponente non intero), i messaggi d'errore italiani e uno strato MCP sottile sul `Server` di basso livello di `mcp`, come `convertitore.py`. L'assistente avvia il server via stdio con il ponte esistente `ClientMCP` (`assistente/mcp_remoto.py`), in una seconda istanza indipendente da quella del convertitore.

**Tech Stack:** Python 3.12, `mcp==2.3.0` (già presente), `fractions`, LangChain core, LangGraph, pytest. Nessuna dipendenza nuova.

**Spec:** `specs.md` §14 (approvata il 2026-11-03); per lo stile del server e del ponte vedere §13 e `convertitore.py`.

## Global Constraints

- Solo in `lezione_4/`, branch `feature/nuove-funzionalita`. **Nessun commit né push: lo decide l'utente.** Al posto del commit, ogni task finisce con la suite completa verde.
- Comandi da `lezione_4/` in PowerShell: test `.\venv\Scripts\python.exe -m pytest -q`.
- File del server: `lezione_4/calcolatrice.py`, avvio `python calcolatrice.py`, trasporto stdio, un solo strumento.
- Nome strumento `calculate`, unico argomento `expression` (stringa). Descrizione dello strumento in inglese.
- Nel sorgente di `calcolatrice.py` non compaiono `eval`, `exec`, `compile`, `literal_eval`, `import ast`.
- Ammessi: cifre, separatore decimale `,` o `.` (sempre decimale, mai migliaia: `1.000` = 1), `+ - * / ^`, sinonimi `**` → `^`, `×` → `*`, `÷` → `/`, parentesi tonde, spazi. Nient'altro (anche `−` U+2212 e `x` sono rifiutati).
- Precedenza: parentesi > `^` (associativa a destra, esponente con segno ammesso: `2^-1`) > segno davanti (`-2^2` = −4) > `* /` > `+ -` (a sinistra). Segni ripetuti ammessi (`--2` = 2).
- Limiti: espressione ≤ 200 caratteri; ≤ 30 livelli di parentesi annidate; ogni risultato, intermedio e finale, con 10^-100 ≤ |x| ≤ 10^100 oppure x = 0.
- Errori: testo che inizia con `Errore: `, risultato MCP con `is_error=True`, nessun crash del server né della chat.
- Grafo (`grafo.py`) ed esecuzione chiamate (`strumenti.py`) non cambiano.
- Le chiamate a `calculate` restano in cronologia (`STRUMENTI_IN_CRONOLOGIA`).

## Review Focus

1. Il modello manda simboli «quasi giusti» (`−` Unicode, `x` per per, `:`): rifiuto con il carattere e la posizione, non un crash né un'accettazione silenziosa.
2. Input al limite della ricorsione: 150 segni `-` di fila davanti a un numero, o 30 / 31 livelli di parentesi: risposta o errore italiano, mai `RecursionError`.
3. Risultato float da potenza non intera che poi torna intero: `2^0,5 * 2^0,5` → `2`, non `2.0000000000000004`.
4. Un intermedio fuori limite anche se il finale rientrerebbe: `10^60 * 10^60 / 10^30` → «troppo grande»; `10^-60 * 10^-60 * 10^100` → «troppo piccolo».
5. Spazi attorno all'espressione: `"  2+2 "` → `2+2 = 4` (espressione ripetuta senza spazi esterni).

Ognuno ha il suo test nel Task 1.

---

### Task 1: analizzatore, calcolo e messaggi (senza MCP)

**Files:**
- Create: `calcolatrice.py` (docstring di testa come `convertitore.py`; sezioni: 1. limiti e simboli, 2. lettura dei pezzi, 3. analisi e calcolo, 4. formato e messaggi; la sezione 5 «server MCP» arriva nel Task 2)
- Test: `tests/test_calcolatrice.py`

**Interfaces:**
- Produces:
  - `LUNGHEZZA_MASSIMA = 200`, `PROFONDITA_MASSIMA = 30`, `LIMITE_GRANDE = Fraction(10) ** 100`, `LIMITE_PICCOLO = Fraction(1, 10**100)`.
  - `class ErroreCalcolo(Exception)`: il messaggio (senza `Errore: `) è `str(errore)`.
  - `calcola(espressione: str) -> Fraction | float`: solleva `ErroreCalcolo` per ogni rifiuto.
  - `formatta_numero(valore: Fraction | float) -> str`: interi con |x| < 10^15 scritti per intero (`22`, `-4`, mai `-0`); tutti gli altri con `format(float(valore), ".10g")` (`0.3`, `0.3333333333`, `1.2676506e+30`, `2`).
  - `esegui_calcolo(argomenti: dict) -> tuple[str, bool]` → (testo, è_errore): unico punto usato dal Task 2. Successo: `f"{espressione.strip()} = {formatta_numero(r)}"`; errore: `f"Errore: {messaggio}"`.

**Algoritmo (non lo determinano i test):**
- Lettura: scorre il testo; sostituisce i sinonimi; un numero è la sequenza massima di cifre e separatori, poi validata (esattamente cifre, al più un separatore con cifre su entrambi i lati). Posizioni 1-based sull'espressione originale.
- Grammatica (discesa ricorsiva, un metodo per regola):
  `espressione := termine (("+"|"-") termine)*` · `termine := unario (("*"|"/") unario)*` · `unario := ("+"|"-") unario | potenza` · `potenza := primario ("^" unario)?` · `primario := numero | "(" espressione ")"`.
  La profondità delle parentesi si conta all'ingresso in `"("`. I segni ripetuti si gestiscono con un ciclo, non con ricorsione (Review Focus 2).
- Ogni operazione passa da un controllo `_nei_limiti(x)` (0, oppure 10^-100 ≤ |x| ≤ 10^100), altrimenti «troppo grande» / «troppo piccolo».
- Potenza `b ^ e`: `b = 0` e `e = 0` → indeterminata; `b = 0` e `e < 0` → divisione per zero; `b = 0` e `e > 0` → 0. Altrimenti stima **prima** del calcolo `e · log10|b|` (con `math.log10` su `abs(b)`, che sta nei limiti): > 100 → troppo grande, < −100 → troppo piccolo. Poi: `e` intero (`Fraction` con denominatore 1, o float intero) → `b ** int(e)` esatto se `b` è `Fraction`; `e` non intero e `b < 0` → base negativa; altrimenti `float(b) ** float(e)`.
- `Fraction` op `float` → float (normale aritmetica Python); il formato `.10g` assorbe l'errore di arrotondamento (Review Focus 3).

**Testi esatti** (i test li confrontano):
- `espressione vuota`
- `carattere non consentito '{c}' in posizione {n}: sono ammessi numeri, + - * / ^ e parentesi`
- `numero scritto male '{testo}' in posizione {n}`
- `manca un numero in posizione {n}` (operatore senza operando, parentesi vuote, espressione che finisce con un operatore: `n` = posizione del pezzo che sta dove servirebbe il numero, oppure lunghezza+1 se il testo è finito)
- `manca un operatore prima di '{pezzo}' in posizione {n}` (`2 3`, `2(3)`, `(1)(2)`)
- `parentesi aperta in posizione {n} non chiusa`
- `parentesi chiusa in posizione {n} senza apertura`
- `divisione per zero`
- `0^0 è una forma indeterminata`
- `potenza con base negativa ed esponente non intero non supportata`
- `risultato troppo grande (oltre 10^100)` · `risultato troppo piccolo (sotto 10^-100)`
- `espressione troppo lunga (massimo 200 caratteri)` · `troppe parentesi annidate (massimo 30 livelli)`
- argomento mancante, `None`, numero, bool, lista: `serve un'espressione scritta come testo, per esempio '(3,5 + 2) * 4'`

- [ ] **Step 1: test che falliscono** in `tests/test_calcolatrice.py` (usare `pytest.mark.parametrize` per le tabelle):
  - `test_operazioni_e_precedenza`: `calcola` → `"2 + 3 * 4"`=14, `"(2 + 3) * 4"`=20, `"10 - 4 - 3"`=3, `"8 / 4 / 2"`=1, `"2 + 3^2"`=11, `"2^3^2"`=512, `"-2^2"`=−4, `"(-2)^2"`=4, `"2^-1"`=`Fraction(1, 2)`, `"--2"`=2, `"-(2 + 1)"`=−3, `"+5"`=5.
  - `test_virgola_e_punto`: `"3,5 + 2"` e `"3.5 + 2"` → `Fraction(11, 2)`; `"1.000"` → 1.
  - `test_sinonimi`: `"2**3"`=8, `"6 × 7"`=42, `"9 ÷ 3"`=3.
  - `test_aritmetica_esatta`: `esegui_calcolo({"expression": "0,1 + 0,2"}) == ("0,1 + 0,2 = 0.3", False)`; `"1 / 3"` → `"1 / 3 = 0.3333333333"`.
  - `test_formato`: `"(3,5 + 2) * 4"` → `("(3,5 + 2) * 4 = 22", False)`; `"2^0,5"` → `"2^0,5 = 1.414213562"`; `"2^100"` → `"2^100 = 1.2676506e+30"`; `"-0"` → `"-0 = 0"`; Review Focus 3: `"2^0,5 * 2^0,5"` → `"2^0,5 * 2^0,5 = 2"`; Review Focus 5: `"  2+2 "` → `"2+2 = 4"`.
  - `test_rifiuti_matematici`: `esegui_calcolo` → `(f"Errore: {testo}", True)` per `"10 / 0"` e `"5 / (2 - 2)"` e `"0^-1"` (divisione per zero), `"0^0"`, `"(-8)^0,5"` e `"(-8)^(1/3)"` (base negativa), `"9^9^9"` e `"10^1000"` (troppo grande), `"10^-1000"` e `"0,5^1000"` e `"10^-(9^9)"` (troppo piccolo); Review Focus 4: `"10^60 * 10^60 / 10^30"` (grande), `"10^-60 * 10^-60 * 10^100"` (piccolo).
  - `test_potenze_enormi_rifiutate_subito`: `"9^9^9"` e `"10^-(9^9)"` rifiutati in meno di 1 s (`time.perf_counter`).
  - `test_rifiuti_di_forma`: `""` e `"   "` (vuota); `"2 + x"` → `carattere non consentito 'x' in posizione 5…`; `"3,5,2"` → `numero scritto male '3,5,2' in posizione 1`; `"1.000,5"`, `"3,"`, `",5 + 1"` (numero scritto male); `"3 + * 2"` → `manca un numero in posizione 5`; `"4 /"` → `manca un numero in posizione 4`; `"()"` → `manca un numero in posizione 2`; `"2 3"` → `manca un operatore prima di '3' in posizione 3`; `"2(3)"` → `manca un operatore prima di '(' in posizione 2`; `"(1 + 2"` → `parentesi aperta in posizione 1 non chiusa`; `"1 + 2)"` → `parentesi chiusa in posizione 6 senza apertura`.
  - `test_simboli_quasi_giusti` (Review Focus 1): `"5 − 2"` (U+2212) → `carattere non consentito '−' in posizione 3…`; `"3 x 4"`, `"8 : 2"`, `"10 % 3"`, `"sqrt(4)"`, `"2 = 2"` → carattere non consentito.
  - `test_limiti_di_lunghezza_e_profondita` (Review Focus 2): `"1+" * 99 + "1"` (199 caratteri) → 100; `"1+" * 100 + "1"` → troppo lunga; `"(" * 30 + "1" + ")" * 30` → 1; con 31 → troppe parentesi; `"-" * 150 + "2"` → 2 (nessun `RecursionError`).
  - `test_argomento_non_testuale`: `esegui_calcolo({})`, `{"expression": None}`, `{"expression": 5}`, `{"expression": True}`, `{"expression": ["1"]}` → `(…argomento…, True)`.
  - `test_nessun_eval_nel_sorgente`: il testo di `calcolatrice.py` non contiene `eval(`, `exec(`, `compile(`, `literal_eval`, `import ast`.
- [ ] **Step 2: vedere fallire**: `.\venv\Scripts\python.exe -m pytest tests/test_calcolatrice.py -q` → errore di import di `calcolatrice`.
- [ ] **Step 3: implementare** sezioni 1–4 di `calcolatrice.py` come da interfaccia e algoritmo.
- [ ] **Step 4: test verdi**, poi suite completa `.\venv\Scripts\python.exe -m pytest -q` → PASS.

### Task 2: server MCP stdio in `calcolatrice.py`

**Files:**
- Modify: `calcolatrice.py` (sezione 5 «server MCP», sullo stampo della sezione 5 di `convertitore.py`)
- Test: `tests/test_calcolatrice_mcp.py` (stesso schema di `tests/test_convertitore_mcp.py`: `_con_client`, `_chiama`)

**Interfaces:**
- Consumes: `esegui_calcolo` (Task 1).
- Produces:
  - `NOME_STRUMENTO = "calculate"`.
  - `DESCRIZIONE: str` in inglese: calcola un'espressione aritmetica passata come testo; operazioni ammesse `+ - * / ^` e parentesi, decimali con virgola o punto; nessuna funzione né variabile; ogni calcolo va mandato allo strumento, anche quelli che sembrano impossibili (es. divisione per zero), riportando il risultato o il messaggio d'errore.
  - `SCHEMA: dict` = `{"type": "object", "properties": {"expression": {"type": "string", "description": "Arithmetic expression, e.g. '(3,5 + 2) * 4' or '2^10'"}}, "required": ["expression"]}`.
  - `crea_server() -> Server` (nome `"calcolatrice"`; nome strumento diverso → `Errore: strumento 'X' non disponibile`, `is_error=True`).
  - `main() -> None` su `stdio_server()` con `anyio.run`; `if __name__ == "__main__": main()`.

- [ ] **Step 1: test che falliscono**:
  - `test_un_solo_strumento_con_schema`: un solo strumento `calculate`; `input_schema["properties"]["expression"]["type"] == "string"`; `"expression"` in `required`.
  - `test_chiamata_riuscita`: `{"expression": "(3,5 + 2) * 4"}` → `(False, "(3,5 + 2) * 4 = 22")`.
  - `test_divisione_per_zero`: `{"expression": "10 / 0"}` → `(True, "Errore: divisione per zero")`.
  - `test_argomento_mancante`: `{}` → `is_error True`, testo inizia con `Errore: serve un'espressione`.
  - `test_strumento_sconosciuto`: nome `pippo` → `is_error True`.
  - `test_server_vero_via_stdio`: `Client(StdioServerParameters(command=sys.executable, args=[<percorso assoluto di calcolatrice.py>]))`: `"6 × 7"` → `"6 × 7 = 42"` (il `×` attraversa intatto stdio) e `"10 / 0"` con `is_error True`.
- [ ] **Step 2: vedere fallire** (`crea_server` assente).
- [ ] **Step 3: implementare la sezione 5** (nessuna logica di calcolo qui).
- [ ] **Step 4: test verdi** + suite completa verde.

### Task 3: collegamento nell'assistente, prompt, Docker, documentazione

**Files:**
- Modify: `assistente/mcp_remoto.py` (aggiunte), `assistente/terminale.py`, `assistente/sessione.py`, `Dockerfile` (`COPY calcolatrice.py .`)
- Modify: `README.md`, `CLAUDE.md`, `specs.md` (§14 «Stato: implementata»)
- Test: `tests/test_mcp_remoto.py`, `tests/test_terminale.py`, `tests/test_sessione.py` (solo aggiunte; i test esistenti del convertitore restano invariati)

**Interfaces:**
- Consumes: `ClientMCP`, `ErroreMCP` esistenti; `calcolatrice.py` avviabile come script (Task 2).
- Produces:
  - in `mcp_remoto.py`: `FILE_CALCOLATRICE: Path` (cartella del progetto / `calcolatrice.py`), `parametri_calcolatrice() -> StdioServerParameters` (come `parametri_convertitore`).
  - in `terminale.py`: `_collega(nome: str, parametri: StdioServerParameters) -> ClientMCP | None` (log `WARNING` «{nome} MCP non disponibile: …»); `collega_convertitore(parametri=None)` diventa un involucro di `_collega("convertitore", …)` (firma e messaggio invariati); nuovo `collega_calcolatrice(parametri: StdioServerParameters | None = None) -> ClientMCP | None`; `intestazione(config: Config, convertitore: bool, calcolatrice: bool) -> str` con tre righe: quella esistente del modello, `Convertitore di unità (MCP): attivo|non disponibile`, `Calcolatrice (MCP): attivo|non disponibile`.
  - `main`: apre i due server in modo indipendente (`remoti = [r for r in (collega_convertitore(), collega_calcolatrice()) if r]`), strumenti `[crea_orologio(), *strumenti di ogni remoto]`, `finally` che chiude ogni remoto aperto.
  - in `sessione.py`: `STRUMENTI_IN_CRONOLOGIA = frozenset({"convert_units", "calculate"})`; `PROMPT_SISTEMA` esteso (testo iniziale sotto, da affinare nel Task 4).

**Testo iniziale da aggiungere a `PROMPT_SISTEMA`** (dopo la parte sul convertitore):
«Per ogni calcolo aritmetico, anche semplice, usa sempre lo strumento calculate e non fare i conti a mente. Chiamalo anche quando pensi che il calcolo sia impossibile (per esempio una divisione per zero): è lo strumento a verificarlo. Esempio: per «quanto fa 10 / 0?» chiama calculate con expression '10 / 0'. Per le conversioni di unità usa convert_units, non calculate. Se calculate restituisce un errore, riportalo senza proporre un risultato.»

- [ ] **Step 1: test che falliscono**:
  - `test_mcp_remoto.py::test_apre_e_espone_calculate`: `ClientMCP.apri(parametri_calcolatrice())`, un tool `calculate`; `tool.invoke({"expression": "2^10"}) == "2^10 = 1024"`; `tool.invoke({"expression": "10 / 0"}) == "Errore: divisione per zero"`; `chiudi()`.
  - `test_terminale.py::test_collega_calcolatrice_fallito` (parametri che escono subito → `None`, warning `calcolatrice MCP non disponibile` in `caplog`) e `test_collega_calcolatrice_riuscito`.
  - `test_terminale.py::test_intestazione_server_mcp`: `intestazione(config, True, False)` contiene `Convertitore di unità (MCP): attivo` e `Calcolatrice (MCP): non disponibile`; e viceversa.
  - `test_terminale.py::test_main_server_indipendenti_e_chiusi`: con `monkeypatch` su `carica_config`, `crea_modello`, `esegui_chat` (che registra l'intestazione e gli strumenti), `collega_convertitore` → `None`, `collega_calcolatrice` → un finto con `strumenti()` e `chiudi()` registrato: `main()` ritorna 0, l'intestazione dice convertitore `non disponibile` e calcolatrice `attivo`, il finto è stato chiuso.
  - `test_sessione.py::test_prompt_sistema_impone_la_calcolatrice`: `"calculate"` in `PROMPT_SISTEMA`, «a mente» presente, esempio `'10 / 0'` presente, rimando a `convert_units` per le conversioni.
  - `test_sessione.py::test_cronologia_conserva_le_chiamate_alla_calcolatrice`: sullo stampo di `test_cronologia_conserva_le_chiamate_al_convertitore`.
- [ ] **Step 2: vedere fallire.**
- [ ] **Step 3: implementare** come da interfaccia; `Dockerfile` copia `calcolatrice.py`; `README.md`: sezione «Calcolatrice sicura (MCP)» (cosa accetta, elenco dei rifiuti con un esempio ciascuno, esempio di riga di log `WARNING`, avvio isolato `.\venv\Scripts\python.exe calcolatrice.py`, riga di diagnosi «Calcolatrice (MCP): non disponibile»), punti della prova guidata «Quanto fa (3,5 + 2) * 4?» e «Quanto fa 10 / 0?»; `CLAUDE.md`: struttura (`calcolatrice.py`, specifica in `specs.md` §14) e obiettivo con la calcolatrice MCP; `specs.md` §14: «Stato: implementata».
- [ ] **Step 4: test automatici verdi**: `.\venv\Scripts\python.exe -m pytest -q`.

### Task 4: prove reali, misure, ritocchi al prompt, Docker

**Files:**
- Modify: `tests/test_reale.py`, eventualmente `assistente/sessione.py` (solo il prompt), `README.md` (misure e limiti)
- Script di misura usa-e-getta nella scratchpad (non nel repository)

- [ ] **Step 1: test reali** in `tests/test_reale.py`: sostituire `_chiedi_con_convertitore` con `_chiedi_con_strumenti_mcp(domanda) -> dict[str, list[str]]` + risposta finale (collega **entrambi** i server, così anche i test del convertitore girano con il prompt completo; `assert` che entrambi siano partiti; restituisce i contenuti dei `ToolMessage` per nome di strumento). Nuovi test:
  - `test_espressione_usa_la_calcolatrice`: «Quanto fa (3,5 + 2) * 4?» → almeno una chiamata `calculate` che finisce con `= 22`; `"22"` nella risposta.
  - `test_divisione_per_zero_usa_la_calcolatrice` (**severo**, deciso dall'utente): «Quanto fa 10 / 0?» → almeno una chiamata `calculate`, tutte con `Errore: divisione per zero`; la risposta non contiene un risultato inventato (`not re.search(r"=\s*-?\d", finale)` e nessun «infinito»).
- [ ] **Step 2: eseguire** `$env:RUN_REAL_TESTS="1"; .\venv\Scripts\python.exe -m pytest -m reale -v -s` → PASS di tutti i casi (vecchi e nuovi).
- [ ] **Step 3: misure** con uno script nella scratchpad che usa il grafo vero e conta le chiamate per strumento (da `ToolMessage`), con Qwen in LM Studio:
  - calcolatrice, sessione nuova per ogni domanda: 6 calcoli validi (`(3,5 + 2) * 4`, `2^10`, `0,1 + 0,2`, `15 * 23`, `100 / 8`, `2 + 2`) e 6 rifiutati (`10 / 0` ×2, `5 / (3 - 3)`, `0^0`, `2^1000`, `radice di 16` che deve arrivare allo strumento o essere rifiutata senza numeri) → conteggio «strumento usato» su 12;
  - sessione lunga di 20 domande miste (calcoli, conversioni, ore, domande senza strumenti) → quante chiamate attese avvenute, per strumento;
  - **regressione** (deciso dall'utente): i 12 casi d'errore del convertitore in sessione nuova come nelle prove del 2026-11-03, «converti 10 km in miglia» ×3 (deve usare `convert_units`, non `calculate`), «Che ore sono a Tokyo?» seguito da «e a Roma?» ×6 → confronto con i numeri del README (11/12; circa 1 su 6).
- [ ] **Step 4: ritocchi al prompt** se i tassi sono bassi o se la regressione peggiora: al massimo 3 giri (prompt → test automatici → misure di nuovo); poi ci si ferma (nessuna soglia minima bloccante, deciso dall'utente). Ogni giro annotato nel resoconto.
- [ ] **Step 5: Docker**: `docker compose build`, poi `docker compose run --rm assistente`: intestazione con convertitore e calcolatrice `attivo`; «Quanto fa (3,5 + 2) * 4?», «Quanto fa 10 / 0?», «converti 10 km in miglia» con le righe di log attese.
- [ ] **Step 6: README**: misure finali (data, modello, conteggi, limiti rimasti) nella sezione della calcolatrice e aggiornamento di quelle di orologio e convertitore se cambiate; suite completa verde.
- [ ] **Step 7: resoconto** all'utente: cosa è stato eseguito, con quale esito, cosa resta da provare. Nessun commit: si aspetta l'indicazione dell'utente.
