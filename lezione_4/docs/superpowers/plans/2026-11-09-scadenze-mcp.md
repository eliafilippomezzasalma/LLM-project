# Giorni e scadenze MCP — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un terzo server MCP separato (`scadenze.py`) con sei strumenti su date, scadenze, giorni lavorativi e festività italiane 2020–2040 lette da `festivita.json`, usato dall'assistente accanto a orologio, convertitore e calcolatrice, con la nota non normativa gestita dalla sessione.

**Architecture:** `scadenze.py` ha sezioni distinte: intervallo e nomi, lettura e controllo del file delle festività, calendario (funzioni pure su `datetime.date`), richieste Pydantic + formato + messaggi italiani, strato MCP sottile sul `Server` di basso livello (come `convertitore.py` e `calcolatrice.py`). Il server è senza stato: ogni scadenza riuscita porta la riga della nota. Lato assistente un nuovo modulo `assistente/nota.py` toglie la riga quando la nota è già arrivata all'utente; lo stato vive nella `Sessione`.

**Tech Stack:** Python 3.12, `datetime` della libreria standard, `pydantic` e `mcp==2.3.0` (già presenti), LangChain core, LangGraph, pytest. Nessuna dipendenza nuova.

**Spec:** `specs.md` §15 (approvata il 2026-11-09); per lo stile di server, ponte e test vedere §13–14, `convertitore.py`, `calcolatrice.py`, `tests/test_calcolatrice_mcp.py`.

## Global Constraints

- Solo in `lezione_4/`, branch `feature/nuove-funzionalita`. **Nessun commit né push: lo decide l'utente** (un commit per tool, `COPIONE.md` sempre escluso). Al posto del commit, ogni task finisce con la suite completa verde.
- Comandi da `lezione_4/` in PowerShell: test `.\venv\Scripts\python.exe -m pytest -q`.
- Intervallo coperto: dal `2020-01-01` al `2040-12-31`. Ogni data ricevuta, calcolata (anche ogni passo intermedio dei conteggi lavorativi) o restituita, compresa la data spostata, sta nell'intervallo, altrimenti rifiuto.
- Non lavorativi: sabato, domenica, festività di `festivita.json`. Festività: le 12 della tabella in §15.4, il 4 ottobre solo dal 2026 (11 per anno 2020–2025, 12 per anno 2026–2040).
- Date solo ISO `AAAA-MM-GG` per intero (regex `^\d{4}-\d{2}-\d{2}$` dopo aver tolto gli spazi esterni), poi `date.fromisoformat`. Nei risultati ogni data è scritta `AAAA-MM-GG (giorno)` con il giorno della settimana in italiano minuscolo (`lunedì` … `domenica`).
- Errori: testo che inizia con `Errore: `, risultato MCP con `is_error=True`, nessun crash del server né della chat.
- Nota: costante `FRASE_NOTA = "calcolo indicativo, non ha valore legale."`; riga nel risultato `f"Nota: {FRASE_NOTA}"`, sempre l'**ultima** riga dei risultati riusciti di `compute_deadline`, mai negli altri strumenti né negli errori.
- Il server non calcola la Pasqua e non contiene date di festività nel codice: le legge solo da `festivita.json`.
- Grafo (`grafo.py`) ed esecuzione chiamate (`strumenti.py`) non cambiano.
- L'orologio non cambia: le sue risposte restano nella forma attuale.

## Review Focus

1. Il modello passa una data con l'ora o in formato italiano («2026-11-09T10:00:00», «09/11/2026», «9 novembre 2026»): rifiuto con il formato atteso, mai un crash né un'interpretazione silenziosa.
2. Il modello passa la quantità come testo o decimale (`"30"`, `30.0`, `true`): rifiuto esplicito sulla quantità.
3. Il modello usa unità o direzioni in italiano (`"mesi"`, `"indietro"`): rifiuto che elenca i valori ammessi, così può riprovare.
4. Una festività di sabato o domenica non va sottratta due volte nel conteggio dei giorni lavorativi: dal 2026-04-20 al 2026-04-30 (25 aprile di sabato) → 9.
5. Conteggi lunghi: `count_business_days` su tutto l'intervallo e `add_business_days` con 6000 giorni rispondono in meno di 1 s (risultato o rifiuto fuori intervallo).

Ognuno ha il suo test nel Task 3.

---

### Task 1: file delle festività e loro lettura

