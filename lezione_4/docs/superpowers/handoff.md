# Passaggio di consegne — Lezione 4, assistente con grafo a tre nodi LLM

Aggiornato: 2026-11-17 ~21:00 · Branch: `feature/nuove-funzionalita` · Ultimo commit (pushato): `2eea005`
«aggiunta del secondo nodo» · Locale = remoto.

> La versione precedente di questo file (stato al 2026-10-26, assistente con solo orologio) è nel
> commit `c27c538`.

Serve a riprendere il lavoro in una nuova sessione senza perdere nulla. Leggere in quest'ordine:
questo file → `lezione_4/CLAUDE.md` → `lezione_4/specs.md` (§17, §18, §19) →
`docs/superpowers/plans/2026-11-16-riassunto-cronologia.md`.

## 1. Dove siamo

L'assistente evolve, un passo alla volta, in un grafo LangGraph con nodi LLM. Ogni passo riparte
dal precedente funzionante e verificato, con le evidenze richieste dall'utente.

| Passo | Stato |
|---|---|
| Strumenti: orologio interno, convertitore (§13), calcolatrice (§14), scadenze (§15), tutti MCP tranne l'orologio | completati e pushati |
| §16 tavola periodica | **solo bozza**, modifica locale di `specs.md` mai committata: non toccarla, escluderla da ogni commit |
| Passo 1, router d'ambito (§17) | completato, `3f47059` + fix `96d46a2` |
| Passo 2, revisore della risposta (§18, con domande miste V2c e controllo A) | completato, `2eea005` |
| **Passo 3, riassunto della cronologia (§19)** | **completo e verificato il 2026-11-17 (Task 0–6, ritocchi A giri 1–2, valori realistici, misure in modalità token, README); NON committato** |

Grafo attuale: `START → riassunto → router → agente ⇄ strumenti → revisore → END | agente`, con
`router → rifiuto → END` per le domande fuori ambito.

## 2. Passo 3: riassunto della cronologia (§19)

**Compito (dall'utente):** un nodo LLM sostituisce i messaggi più vecchi con un riassunto e mantiene
intatti gli ultimi turni, così la conversazione resta utilizzabile su molti turni senza perdere le
informazioni importanti.

**Decisioni dell'utente:**
- **Strada A:** `Sessione` conserva cronologia **e** riassunto, li passa al grafo a ogni turno e li
  sostituisce solo se il turno riesce. Niente checkpointer: la strada B è stata valutata e scartata.
- Nel riassunto vanno nome, preferenze e argomenti delle domande; i risultati degli strumenti restano fuori.
- Soglia bassa per le prove: `RIASSUNTO_SOGLIA_TIPO=messaggi`, `RIASSUNTO_SOGLIA=10`,
  `RIASSUNTO_TURNI_DA_TENERE=2`.
- **Ambito allargato:** `AMBITO_ASSISTENTE` include le domande su ciò che l'utente ha detto nella
  conversazione (nome, preferenze). Altrimenti il router rifiuterebbe «come mi chiamo?».
- **Promemoria per la fine:** ricordare all'utente i valori realistici (circa 5000 token stimati,
  ultimi 3 turni), da implementare se avanza tempo.

**Scelte mie scritte in §19 (l'utente le ha approvate con la specifica):**
- conteggio senza i messaggi di sistema;
- taglio sempre su un `HumanMessage`, con controllo delle coppie chiamata/risultato;
- riassunto in coda all'unico messaggio di sistema di agente, router e revisore;
- fail-open;
- nessuna chiamata al modello se non c'è niente da togliere;
- regressione «prima» sull'albero `2eea005`, prima di toccare il codice.

**Piano:** `docs/superpowers/plans/2026-11-16-riassunto-cronologia.md`, Task 0–6:
- Task 0: verifica di partenza e regressione «prima», le fa il controllore;
- Task 1: configurazione e ambito;
- Task 2: `assistente/riassunto.py`;
- Task 3: nodo nel grafo e riassunto ai tre nodi;
- Task 4: `Sessione` e `terminale`;
- Task 5: controllo reale, test reali e documentazione;
- Task 6: misure, regressione, Docker e resoconto, li fa il controllore.

**Esecuzione scelta:** `superpowers:subagent-driven-development`, con implementatore e revisore per
ogni task e una revisione finale sul modello più capace. Prove reali, misure, regressione e Docker
le fa il controllore in sessione, con numeri di prima mano. Il registro SDD va in
`repo-lab-llm/.superpowers/sdd/2026-11-16-riassunto-cronologia/`, ignorato da Git. Contiene il
registro `progress.md`, i brief e i report dei task, i pacchetti di revisione, `snap.sh` per le
istantanee dell'albero (non si committa per task, i diff sono tra hash di tree) e `reviewer-rubric.md`.

**Avanzamento (2026-11-16):**

| Task | Esito | Istantanee (tree) |
|---|---|---|
| 0. Verifica e regressione «prima» | suite 436/21; regressione salvata in `regressione.txt` (15 domande) e `regressione_prima.txt` | base `3904db1` |
| 1. Configurazione e ambito | `SogliaRiassunto` + `Config.riassunto` in `config.py`, 3 variabili `RIASSUNTO_*`; ambito allargato in `.env.example` e nel `.env` locale; suite 445/21; revisione pulita | `3904db1..f846105` |
| 2. Modulo `assistente/riassunto.py` | conteggio, stima token, taglio, controllo coppie, `testo_con_riassunto`, `messaggi_con_riassunto`, presentazione dei tolti senza `ToolMessage`, `riassumi` fail-open, `crea_riassuntore`; `RiassuntoreFinto` e `SOGLIA_ALTA` in `tests/finti.py`; suite 461/21; revisione pulita | `f846105..85df1f6` |
| 3. Nodo nel grafo, riassunto ai tre nodi | rifatto da capo il 2026-11-17 (i 6 file del tentativo interrotto riportati a `85df1f6`); `terminale.py` collegato già qui; suite 473/21; revisione pulita | `85df1f6..9123714` |
| 4. `Sessione` e collegamento | `Sessione.riassunto`, taglio della cronologia con `stato["inizio_turno"]`; suite 482/21; revisione pulita | `9123714..2f69466` |
| 5. Controllo reale, reali nuovi, documentazione | passo 1 ok (nessun errore del template); **3 giri** sulle istruzioni del riassunto (richiesta dell'utente): attuali 2/3 casi con risultati, v1 1/6, v2 1/6, **v3 0/5 → tenuta** («Usa solo i numeri scritti dall'utente»; file `istruzioni_riassunto_v1..v3.py` nel registro); 3 reali nuovi; README, CLAUDE.md, specs §6.2; revisione pulita | `2f69466..6ec01ba` + v3 |
| Revisione finale (opus) | nessun Critical; corretti: disegno nella docstring di `grafo.py`, frase README sulle variabili, «conservati 1 turno», test sul controllo coppie fallito; ricontrollo 4/4. Poi trovato dal controllore nell'app vera: **prefisso doppio nel log** (`INFO riassunto: riassunto: …`), corretto + test sul formato reale; suite **484/28** | `27811ad..81b01e9..` |
| 6. Misure, regressione «dopo», Docker, resoconto | **fatto** il 2026-11-17 entro le 12:00 (vedi sotto); manca solo il commit, su ordine dell'utente | — |

**Esiti del 2026-11-17 (prove reali, una o due sessioni LM Studio):**
- Reali nuovi: router sulle domande sulla conversazione **5/5**; nome dopo la compressione **PASSED con v3**
  (con v1 falliva); seguito dopo la compressione **FALLISCE**: il riassunto contiene «ha convertito 5 miglia
  in km», ma «e in piedi?» viene agganciato all'ultimo turno conservato (N=1). Il test è stato corretto una
  volta (turno intermedio «12 per 7» ambiguo → «ore a Tokyo»), poi lasciato com'è: **decisione dell'utente**
  (limite noto nel README, oppure ritocco del prompt dell'agente, oppure segnare il test).
- Misura 1 (`misura_1.txt`, 16 turni, log `misura_1_out.txt`): compressione in 12/16 turni, 0 guasti del
  riassunto, fuori ambito + seguito rifiutati anche dopo la compressione, risultati numerici giusti.
  **Problema:** «Come mi chiamo?» (turno 10) → «non ho informazioni sul tuo nome»; «Converti 30 km nella mia
  unità preferita» (turno 11) → chiede l'unità (limite 3 revisioni); al turno 15 invece cita «Elia».
  Nome e preferenza del 1° turno **non usati in modo affidabile** dopo più compressioni. Proposte da
  discutere: regola nel riassunto «inizia sempre con nome e preferenze dell'utente», prefisso più esplicito
  per l'agente, log DEBUG dei riassunti per vedere dove si perdono.
- Misura 2 (15 turni): 9/9 risultati giusti, seguiti e fuori ambito ok; nome (t10) e preferenza «risposte brevi»
  (t14 → «Ho 178 giorni.») non usati. Regressione «dopo»: router 15/15, risposte giuste 14/14 (prima 13/14),
  rimandi 3 (prima 5), 2 timeout del riassunto fail-open. Docker: ok, «Ti chiami Elia» dopo 3 compressioni.
- Reali completi: **25/28**. Falliti: revisore su domanda mista (passo 2, pignolo, non legato al riassunto);
  nome dopo la compressione (intermittente, 1/3: il riassunto CONTIENE «Elia», è l'agente a non usarlo);
  seguito dopo la compressione (limite noto).
- **Diagnosi per la prossima sessione:** il riassuntore conserva il nome; il punto debole è l'agente. Proposte:
  una riga in `PROMPT_SISTEMA` («per domande su nome, preferenze o richieste precedenti usa il riassunto della
  conversazione precedente»), oppure prefisso del riassunto più esplicito; misurare con misura_1/misura_2.
- README «Misure del riassunto» e limiti noti scritti; §19 → «implementata (2026-11-17)». Task 6 FATTO.

**Stima di ciò che resta (2026-11-16):** circa 3,5–4,5 ore, quasi tutte di prove con LM Studio (un turno
con il revisore dura 1–2 min, una conversazione da 15 turni circa 30 min).

- **Regressione «prima» (30 minuti, non 15):** router 15/15, strumenti giusti ovunque, 5 turni rimandati
  dal revisore, nessun limite. Le risposte finali sono giuste 13/14. **Bug preesistente del revisore (§18):** su «Che giorno sarà fra
  10 giorni lavorativi?» lo strumento dà 2026-11-30, il revisore inventa «venerdì 27 novembre», l'agente
  si adegua e la risposta finale è sbagliata («giovedì 27 novembre»). Non toccato: punto aperto del passo 2.
- Rulings del controllore: `RiassuntoreFinto` è una sottoclasse di `RouterFinto`; `testo_con_riassunto`
  mantiene il nome del piano (nei test va importata con alias o tramite il modulo, altrimenti pytest la
  raccoglie come test).
- Dettagli minori rimandati alla revisione finale: sono nel registro (`Task N: minor (deferred)`).

## 3. Rimasto aperto dal passo 2 (fuori dal passo 3 salvo decisione dell'utente)

- **Secondo controllo sulle false «domande miste» nei seguiti.** Una parte fuori ambito vale solo
  se tutte le sue parole compaiono nella domanda dell'utente. Senza questo controllo il router a
  volte (circa 2 prove reali su 7) ripete «consigliami un film» sul seguito «e in piedi?». Il test
  reale `test_router_non_ripete_le_parti_escluse_del_turno_prima_reale[...e in piedi?]` quindi
  a volte fallisce. L'utente ha detto: «lasciamo stare per il momento».
- README: le righe g7 e g8 in «Misure del revisore» e il paragrafo «Limite noto» sulle domande miste.
- Test reali completi e regressione del revisore dopo `2eea005`.
- Falso rifiuto del revisore con un valore inventato, che rende sbagliata la risposta finale (trovato nella
  regressione «prima» del 2026-11-16, vedi §2).

## 4. Regole di lavoro (dall'utente)

- Si lavora solo in `lezione_4/`, sul branch `feature/nuove-funzionalita`. Su `master` c'è solo l'orologio: non toccarlo.
- **Commit e push solo su ordine esplicito.** Quando l'utente detta il messaggio, va usato esattamente, senza
  `Co-Authored-By`.
- Nei commit `specs.md` va **senza la §16**. Si costruisce il file senza quelle righe, si controlla con
  `diff` contro `git show HEAD:lezione_4/specs.md`, poi `git hash-object -w --path lezione_4/specs.md <file>`
  e `git update-index --cacheinfo 100644,<hash>,lezione_4/specs.md`. `COPIONE.md` resta sempre fuori da Git.
- Specifica unica e cumulativa in `specs.md`, una sezione per passo (la prossima sarebbe la §20). I piani vanno in
  `docs/superpowers/plans/`.
- L'agente deve usare **sempre** gli strumenti, mai valori a mente. Si interviene sul prompt e si misura,
  non si forza dal codice.
- Il controllore fa prove accurate, così l'utente non deve farle a mano, e riporta i problemi trovati con
  la correzione proposta prima del commit.
- Risposte in italiano. Quando l'utente chiede «a che punto è?», dare lo stato concreto: n/N, numeri
  parziali, tempo stimato.

## 5. Comandi (da `lezione_4/`)

```powershell
.\venv\Scripts\python.exe -m pytest -q                       # suite attesa: 436 passed, 21 skipped (al 2026-11-16)
$env:RUN_REAL_TESTS="1"; .\venv\Scripts\python.exe -m pytest -m reale -v -s   # reali, ~15–20 min
.\venv\Scripts\python.exe -m assistente                      # chat
docker compose build; docker compose run --rm assistente    # Docker (avviare prima Docker Desktop a mano)
```

App vera via stdin, in Git Bash, per misure e regressione:
`PYTHONIOENCODING=utf-8 LOG_LEVEL=INFO ./venv/Scripts/python.exe -m assistente < domande.txt > uscita.txt 2>&1`

## 6. Fatti di ambiente e lezioni utili

- LM Studio su `http://localhost:1234/v1`, modello `qwen/qwen3.5-9b`, ragionamento disattivato
  (`reasoning_effort: "none"` nel body). Se è spento: `lms server start` e `lms load qwen/qwen3.5-9b -y`;
  la CLI è in `~/.lmstudio/bin`.
- Il contesto di 8192 token è condiviso tra le richieste parallele: al massimo **una** sessione di misura
  alla volta, due con cautela. Oltre si ottiene HTTP 400 «Context size has been exceeded».
- Il prompt di sistema dell'agente occupa circa 1350 token; un turno sull'ora circa 112.
- Router, revisore e il futuro riassunto usano lo stesso modello, timeout 60 s, `max_retries=0`
  (ChatOpenAI ripeterebbe 2 volte per default) e fail-open.
- Output strutturato: il campo `motivo` va **prima** della decisione, perché alza molto la qualità.
  Si usa `method="json_schema"`.
- Prompt: esempi di chiamata, mai risposte pronte. Misurare anche su domande diverse dagli esempi.
  Al massimo 3 giri di ritocco, poi si tiene il migliore.
- I valori attesi che dipendono dalla data vanno calcolati da quella restituita dall'orologio.
- Per confrontare con una versione precedente: `git worktree add --detach <scratchpad>/vecchio <commit>`,
  copiare `.env`, lanciare con il python del venv principale, poi `git worktree remove --force`.
- Nei heredoc Python lanciati da Bash, `\n` diventa un a-capo vero: per stringhe con `\n` usare Edit.
- Fine riga misti CRLF/LF nell'albero di lavoro sono normali (nell'indice LF).
- Fissati per Smart App Control: `jiter 0.17.0` e `uuid_utils 0.18.0`. Gli avvisi di import di Pyright
  vengono dall'editor che non usa il venv.

## 7. Come riprendere

1. Nuova sessione in `repo-lab-llm/`, dire: «riprendi la lezione 4 da `lezione_4/docs/superpowers/handoff.md`».
2. Controllare `git status` e `git log -1`. Atteso: `2eea005` (o un commit successivo dell'utente) con le
   modifiche del passo 3 nell'albero: `specs.md` (§16 + §19 + §6.2), `.env.example`, `README.md`, `CLAUDE.md`,
   `assistente/` (config, grafo, router, revisore, sessione, terminale, `?? riassunto.py`), `tests/`
   (`?? test_riassunto.py`, finti, test_config/grafo/reale/revisore/router/sessione/terminale), `?? COPIONE.md`,
   il piano e questo file. Suite attesa: **484 passed, 28 skipped**. Controllare che LM Studio sia acceso.
3. Il passo 3 è completo (non committato; il commit solo quando l'utente dà il messaggio: specs senza §16,
   COPIONE fuori). Decisioni dell'utente a fine giornata 2026-11-17: (1) diagnosi ok; (2) correggere il prompt
   dell'agente; (3) fare i valori realistici. **Avviati subito dopo (~11:50)**, «mal che vada ci fermiamo»:
   - A. ritocco di `PROMPT_SISTEMA` (nome, preferenze e seguiti dal riassunto), max 3 giri; ogni giro = i 2 reali
     sulla compressione ripetuti 3 volte; poi misure 1–2 e regressione. Stima 2–2,5 h.
   - B. valori realistici (`token`, ~5000, ultimi 3 turni) nei predefiniti + misura lunga (35–45 turni). Stima 1,5–2 h.
   Lo stato di partenza (fine Task 6) è il tree `9fca4d1`: se A o B peggiorano, si torna lì con
   `git restore --source=<tree> -- <file>`. Esiti di A e B in fondo a `progress.md`.

   **Esito al 2026-11-17 12:40 (fermato dall'utente dopo il giro 1 di A):**
   - A giro 1 = `PREFISSO_RIASSUNTO` rafforzato in `assistente/riassunto.py` (dice di usare il riassunto per
     nome, preferenze e seguiti brevi; `PROMPT_SISTEMA` invariato, quindi senza riassunto non cambia nulla);
     3 test unitari usano la costante. Prova diretta sull'agente (`spike_agente.py`, 5 casi × 2): P0 8/10, P1 9/10.
     Reali sulla compressione ×3: **nome 2/3, seguito 1/3** (prima nome 1/2, seguito 0/3). Nel fallimento del
     nome il riassunto diceva solo «Elia ha chiesto le ore a Tokyo» → serve anche una regola nel riassuntore
     («inizia con nome e preferenze dell'utente: "L'utente si chiama …"»).
   - B = predefiniti realistici fatti (`token`, 5000, 3) in config, test, `.env.example`, README, §19.4.
     Un turno pesa ~25 token stimati: 5000 ≈ 200 turni, quindi la misura lunga non è fattibile; da fare solo
     una prova reale in modalità token con `RIASSUNTO_SOGLIA=300` (≈12 turni). NON fatta.
   - Tree dopo A giro 1 + B: `c471cf4`. Suite 484/28.
   **Esito al 2026-11-17 sera (sessione successiva):**
   - A giro 2 = regola in testa a `ISTRUZIONI_RIASSUNTO` («Inizia sempre il riassunto con una frase sul nome e
     sulle preferenze dell'utente, per esempio "L'utente si chiama Elia e preferisce le distanze in miglia."…»),
     chiave aggiunta in `test_istruzioni`. Prova diretta del riassuntore: 4/4 riassunti con nome noto iniziano così.
     Reali compressione ×3: **nome 3/3**, seguito ~1/3 (una volta il router rifiuta «e in piedi?», una volta il test
     passa ma la risposta dà solo i km). Decisione dell'utente: **niente giro 3**, il seguito resta limite noto.
   - Prova token reale = misure 1 e 2 rifatte con `RIASSUNTO_SOGLIA_TIPO=token RIASSUNTO_SOGLIA=300
     RIASSUNTO_TURNI_DA_TENERE=3`: la modalità token funziona (log con token stimati, compressioni 355→119, 368→197,
     305→129). Misura 1: nome e unità preferita giusti dopo la compressione; errore al t15 («cosa ti avevo chiesto
     all'inizio?» → ripete la risposta prima, falsa mista); limite revisioni al t12 (preesistente). Misura 2:
     15/15 giuste, nome e preferenza «breve» ricordati (prima 0/2).
   - README «Misure del riassunto» aggiornato (tabella dei giri, misure in modalità token, limiti noti).
   - Regressione 15 domande NON rifatta dopo i giri 1–2 (l'ultima è quella di fine Task 6: 14/14).
   - Tree finale: `54f31b0`. Suite 484/28. Esiti in `misura_1_token300.txt`, `misura_2_token300.txt`,
     `reali_R2_1..3.txt`, `spike_R2.txt`, `progress.md`.
4. **Prossimo, prima del commit — richiesta dell'utente:** spostare i nodi su un ramo nuovo «i tre nodi» (Git non
   accetta spazi: proporre `i-tre-nodi`). I commit già pushati dei 2 nodi (`3f47059` router, `96d46a2` fix,
   `2eea005` secondo nodo) devono stare SOLO sul ramo nuovo: crearlo da `2eea005`, committare lì il terzo nodo,
   riportare `feature/nuove-funzionalita` a prima di `3f47059` → serve force push (confermare con l'utente);
   chiedere se `d2a40b5` (uuid_utils) resta sul ramo vecchio. Messaggio di commit dall'utente (specs senza §16,
   COPIONE fuori, niente Co-Authored-By nei commit dettati).