**Files:**
- Create: `festivita.json`, `scadenze.py` (docstring di testa come `calcolatrice.py`, con l'elenco delle cinque sezioni; qui solo le sezioni 1 «intervallo e nomi» e 2 «festività»)
- Test: `tests/test_scadenze_festivita.py`

**Interfaces:**
- Produces:
  - `PRIMA_DATA = date(2020, 1, 1)`, `ULTIMA_DATA = date(2040, 12, 31)`.
  - `GIORNI_SETTIMANA = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")` (indice = `date.weekday()`), `MESI = ("gennaio", …, "dicembre")`.
  - `FILE_FESTIVITA: Path` = cartella di `scadenze.py` / `festivita.json`.
  - `class ErroreFestivita(Exception)`: file mancante, JSON non valido o contenuto incoerente; il messaggio è in italiano.
  - `carica_festivita(percorso: Path = FILE_FESTIVITA) -> dict[date, str]`: data → nome.

**Forma di `festivita.json`** (decisa qui): oggetto con chiavi anno come stringa `"2020"` … `"2040"`; ogni valore è un elenco di oggetti `{"data": "AAAA-MM-GG", "nome": "…"}` in ordine di data. Nomi esatti: `Capodanno`, `Epifania`, `Lunedì dell'Angelo`, `Festa della Liberazione`, `Festa del Lavoro`, `Festa della Repubblica`, `Assunzione`, `San Francesco d'Assisi`, `Ognissanti`, `Immacolata Concezione`, `Natale`, `Santo Stefano`. Le date di Pasquetta si ricavano una volta (per esempio con uno script usa-e-getta nella scratchpad, non nel repository) e si scrivono nel file.

**Controlli di `carica_festivita`** (ognuno → `ErroreFestivita`): file mancante o JSON non valido; anni diversi da 2020–2040 (mancanti o in più); data non ISO o di un anno diverso dalla sua chiave; nome vuoto; date ripetute; numero di festività diverso da 11 (fino al 2025) o 12 (dal 2026).

- [ ] **Step 1: test che falliscono**:
  - `test_file_vero_si_carica`: `len(carica_festivita()) == 6 * 11 + 15 * 12` (= 246).
  - `test_pasquetta_come_algoritmo`: per ogni anno 2020–2040, l'unica voce `Lunedì dell'Angelo` è la Pasqua + 1 giorno, con la Pasqua calcolata da una funzione `_pasqua(anno)` scritta **solo nel test** (algoritmo gregoriano anonimo «Meeus/Jones/Butcher»). Controlli espliciti: 2024 → `2024-04-01`, 2026 → `2026-04-06`, 2038 → `2038-04-26`.
  - `test_san_francesco_dal_2026`: `date(2025, 10, 4)` assente, `date(2026, 10, 4)` e `date(2040, 10, 4)` presenti con nome `San Francesco d'Assisi`.
  - `test_date_fisse`: per 2020 e 2040 ci sono 01-01, 01-06, 04-25, 05-01, 06-02, 08-15, 11-01, 12-08, 12-25, 12-26 con i nomi esatti.
  - `test_file_rovinati` (parametrizzato, file scritti in `tmp_path`): mancante; non JSON; manca l'anno 2033; c'è il 2041; una data `2026-02-30`; una data del 2027 sotto la chiave 2026; nome vuoto; una festività in meno nel 2030 → `pytest.raises(ErroreFestivita)`.
- [ ] **Step 2: vedere fallire**: `.\venv\Scripts\python.exe -m pytest tests/test_scadenze_festivita.py -q` → errore di import di `scadenze`.
- [ ] **Step 3: scrivere `festivita.json` e implementare** le sezioni 1–2 come da interfaccia.
- [ ] **Step 4: test verdi**, poi suite completa → PASS.

### Task 2: calendario (funzioni pure)

**Files:**
- Modify: `scadenze.py` (sezione 3 «calendario»)
- Test: `tests/test_scadenze_calendario.py` (calendario costruito con `carica_festivita()` del file vero)

**Interfaces:**
- Consumes: costanti e `carica_festivita` (Task 1).
- Produces:
  - `class ErroreDate(Exception)`: il messaggio (senza `Errore: `) è `str(errore)`.
  - `MESSAGGIO_INTERVALLO = "posso calcolare solo date tra il 2020-01-01 e il 2040-12-31"`.
  - `controlla_intervallo(d: date) -> date`: restituisce `d` o solleva `ErroreDate(f"data {d.isoformat()} fuori dall'intervallo coperto: {MESSAGGIO_INTERVALLO}")`.
  - `aggiungi_mesi(d: date, mesi: int) -> date`: `mesi` con segno; se il giorno non esiste nel mese di arrivo prende l'ultimo del mese (`calendar.monthrange`). Non controlla l'intervallo.
  - `class Calendario`, costruttore `Calendario(festivita: dict[date, str])`, metodi:
    - `festivita(d: date) -> str | None`
    - `lavorativo(d: date) -> bool`
    - `motivo(d: date) -> str | None`: `None` se lavorativo; se festivo `f"è festiva ({nome})"` (soggetto sottinteso: la data) (la festività ha la precedenza sul giorno della settimana); altrimenti `"cade di sabato"` / `"cade di domenica"`.
    - `sposta(d: date, avanti: bool) -> date`: primo giorno lavorativo da `d` compreso, in avanti o all'indietro; ogni passo controllato con `controlla_intervallo`.
    - `aggiungi(d: date, quantita: int, unita: str, avanti: bool) -> date`: `unita` ∈ `{"days", "weeks", "months", "years", "business_days"}`; giorni e settimane di calendario (settimana = 7 giorni), mesi e anni con `aggiungi_mesi` (anni = 12 mesi), `business_days` con `aggiungi_lavorativi`. Il risultato passa da `controlla_intervallo`. **Nessuno spostamento qui.**
    - `aggiungi_lavorativi(d: date, n: int, avanti: bool) -> date`: partenza esclusa, si avanza (o si arretra) di `n` giorni lavorativi; ogni passo controllato.
    - `conta_lavorativi(inizio: date, fine: date) -> int`: estremi compresi; il chiamante garantisce `inizio <= fine`.
    - `festivita_di(anno: int, mese: int | None) -> list[tuple[date, str]]`: in ordine di data.
  - Per stare sotto 1 s sull'intervallo intero (Review Focus 5) basta un ciclo giorno per giorno (≈ 7700 giorni); niente ottimizzazioni.

- [ ] **Step 1: test che falliscono**:
  - `test_fine_mese_e_bisestili` (parametrizzato su `aggiungi_mesi`): `2025-01-31 +1` → `2025-02-28`; `2024-01-31 +1` → `2024-02-29`; `2024-02-29 +12` → `2025-02-28`; `2024-02-29 +48` → `2028-02-29`; `2026-03-31 -1` → `2026-02-28`; `2026-12-31 -6` → `2026-06-30`.
  - `test_lavorativo_e_motivo`: `2026-11-09` lavorativo, motivo `None`; `2026-11-14` → `"cade di sabato"`; `2026-11-15` → `"cade di domenica"`; `2026-04-25` (sabato) → `"è festiva (Festa della Liberazione)"`; `2026-04-06` → `"è festiva (Lunedì dell'Angelo)"`.
  - `test_sposta`: `sposta(2028-03-12, True)` → `2028-03-13`; `sposta(2026-12-25, True)` → `2026-12-28` (Natale, Santo Stefano, domenica); `sposta(2026-12-27, False)` → `2026-12-24`; `sposta(2026-11-09, True)` → `2026-11-09`.
  - `test_aggiungi`: `(2024-03-15, 4, "years", True)` → `2028-03-15`; `(2026-10-10, 30, "days", True)` → `2026-11-09`; `(2026-12-31, 6, "months", False)` → `2026-06-30`; `(2026-11-09, 2, "weeks", True)` → `2026-11-23`; `(2026-11-09, 10, "business_days", True)` → `2026-11-23`; `(2040-12-31, 1, "days", True)` → `ErroreDate` con `MESSAGGIO_INTERVALLO` nel testo.
  - `test_aggiungi_lavorativi`: `(2026-11-06, 1, True)` → `2026-11-09`; `(2026-11-09, 10, True)` → `2026-11-23`; `(2026-11-23, 10, False)` → `2026-11-09`; `(2026-12-23, 2, True)` → `2026-12-28`.
  - `test_conta_lavorativi`: `2026-11-02..2026-11-06` → 5; `2026-11-01..2026-11-30` → 21; `2026-11-14..2026-11-15` → 0; `2026-11-09..2026-11-09` → 1.
  - `test_spostamento_fuori_intervallo`: `sposta(2020-01-01, False)` → `ErroreDate` (il 2020-01-01 è festivo, il precedente è il 2019-12-31).
  - `test_festivita_di`: `(2026, 12)` → tre voci 12-08, 12-25, 12-26 con i nomi; `(2026, 7)` → `[]`; `(2026, None)` → 12 voci.
- [ ] **Step 2: vedere fallire** (`Calendario` assente).
- [ ] **Step 3: implementare la sezione 3.**
- [ ] **Step 4: test verdi** + suite completa verde.

### Task 3: richieste, risultati e rifiuti (senza MCP)

**Files:**
- Modify: `scadenze.py` (sezione 4 «richieste, formato e messaggi»)
- Test: `tests/test_scadenze.py`

**Interfaces:**
- Consumes: `Calendario`, `ErroreDate`, `controlla_intervallo`, costanti (Task 1–2).
- Produces:
  - `FRASE_NOTA = "calcolo indicativo, non ha valore legale."`, `RIGA_NOTA = f"Nota: {FRASE_NOTA}"`.
  - `leggi_data(valore: object) -> date`: toglie gli spazi esterni; testo non ISO (o non testo) → `ErroreDate(f"data '{valore}' non valida: usa il formato AAAA-MM-GG, es. 2024-03-15")`; ISO ma inesistente → `ErroreDate(f"la data '{valore}' non esiste")`; poi `controlla_intervallo`.
  - `formatta_data(d: date) -> str` → `"2028-03-15 (mercoledì)"`.
  - Modelli Pydantic (schemi JSON esposti al modello nel Task 4; le date sono `str` e passano da `leggi_data`):
    - `RichiestaScadenza(start_date: str, amount: StrictInt, unit: Literal["days", "business_days", "weeks", "months", "years"], direction: Literal["forward", "backward"] = "forward")`
    - `RichiestaLavorativi(start_date: str, days: StrictInt, direction: Literal["forward", "backward"] = "forward")`
    - `RichiestaConteggio(start_date: str, end_date: str)`
    - `RichiestaDifferenza(from_date: str, to_date: str)`
    - `RichiestaInfo(date: str)`
    - `RichiestaFestivita(year: StrictInt, month: StrictInt | None = None)`
    Ogni campo con una `description` in inglese (per esempio `"Date in ISO format YYYY-MM-DD, e.g. 2024-03-15"`).
  - `NOMI_STRUMENTI = ("compute_deadline", "add_business_days", "count_business_days", "days_between", "date_info", "list_holidays")`.
  - `esegui_strumento(calendario: Calendario, nome: str, argomenti: dict) -> tuple[str, bool]` → (testo, è_errore): unico punto usato dal Task 4; nome non in `NOMI_STRUMENTI` → `(f"Errore: strumento '{nome}' non disponibile", True)`.

**Testi esatti dei risultati** (i test li confrontano; `{d}` = `formatta_data`, singolare per 1: `1 giorno`, `1 giorno lavorativo`, `1 settimana`, `1 mese`, `1 anno`; plurali `giorni`, `giorni lavorativi`, `settimane`, `mesi`, `anni`; `dopo il` per forward, `prima del` per backward):
- `compute_deadline` senza spostamento: `f"Scadenza: {d_finale}, {quantità} {unità} {dopo il|prima del} {start_iso}."`
- con spostamento, una seconda frase: `f" La data calcolata {d_calcolata} {motivo}: spostata al giorno lavorativo {successivo|precedente}."`
- poi `"\n" + RIGA_NOTA`.
- `add_business_days`: `f"{n} {giorno lavorativo|giorni lavorativi} {dopo il|prima del} {start_iso}: {d}."`
- `count_business_days`: `f"Dal {inizio_iso} al {fine_iso}: {n} {giorno lavorativo|giorni lavorativi}."`
- `days_between`: `f"Il {to_iso} viene {n} {giorno|giorni} dopo il {from_iso}."` / `f"Il {to_iso} viene {n} {giorno|giorni} prima del {from_iso}."` / `f"Le due date coincidono: {d}."`
- `date_info`: `f"{d}: giorno lavorativo."` / `f"{d}: festivo, {nome}."` / `f"{d}: non lavorativo, {sabato|domenica}."`
- `list_holidays` con mese: `f"Festività di {mese} {anno}:"` + una riga per festività `f"\n- {d} {nome}"`; senza mese `f"Festività del {anno}:"` + righe; mese senza festività: `f"Nessuna festività nazionale a {mese} {anno}."`

**Testi esatti dei rifiuti** (dopo `Errore: `; più errori Pydantic uniti con `"; "` come nel convertitore):
- argomento mancante: `argomento '{campo}' mancante`
- `amount` / `days` non interi o < 1: `la quantità deve essere un numero intero da 1 in su`
- `unit` fuori elenco: `unità non valida: usa days, business_days, weeks, months o years`
- `direction` fuori elenco: `direzione non valida: usa forward o backward`
- date: i messaggi di `leggi_data` e `controlla_intervallo`
- `count_business_days` con fine prima dell'inizio: `la data finale {fine_iso} viene prima di quella iniziale {inizio_iso}`
- `year` non intero o fuori 2020–2040: `anno non valido: posso calcolare solo date tra il 2020-01-01 e il 2040-12-31`
- `month` non intero o fuori 1–12: `mese non valido: usa un numero da 1 a 12`

- [ ] **Step 1: test che falliscono** (helper `_esegui(nome, **argomenti)` con il calendario del file vero; tabelle con `pytest.mark.parametrize`):
  - `test_domande_gruppo_a`: `("2024-03-15", 4, "years")` → `"Scadenza: 2028-03-15 (mercoledì), 4 anni dopo il 2024-03-15.\nNota: calcolo indicativo, non ha valore legale."`; `("2026-10-10", 30, "days")` → `"Scadenza: 2026-11-09 (lunedì), 30 giorni dopo il 2026-10-10.\nNota: …"`; `("2026-12-31", 6, "months", "backward")` → `"Scadenza: 2026-06-30 (martedì), 6 mesi prima del 2026-12-31.\nNota: …"`; `("2026-11-09", 10, "business_days")` → `"Scadenza: 2026-11-23 (lunedì), 10 giorni lavorativi dopo il 2026-11-09.\nNota: …"`.
  - `test_scadenza_spostata`: `("2026-03-25", 1, "months")` → `"Scadenza: 2026-04-27 (lunedì), 1 mese dopo il 2026-03-25. La data calcolata 2026-04-25 (sabato) è festiva (Festa della Liberazione): spostata al giorno lavorativo successivo.\nNota: …"`; `("2027-06-27", 6, "months", "backward")` → `"Scadenza: 2026-12-24 (giovedì), 6 mesi prima del 2027-06-27. La data calcolata 2026-12-27 (domenica) cade di domenica: spostata al giorno lavorativo precedente.\nNota: …"`.
  - `test_nota_solo_in_compute_deadline`: nessun risultato degli altri cinque strumenti e nessun errore contiene `"Nota:"`; ogni risultato riuscito di `compute_deadline` finisce con `RIGA_NOTA`.
  - `test_gruppo_b`: `add_business_days("2026-11-09", 10)` → `"10 giorni lavorativi dopo il 2026-11-09: 2026-11-23 (lunedì)."`; `(…, days=1, start "2026-11-06")` → `"1 giorno lavorativo dopo il 2026-11-06: 2026-11-09 (lunedì)."`; `count_business_days("2026-11-01", "2026-11-30")` → `"Dal 2026-11-01 al 2026-11-30: 21 giorni lavorativi."`.
  - `test_gruppo_c`: `days_between("2026-11-09", "2026-12-25")` → `"Il 2026-12-25 viene 46 giorni dopo il 2026-11-09."`; `("2026-11-09", "2026-01-01")` → `"Il 2026-01-01 viene 312 giorni prima del 2026-11-09."`; `("2026-11-09", "2026-11-10")` → `"Il 2026-11-10 viene 1 giorno dopo il 2026-11-09."`; `("2026-11-09", "2026-11-09")` → `"Le due date coincidono: 2026-11-09 (lunedì)."`.
  - `test_gruppo_d`: `date_info("2027-06-02")` → `"2027-06-02 (mercoledì): festivo, Festa della Repubblica."`; `("2028-03-15")` → `"2028-03-15 (mercoledì): giorno lavorativo."`; `("2026-11-14")` → `"2026-11-14 (sabato): non lavorativo, sabato."`; `list_holidays(2026, 12)` → `"Festività di dicembre 2026:\n- 2026-12-08 (martedì) Immacolata Concezione\n- 2026-12-25 (venerdì) Natale\n- 2026-12-26 (sabato) Santo Stefano"`; `list_holidays(2026, 7)` → `"Nessuna festività nazionale a luglio 2026."`; `list_holidays(2026)` inizia con `"Festività del 2026:"` e ha 12 righe `- `.
  - `test_formati_rifiutati` (Review Focus 1): `"15/03/2024"`, `"2024-3-15"`, `"15 marzo 2024"`, `"2026-11-09T10:00:00"`, `"20240315"`, `20240315` (numero) come `date` di `date_info` → `Errore: data '…' non valida: usa il formato AAAA-MM-GG, es. 2024-03-15`; `" 2026-11-09 "` accettato.
  - `test_date_impossibili`: `"2026-02-30"`, `"2025-02-29"`, `"2026-13-01"` → `Errore: la data '…' non esiste`.
  - `test_fuori_intervallo`: `date_info("2019-12-31")`, `date_info("2045-01-01")`, `compute_deadline("2040-12-31", 1, "days")`, `compute_deadline("2020-01-02", 1, "days", "backward")` (cade sul 2020-01-01 festivo, lo spostamento va al 2019) → testo che contiene `MESSAGGIO_INTERVALLO`, `is_error True`.
  - `test_quantita_non_valide` (Review Focus 2): `amount` = `0`, `-3`, `1.5`, `30.0`, `"30"`, `True` e `days` = `0` → `Errore: la quantità deve essere un numero intero da 1 in su`.
  - `test_unita_e_direzione_non_valide` (Review Focus 3): `unit="mesi"` → `Errore: unità non valida: usa days, business_days, weeks, months o years`; `direction="indietro"` → `Errore: direzione non valida: usa forward o backward`.
  - `test_argomenti_mancanti`: `compute_deadline` senza `start_date` → `Errore: argomento 'start_date' mancante`; `days_between({})` → entrambi i campi nominati, uniti da `"; "`.
  - `test_intervallo_rovesciato`: `count_business_days("2026-11-30", "2026-11-01")` → `Errore: la data finale 2026-11-01 viene prima di quella iniziale 2026-11-30`.
  - `test_anno_e_mese_non_validi`: `list_holidays(2041)`, `list_holidays(2019)` → messaggio dell'anno; `list_holidays(2026, 13)`, `(2026, 0)` → messaggio del mese.
  - `test_festivita_nel_weekend_contata_una_volta` (Review Focus 4): `count_business_days("2026-04-20", "2026-04-30")` → `"Dal 2026-04-20 al 2026-04-30: 9 giorni lavorativi."`.
  - `test_conteggi_lunghi_veloci` (Review Focus 5): `count_business_days("2020-01-01", "2040-12-31")` riuscito e `add_business_days("2020-01-02", 6000)` rifiutato con `MESSAGGIO_INTERVALLO`, ciascuno in meno di 1 s (`time.perf_counter`).
  - `test_strumento_sconosciuto`: `esegui_strumento(cal, "pippo", {})` → `("Errore: strumento 'pippo' non disponibile", True)`.
- [ ] **Step 2: vedere fallire.**
- [ ] **Step 3: implementare la sezione 4** (traduzione degli errori Pydantic in italiano sullo stampo di `_messaggio` in `convertitore.py`).
- [ ] **Step 4: test verdi** + suite completa verde.

### Task 4: server MCP stdio in `scadenze.py`

**Files:**
- Modify: `scadenze.py` (sezione 5 «server MCP», sullo stampo della sezione 5 di `calcolatrice.py`)
- Test: `tests/test_scadenze_mcp.py` (stesso schema di `tests/test_calcolatrice_mcp.py`: `_con_client`, `_chiama`)

**Interfaces:**
- Consumes: `esegui_strumento`, `NOMI_STRUMENTI`, modelli Pydantic, `carica_festivita`, `ErroreFestivita`, `FILE_FESTIVITA` (Task 1–3).
- Produces:
  - `DESCRIZIONI: dict[str, str]`, in inglese, una per strumento:
    - `compute_deadline`: deadline or term from a start date plus a duration (days, business days, weeks, months, years), forward or backward (backward for notice periods); moves a deadline that falls on a weekend or Italian national holiday to the next (forward) or previous (backward) business day and says why. Use it for every deadline or term, also in business days.
    - `add_business_days`: which date comes N business days after or before a date, when the question is **not** about a deadline.
    - `count_business_days`: how many business days between two dates, both included.
    - `days_between`: how many calendar days between a reference date (usually today, from get_current_time) and another date.
    - `date_info`: weekday of a date and whether it is a business day or an Italian national holiday.
    - `list_holidays`: Italian national holidays of a year, or of one month.
    Ogni descrizione ricorda: dates only in ISO format YYYY-MM-DD, covered years 2020–2040.
  - `crea_server(festivita: dict[date, str] | None = None) -> Server` (nome `"scadenze"`; `None` → `carica_festivita()`): elenca i sei strumenti con `input_schema=<Modello>.model_json_schema()` e instrada ogni chiamata a `esegui_strumento`.
  - `main() -> None`: carica le festività; su `ErroreFestivita` scrive `scadenze: {errore}` su stderr e termina con `sys.exit(1)` (così `ClientMCP.apri` fallisce e l'intestazione dice «non disponibile»); altrimenti `stdio_server()` con `anyio.run`. `if __name__ == "__main__": main()`.

- [ ] **Step 1: test che falliscono**:
  - `test_sei_strumenti_con_schema`: i nomi elencati sono esattamente `NOMI_STRUMENTI`; lo schema di `compute_deadline` ha `unit` con `enum` dei cinque valori e `required` con `start_date`, `amount`, `unit`; ogni descrizione contiene `YYYY-MM-DD`.
  - `test_chiamata_riuscita`: `compute_deadline {"start_date": "2024-03-15", "amount": 4, "unit": "years"}` → `is_error False`, testo che inizia con `Scadenza: 2028-03-15 (mercoledì)` e finisce con `RIGA_NOTA`.
  - `test_errore_marcato`: `date_info {"date": "15/03/2024"}` → `is_error True`, testo che inizia con `Errore: data`.
  - `test_strumento_sconosciuto`: `pippo` → `(True, "Errore: strumento 'pippo' non disponibile")`.
  - `test_file_festivita_rovinato_server_non_parte`: `monkeypatch` di `scadenze.FILE_FESTIVITA` su un file inesistente in `tmp_path` e `scadenze.carica_festivita` che usa quel default (o passaggio esplicito del percorso: scelta dell'implementatore, purché `main()` legga `FILE_FESTIVITA` al momento della chiamata) → `pytest.raises(SystemExit)` con codice 1 e messaggio `scadenze:` in `capsys.readouterr().err`.
  - `test_server_vero_via_stdio`: `Client(StdioServerParameters(command=sys.executable, args=[<percorso assoluto di scadenze.py>]))`: `list_holidays {"year": 2026, "month": 12}` → testo con `Santo Stefano` e `lunedì`/`martedì` accentati intatti; `date_info {"date": "2045-01-01"}` con `is_error True`.
- [ ] **Step 2: vedere fallire.**
- [ ] **Step 3: implementare la sezione 5** (nessuna logica di date qui).
- [ ] **Step 4: test verdi** + suite completa verde.

### Task 5: nota non normativa nella sessione

**Files:**
- Create: `assistente/nota.py`
- Modify: `assistente/sessione.py` (solo il costruttore e `chiedi`)
- Test: `tests/test_nota.py`, aggiunte in `tests/test_sessione.py`

**Interfaces:**
- Consumes: `Sessione`, `ModelloFinto` (`tests/finti.py`), `costruisci_grafo`, `crea_registro`.
- Produces:
  - in `assistente/nota.py`:
    - `FRASE_NOTA = "calcolo indicativo, non ha valore legale."` (stessa di `scadenze.py`; un test confronta le due costanti) e `STRUMENTO_CON_NOTA = "compute_deadline"`.
    - `class NotaNonNormativa` con attributo `consegnata: bool = False` e metodi:
      - `filtra(testo: str) -> str`: se `consegnata`, toglie le righe che iniziano con `"Nota:"` (e il `"\n"` che le precede); altrimenti restituisce `testo` invariato.
      - `registra_risposta(testo: str) -> None`: se `"non ha valore legale"` è in `testo.lower()`, `consegnata = True`; mai di nuovo `False`.
    - `con_nota(strumenti: list[BaseTool], nota: NotaNonNormativa) -> list[BaseTool]`: stessa lista, con lo strumento di nome `STRUMENTO_CON_NOTA` (se c'è) sostituito da uno `StructuredTool` con lo stesso nome, descrizione e `args_schema`, che chiama l'originale (`originale.invoke(argomenti)`) e passa il testo da `nota.filtra`. Gli altri strumenti restano gli stessi oggetti.
  - in `sessione.py`: `Sessione(grafo, nota: NotaNonNormativa | None = None)`; in `chiedi`, **solo dopo** un turno riuscito (dopo il controllo del limite e il calcolo di `testo`), `if self.nota: self.nota.registra_risposta(testo)`.

- [ ] **Step 1: test che falliscono**:
  - `test_nota.py::test_filtra`: con `consegnata False`, `"Scadenza: X.\nNota: calcolo indicativo, non ha valore legale."` invariato; con `True` → `"Scadenza: X."`; testo senza nota invariato in entrambi i casi.
  - `test_nota.py::test_registra_risposta`: `"…Nota: calcolo indicativo, non ha valore legale."` → `consegnata True`; risposta senza la frase → resta `False`; una volta `True` resta `True`.
  - `test_nota.py::test_con_nota_tocca_solo_compute_deadline`: con uno strumento finto `compute_deadline` (`StructuredTool.from_function`, restituisce un testo con la riga della nota) e uno `date_info`: dopo `con_nota`, `date_info` è lo stesso oggetto; `compute_deadline` mantiene nome e descrizione e, con `consegnata True`, `invoke` restituisce il testo senza la riga.
  - `test_nota.py::test_frase_uguale_al_server`: `nota.FRASE_NOTA == scadenze.FRASE_NOTA`.
  - `test_sessione.py::test_nota_tolta_dopo_che_e_arrivata`: grafo con `ModelloFinto` e lo strumento finto avvolto con `con_nota`; turno 1: il modello chiama `compute_deadline` e poi risponde con un testo che contiene la frase → `nota.consegnata True` e il `ToolMessage` del turno 1 contiene `"Nota:"`; turno 2: stessa chiamata → il `ToolMessage` del turno 2 non contiene `"Nota:"`.
  - `test_sessione.py::test_nota_ripresentata_se_non_riportata`: turno 1 con risposta **senza** la frase → `consegnata False`; turno 2 → il `ToolMessage` contiene ancora `"Nota:"`.
  - `test_sessione.py::test_nota_ripresentata_se_il_turno_fallisce`: turno 1 che finisce con `LimitePassaggiRaggiunto` (il modello finto continua a chiedere lo strumento oltre `max_tool_steps`) → `consegnata False`.
- [ ] **Step 2: vedere fallire.**
- [ ] **Step 3: implementare** `assistente/nota.py` e le due righe in `sessione.py`.
- [ ] **Step 4: test verdi** + suite completa verde.

### Task 6: collegamento nell'assistente, prompt, Docker, documentazione

**Files:**
- Modify: `assistente/mcp_remoto.py`, `assistente/terminale.py`, `assistente/sessione.py` (prompt e cronologia), `Dockerfile` (`COPY scadenze.py .` e `COPY festivita.json .`)
- Modify: `README.md`, `CLAUDE.md`, `specs.md` (§15 «Stato: implementata»)
- Test: `tests/test_mcp_remoto.py`, `tests/test_terminale.py` (aggiornare i test esistenti di `intestazione` e `main` alla nuova firma), `tests/test_sessione.py`

**Interfaces:**
- Consumes: `ClientMCP`, `_collega`, `NotaNonNormativa`, `con_nota` (Task 5); `scadenze.py` avviabile come script (Task 4).
- Produces:
  - in `mcp_remoto.py`: `FILE_SCADENZE: Path`, `parametri_scadenze() -> StdioServerParameters` (come `parametri_calcolatrice`).
  - in `terminale.py`: `collega_scadenze(parametri: StdioServerParameters | None = None) -> ClientMCP | None` (via `_collega("scadenze", …)`); `intestazione(config: Config, convertitore: bool, calcolatrice: bool, scadenze: bool) -> str` con una quarta riga `Giorni e scadenze (MCP): attivo|non disponibile`; `main` apre i tre server in modo indipendente, crea `nota = NotaNonNormativa()`, `strumenti = con_nota([crea_orologio(), *strumenti remoti], nota)`, `Sessione(grafo, nota)`, e chiude ogni remoto nel `finally`.
  - in `sessione.py`: `STRUMENTI_IN_CRONOLOGIA` comprende anche i sei `NOMI_STRUMENTI` (scritti per esteso, senza importare `scadenze`); `PROMPT_SISTEMA` esteso con il testo iniziale sotto, da affinare nel Task 7.

**Testo iniziale da aggiungere a `PROMPT_SISTEMA`** (in fondo):
«Per ogni domanda su date, scadenze, giorni lavorativi, festività o giorni della settimana usa sempre gli strumenti delle scadenze e non fare i conti a mente, anche quando la risposta sembra ovvia. Questi strumenti accettano solo date nel formato AAAA-MM-GG: converti tu le date dell'utente (per esempio «15/03/2024» o «15 marzo 2024» diventano '2024-03-15'). Quando la domanda parte da oggi, chiedi prima la data a get_current_time con il fuso 'Europe/Rome' e poi passala allo strumento. Per scadenze e termini (affitti, fatture, preavvisi, anche in giorni lavorativi) usa compute_deadline; per un preavviso usa direction 'backward'. Usa add_business_days solo per sapere che giorno sarà fra N giorni lavorativi quando non si parla di una scadenza. days_between dice se una data viene prima o dopo l'altra: se una delle due è oggi, rispondi con «mancano» o «sono passati». Nelle risposte che usano questi strumenti scrivi le date nel formato AAAA-MM-GG. Se la scadenza è stata spostata, riporta la data calcolata, il motivo e la data finale. Se il risultato contiene una riga «Nota:», riportala così com'è nella risposta. Se uno di questi strumenti restituisce un errore, spiega il motivo e fermati, senza calcolare la data da solo.»

- [ ] **Step 1: test che falliscono**:
  - `test_mcp_remoto.py::test_apre_e_espone_le_scadenze`: `ClientMCP.apri(parametri_scadenze())` espone i sei nomi; `date_info` con `{"date": "2027-06-02"}` → `"2027-06-02 (mercoledì): festivo, Festa della Repubblica."`; `chiudi()`.
  - `test_terminale.py::test_collega_scadenze_fallito` (parametri che escono subito → `None`, warning `scadenze MCP non disponibile`) e `test_collega_scadenze_riuscito`.
  - `test_terminale.py::test_intestazione_server_mcp` aggiornato: `intestazione(config, True, False, True)` contiene `Convertitore di unità (MCP): attivo`, `Calcolatrice (MCP): non disponibile`, `Giorni e scadenze (MCP): attivo`.
  - `test_terminale.py::test_main_server_indipendenti_e_chiusi` aggiornato: convertitore `None`, calcolatrice e scadenze finti; intestazione coerente; entrambi i finti chiusi.
  - `test_terminale.py::test_main_avvolge_compute_deadline`: un finto server scadenze che espone uno strumento `compute_deadline`; lo strumento passato a `crea_modello` con quel nome non è l'oggetto originale (è stato avvolto da `con_nota`) e la `Sessione` passata a `esegui_chat` ha `nota` non `None`.
  - `test_sessione.py::test_prompt_sistema_scadenze`: `PROMPT_SISTEMA` contiene `compute_deadline`, `add_business_days`, `AAAA-MM-GG`, `get_current_time`, `backward`, `Nota:`.
  - `test_sessione.py::test_cronologia_conserva_le_chiamate_alle_scadenze`: sullo stampo di `test_cronologia_conserva_le_chiamate_alla_calcolatrice`, con `compute_deadline`.
- [ ] **Step 2: vedere fallire.**
- [ ] **Step 3: implementare** come da interfaccia; `Dockerfile`; `README.md`: sezione «Giorni e scadenze (MCP)» (domande supportate con un esempio per gruppo, regole di spostamento, festività e intervallo, formato ISO, nota alla prima scadenza, elenco dei rifiuti con un esempio ciascuno, avvio isolato `.\venv\Scripts\python.exe scadenze.py`, diagnosi «Giorni e scadenze (MCP): non disponibile» con la causa più probabile «festivita.json mancante o rovinato»), punti della prova guidata; `CLAUDE.md`: struttura (`scadenze.py`, `festivita.json`, `assistente/nota.py`, specifica in §15) e obiettivo; `specs.md` §15: «Stato: implementata».
- [ ] **Step 4: test automatici verdi**: `.\venv\Scripts\python.exe -m pytest -q`.

### Task 7: prove reali, misure, ritocchi al prompt, Docker (controllore in sessione)

**Files:**
- Modify: `tests/test_reale.py`, eventualmente `assistente/sessione.py` (solo il prompt) e le descrizioni degli strumenti in `scadenze.py`, `README.md` (misure e limiti)
- Script di misura usa-e-getta nella scratchpad (non nel repository)

- [ ] **Step 1: test reali** in `tests/test_reale.py`: l'helper esistente che collega i server MCP collega anche le scadenze (con `assert` che sia partito) e usa `con_nota` + `NotaNonNormativa` come `main`. Nuovi test:
  - `test_scadenza_spostata_con_nota`: «Ho un termine che parte dal 25/03/2026 e dura un mese: quando scade?» → almeno una chiamata `compute_deadline`; la risposta contiene `2026-04-27`, `2026-04-25` e `valore legale`.
  - `test_domanda_da_oggi_usa_orologio_e_scadenze`: «Quanti giorni mancano al 25/12/2040?» → chiamati sia `get_current_time` sia `days_between`; la risposta contiene il numero restituito dallo strumento.
  - `test_formato_italiano_convertito`: «Il 2 giugno 2027 è festivo?» → `date_info` chiamato con `"2027-06-02"`; la risposta contiene `Festa della Repubblica`.
  - `test_anno_fuori_intervallo_senza_data_inventata`: «Che giorno della settimana è il 2045-03-15?» → strumento chiamato, tutte le risposte con `Errore:`; la risposta non contiene nomi di giorni della settimana.
- [ ] **Step 2: eseguire** `$env:RUN_REAL_TESTS="1"; .\venv\Scripts\python.exe -m pytest -m reale -v -s` → PASS di tutti i casi (vecchi e nuovi).
- [ ] **Step 3: misure** con uno script nella scratchpad che usa il grafo vero (con `con_nota`) e conta le chiamate per strumento dai `ToolMessage`, con Qwen in LM Studio:
  - **sessione nuova per ogni domanda**: le 11 domande del §15.2 con date assolute, più 3 date scritte in formati diversi e 2 rifiuti (2045, 2026-02-30) → «strumento giusto usato» su 16, e quante volte è stato scelto `add_business_days` al posto di `compute_deadline` per le scadenze;
  - **catena orologio → scadenze**: «quanti giorni mancano al 25/12?» e «che giorno sarà fra 10 giorni lavorativi?» ×3 ciascuna → entrambi gli strumenti chiamati su 6;
  - **nota**: sessione con tre scadenze di fila → la nota compare nella prima risposta e non nelle altre (e `consegnata` diventa vera al primo turno);
  - **sessione lunga mista** di 20 domande (scadenze, calcoli, conversioni, ore, domande senza strumenti);
  - **regressione**: le misure del README per calcolatrice (14 casi del ritocco «radice di 16»), convertitore (12 errori, 10 km → miglia) e orologio («Che ore sono a Tokyo?» poi «e a Roma?» ×6, «che giorno è oggi?» ×3 che deve rispondere nella forma attuale, **non** in ISO) → confronto prima/dopo.
- [ ] **Step 4: ritocchi** al prompt e alle descrizioni se i tassi sono bassi o la regressione peggiora: al massimo 3 giri (prompt → test automatici → misure di nuovo); poi ci si ferma (nessuna soglia bloccante). Se la confusione tra `compute_deadline` e `add_business_days` resta alta, proporlo all'utente prima di raggruppare gli strumenti.
- [ ] **Step 5: Docker**: `docker compose build`, poi `docker compose run --rm assistente`: intestazione con i tre server `attivo`; una scadenza spostata, «Il 2 giugno 2027 è festivo?», «che giorno è oggi?».
- [ ] **Step 6: README**: misure finali (data, modello, conteggi, limiti rimasti) nella sezione delle scadenze e aggiornamento di quelle degli altri strumenti se cambiate; suite completa verde.
- [ ] **Step 7: resoconto** all'utente: cosa è stato eseguito, con quale esito, cosa resta da provare. Nessun commit: si aspetta l'indicazione dell'utente.
