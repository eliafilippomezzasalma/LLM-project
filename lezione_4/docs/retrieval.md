# Retrieval sul ricettario dell'Artusi: misure

RAG parte 1 (`specs.md` §20): indice vettoriale delle ricette e ricerca per significato, senza
generazione. Misure del 2026-11-23, prese dal controllore con Qdrant e LM Studio veri.

## Configurazione misurata

| Voce | Valore |
|---|---|
| Corpus | Artusi, *La scienza in cucina e l'arte di mangiar bene*, Project Gutenberg n. 59047 (`dati/artusi.txt`) |
| Documenti | 790 ricette numerate (23 capitoli); restano fuori prefazione, lettere, appendice e licenza |
| Chunking | per ricetta, poi ai paragrafi; dimensione 1200 caratteri, overlap 200 |
| Chunk | 1106 (caratteri min/medi/max: 64/811/1394) |
| Modello di embedding | `text-embedding-nomic-embed-text-v1.5` (LM Studio), vettori da 768, distanza coseno |
| Testo indicizzato | il testo del chunk così com'è, senza titolo né prefissi |
| Qdrant | `qdrant/qdrant:v1.20.2`, collezione `ricette`, indici su `capitolo` e `ricetta` |

## Test a servizi spenti

Con Qdrant fermo (`docker compose stop qdrant`) e il server di LM Studio fermo
(`lms server stop`), le due porte rifiutavano la connessione e la suite intera dava
**558 passed, 28 skipped** (i 28 saltati sono le prove reali, attive solo con `RUN_REAL_TESTS=1`).
Dopo le correzioni della revisione finale, la suite è a **562 passed, 28 skipped**.

Con i servizi spenti i tre comandi terminano con un messaggio e codice di uscita 1, senza traceback.
Messaggi visti:
- `Errore: LM Studio non raggiungibile su http://localhost:1234/v1: avvialo e attiva il server locale`
- `Errore: Qdrant non raggiungibile su http://localhost:6333: docker compose up -d qdrant e controlla QDRANT_URL`
- `Errore: la collezione 'ricette' non esiste: esegui prima python -m rag.ingestion`

## Le due ingestion complete

Comando: `.\venv\Scripts\python.exe -m rag.ingestion`, con Qdrant appena creato (collezione vuota).

| Esecuzione | Ricette | Chunk | Punti prima | Punti dopo | Rimossi | Tempo |
|---|---|---|---|---|---|---|
| 1ª | 790 | 1106 | 0 | **1106** | 0 | 135,8 s |
| 2ª | 790 | 1106 | 1106 | **1106** | 0 | 132,5 s |
| 3ª (dopo le correzioni della revisione finale) | 790 | 1106 | 1106 | 1106 | 0 | 131,9 s |

Il numero di punti è lo stesso dopo la prima e dopo la seconda esecuzione: gli ID sono stabili
(UUID v5 di ricetta e posizione del chunk) e la scrittura è un upsert.

Dopo `docker compose restart qdrant` la collezione aveva ancora 1106 punti, quindi il volume
persiste. Nei metadati della collezione risultano `modello_embedding` e `dimensione` (768).

## Valutazione di partenza (k = 5)

Comando: `.\venv\Scripts\python.exe -m rag.valutazione --k 5` (domande in
`rag/domande_valutazione.json`; fonti attese decise prima della ricerca e controllate sul testo).

| Domanda | Fonte attesa | Posizione | Score fonte | Score migliore | Primo risultato |
|---|---|---|---|---|---|
| Quanta farina serve per 400 grammi di patate negli gnocchi? | 89 | 1 | 0,771 | 0,771 | 89 — Gnocchi di patate |
| Che vino si usa per il pollo alla cacciatora? | 208 | assente | — | 0,718 | 264 — Pollo colla marsala |
| Come si chiama il cacciucco sulle coste dell'Adriatico? | 455, 456 | 1 | 0,794 | 0,794 | 455 — Cacciucco I |
| Quanti cappelletti bastano a un mangiatore moderato? | 7 | assente | — | 0,754 | 349 — Pasticcio di maccheroni |
| Perché gli gnocchi possono sciogliersi nell'acqua? | 89 | 1 | 0,755 | 0,755 | 89 — Gnocchi di patate |
| Qual è la ricetta del tiramisù? | nessuna (non nel libro) | — | — | 0,720 | 641 — Torta di patate |

Fonte attesa nei primi 5: **3 su 5**. Score migliore della domanda senza risposta: 0,720.

**Il chunk contiene davvero l'informazione?** Il controllo è fatto leggendo il testo restituito.
- Gnocchi, farina: sì. Il chunk 0 della 89 contiene le dosi (patate 400 g, farina 150 g).
- Cacciucco: sì. Il chunk 0 della 455 dice che «ne' paesi che costeggiano l'Adriatico è
  sostituita dalla voce brodetto».
- Gnocchi che si sciolgono: sì, anche se le parole sono diverse. Il chunk 0 racconta che gli
  gnocchi «erano stati intrisi con poca farina e appena furono nell'acqua bollente si liquefecero».
- Cappelletti: la frase giusta («A un mangiatore discreto bastano due dozzine») è nel chunk 1
  della ricetta 7. Con k = 10 compare in 6ª posizione (0,732), fuori dai primi 5.

**Confronto con l'aula** (stessa configurazione: nomic, paragrafi 1200/200).
- In aula: 6 su 8 domande, con la tabella in slide.
- Qui coincidono gnocchi (1ª posizione, 0,777 in aula contro 0,771 qui) e cacciatora (assente in
  entrambi).
- I cappelletti in aula erano 4ⁱ, qui sono 6ⁱ: il chunking non è identico a quello del docente.
- Come in aula, la domanda sul tiramisù ottiene uno score (0,720) simile a quello delle domande con
  risposta. Lo score da solo non dice se il libro contiene la risposta.

## Due query commentate

**Trovata: «Come si chiama il cacciucco sulle coste dell'Adriatico?»**
- La 455 «Cacciucco I» è 1ª con 0,794, staccata dalle altre (la 2ª è a 0,733).
- La domanda e il chunk condividono le parole rare («cacciucco», «Adriatico»), e l'informazione
  sta nelle prime righe della ricetta, quindi nel chunk 0.
- Gli altri risultati sono pesci dell'Adriatico (cicale, storione, acciughe): vicini per argomento,
  ma non rispondono.

**Mancata: «Che vino si usa per il pollo alla cacciatora?»**
- La 208 non compare tra i primi 5 e neppure tra i primi 10.
- La risposta c'è nel testo: «Giovese od altro vino rosso del migliore».
- Però la parola «cacciatora» sta solo nel titolo, che non è nel testo indicizzato.
- Il vettore del chunk non porta il nome del piatto, e la domanda si avvicina a ricette di pollo
  con il vino («Pollo colla marsala», 0,718).
- È l'errore tipico «termine chiave solo nel titolo» delle slide. La modifica B dell'Esercizio 2
  (titolo e capitolo nel testo indicizzato) lo affronta direttamente.

## Domande di prova proprie

Cinque domande scritte **senza le parole del testo**: nessuna parola significativa della domanda
compare nel titolo o nel testo della ricetta attesa (controllo fatto con uno script prima della
ricerca). Le domande e le fonti attese sono state approvate dall'utente prima di lanciare la ricerca
e stanno in `rag/domande_valutazione.json` con `origine: "propria"`.

| Domanda | Fonte attesa | Parole del libro evitate | Posizione (k = 5) | Posizione nella collezione | Score fonte | Score migliore | Primo risultato |
|---|---|---|---|---|---|---|---|
| Come si ottiene una riduzione dolce dal succo degli acini, che i ragazzi nella stagione fredda usavano per farsi una granita? | 731 — Sapa | siroppo, uva, bambini, inverno, neve, sorbetti | assente | 98ª ricetta | 0,726 | 0,771 | 142 — Rossi d'uovo al canapè |
| In quali pasticcini a base di polenta si aggiunge un'infiorescenza essiccata con proprietà che fanno traspirare? | 591 — Paste di farina gialla II | farina gialla, fiori secchi, sambuco, sudare | assente | 336ª ricetta | 0,689 | 0,761 | 232 — Polenta di farina gialla colle salsicce |
| Quale ortaggio a cime, dal retrogusto pungente e poco stimato nel resto della penisola, si accompagna alla carne bollita? | 434 — Broccoli o talli di rape alla fiorentina | broccoli, rape, amarognolo, Italia, contorno, lesso | assente | 374ª ricetta | 0,724 | 0,790 | 330 — Animelle alla bottiglia |
| Come si fa un dessert ghiacciato con i biscottini croccanti dal retrogusto amaro? | 760 — Gelato di amaretti | gelato, amaretti, sorbettiera | assente | 289ª ricetta | 0,695 | 0,758 | 182 — Krapfen I |
| Come si prepara il guacamole con l'avocado maturo? | nessuna (non nel libro) | — | — | — | — | 0,731 | 405 — Cardoni in umido |

Comando: `.\venv\Scripts\python.exe -m rag.valutazione --k 5`. Totale con le domande d'aula:
**3 su 9** a k = 5, **4 su 9** a k = 10 (si aggiungono solo i cappelletti). La «posizione nella
collezione» è stata misurata a parte, chiedendo a Qdrant tutti i 1106 punti e contando le ricette
distinte prima della fonte attesa.

**Esito: nessuna delle quattro fonti attese è tra i primi 10.** È il risultato più istruttivo
della valutazione.
- Con le parole del libro (domande d'aula) la ricerca trova la fonte 3 volte su 5. Senza parole in
  comune la fonte non arriva mai in cima: la più vicina, la Sapa, è 98ª.
- Il modello di embedding avvicina la domanda a ricette che condividono le parole *della domanda*:
  «polenta» porta alla Polenta colle salsicce (che però non è la fonte), «carne bollita» porta a
  piatti di carne, «dessert» a dolci e fritti dolci. I sinonimi e le perifrasi («infiorescenza
  essiccata» per «fiori secchi di sambuco», «biscottini dal retrogusto amaro» per «amaretti») non
  bastano a raggiungere il testo dell'Artusi, scritto in un italiano dell'Ottocento.
- Gli score non separano i casi: la domanda sul guacamole (non nel libro) ha come score migliore
  0,731, più alto dello score di tutte e quattro le fonti giuste (da 0,689 a 0,726). Come per il
  tiramisù, una soglia sullo score non basterebbe a dire «il libro non risponde».
- Le leve da provare su queste domande sono le tecniche della lezione 8 (riscrittura della domanda
  con le parole del libro, reranking) e la modifica B dell'Esercizio 2 (titolo nel testo
  indicizzato).

## Leve del retrieval (§21)

Misure del 2026-11-23 su **19 domande**: le 11 precedenti più 8 nuove, fissate prima di ogni
misura. Delle 17 domande con fonte attesa, **9 usano le parole del libro** (5 d'aula, 4 nuove) e
**8 sono parafrasate** senza parole in comune con la ricetta (4 della sezione precedente, 4 nuove).
Le altre due non hanno risposta (tiramisù, guacamole). Le leve si sono aggiunte una alla volta, in
ordine, ciascuna nella sua collezione Qdrant (1106 punti ogni volta). Si teneva una leva solo se
aumentava le fonti nei primi 5, oppure a parità nei primi 10.

### Confronto

| Configurazione | Collezione | Parole del libro, primi 5 | Parafrasi, primi 5 | Totale primi 5 | Totale primi 10 | Score migliore senza risposta (tiramisù, guacamole) |
|---|---|---|---|---|---|---|
| 0. Partenza (§20: nomic, chunk così com'è) | `ricette` | 6/9 | 0/8 | 6/17 | 7/17 | 0,720 · 0,731 |
| 1. + prefissi di nomic | `ricette_prefissi` | 6/9 | 0/8 | 6/17 | 7/17 | 0,736 · 0,722 |
| 2. Partenza + titolo e capitolo nel testo indicizzato | `ricette_titolo` | **9/9** | 0/8 | 9/17 | 9/17 | 0,725 · 0,728 |
| 3. 2 + riscrittura della domanda (`qwen/qwen3.5-9b`) | `ricette_titolo` | 9/9 | 1/8 | 10/17 | 11/17 | 0,761 · 0,773 |
| 4. bge-m3 + titolo + riscrittura | `ricette_bge` | 9/9 | **3/8** | **12/17** | **13/17** | 0,597 · 0,627 |
| (controllo) bge-m3 + titolo, senza riscrittura | `ricette_bge` | 9/9 | 0/8 | 9/17 | 9/17 | 0,515 · 0,475 |

Le configurazioni 3 e 4 sono state valutate con `--k 10`, perché ogni domanda richiede una
chiamata da circa 20 s al modello di chat. Il conteggio nei primi 5 viene dalle posizioni della
stessa esecuzione: con la temperatura a 0 le riscritture sono risultate identiche nelle due
esecuzioni. Comandi: `rag.ingestion` e `rag.valutazione` con le variabili della §21 impostate
nell'ambiente (README).

### Posizione della fonte domanda per domanda (k = 10)

| Domanda (abbreviata) | Fonte | Tipo | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|---|---|
| Farina per gli gnocchi | 89 | libro | 1 | 1 | 2 | 2 | 1 |
| Vino del pollo alla cacciatora | 208 | libro | assente | assente | 1 | 1 | 1 |
| Cacciucco sull'Adriatico | 455, 456 | libro | 1 | 1 | 1 | 1 | 1 |
| Cappelletti per un mangiatore moderato | 7 | libro | 6 | 1 | 1 | 1 | 1 |
| Gnocchi che si sciolgono | 89 | libro | 1 | 5 | 1 | 1 | 1 |
| Minestrone e colèra a Livorno | 47 | libro | 1 | 1 | 1 | 1 | 1 |
| Erbe della salsa verde | 119, 120 | libro | 2 | 6 | 2 | 1 | 1 |
| Agnello all'aretina, mese | 529 | libro | 1 | 1 | 1 | 1 | 1 |
| Ponce alla romana avanti all'arrosto | 770 | libro | assente | assente | 1 | 1 | 1 |
| Riduzione dolce dagli acini (Sapa) | 731 | parafrasi | assente | assente | assente | assente | assente |
| Pasticcini di polenta con infiorescenza (sambuco) | 591 | parafrasi | assente | assente | assente | 8 | **4** |
| Ortaggio a cime con il bollito (broccoli) | 434 | parafrasi | assente | assente | assente | assente | assente |
| Dessert ghiacciato con biscottini amari | 760 | parafrasi | assente | assente | assente | 5 | 6 |
| Gherigli, cacao e albumi (torta di noci) | 637 | parafrasi | assente | assente | assente | assente | assente |
| Strati di formaggio fresco e biscotti (zuppa tartara) | 676 | parafrasi | assente | assente | assente | assente | **1** |
| Semi oleosi glassati (mandorle tostate) | 785 | parafrasi | assente | assente | assente | assente | assente |
| Baccelli verdi con aroma da pasticceria (fagiuolini) | 382 | parafrasi | assente | assente | assente | assente | **1** |

Tabelle complete e riscritture: output di `rag.valutazione` conservati nel registro di lavoro
(fuori da Git).

### Che cosa ha aiutato e che cosa no

- **Prefissi di nomic: nessun effetto netto, tolti.**
  - I cappelletti salgono dal 6° al 1° posto.
  - In cambio «gnocchi che si sciolgono» scende al 5° e la salsa verde al 6°.
  - Il totale resta 6 su 17 nei primi 5 e 7 su 17 nei primi 10.
  - Con queste domande in italiano i prefissi inglesi del modello non portano vantaggi misurabili.
- **Titolo e capitolo nel testo indicizzato: la leva più efficace per le domande con le parole del
  libro, tenuta.** Da 6 a **9 su 9**.
  - Cacciatora e ponce, che erano assenti, passano al 1° posto: il nome del piatto stava solo nel
    titolo, come previsto dall'analisi della query mancata.
  - Sulle parafrasi non cambia nulla, perché il titolo non ha parole in comune con la domanda.
- **Riscrittura della domanda: utile, ma fragile da sola. Tenuta.**
  - Con nomic porta 2 parafrasi su 8 nei primi 10 (sambuco 8°, gelato di amaretti 5°).
  - Il modello da 9B **inventa spesso**:
    - il ponce diventa «un dolce di pasta frolla»;
    - i broccoli diventano «cavolo nero»;
    - la sapa diventa «granita di fichi»;
    - l'anno del colèra diventa 1854 invece di 1855.
  - Aiuta quando, pur sbagliando il contesto, nomina l'ingrediente chiave del libro: «sambuco»,
    «ricotta», «fagiolini», «gelato».
  - Cercare domanda e riscrittura insieme fa sì che una riscrittura sbagliata non cancelli la domanda
    originale. Sulle domande con le parole del libro il risultato resta 9 su 9.
- **bge-m3: il salto più grande, ma solo insieme alla riscrittura.**
  - Senza riscrittura fa come nomic con il titolo: 9 su 17, nessuna parafrasi.
  - Con la riscrittura arriva a **12 su 17 nei primi 5**. Zuppa tartara e fagiuolini passano da
    assenti al 1° posto, il sambuco al 4°.
  - Il modello multilingue sfrutta meglio le parole italiane che la riscrittura aggiunge, anche
    quando il resto della riscrittura è sbagliato.
- **Restano fuori quattro parafrasi: sapa, broccoli, torta di noci e mandorle tostate.**
  - In tutti e quattro i casi la riscrittura sbaglia il piatto: granita di fichi, cavolo nero,
    «ciambellone» con le mandorle, «fritto di semi» di sesamo.
  - In questi casi la ricerca non ha più da dove ripartire: serve un modello di chat che conosca
    meglio la cucina dell'Ottocento, oppure altre tecniche della lezione 8 (più riscritture,
    reranking).
- **Domande senza risposta:**
  - Con bge-m3 senza riscrittura gli score si separano meglio: 0,515 e 0,475 contro almeno 0,553
    per le fonti giuste. Prima, con nomic, erano mescolati.
  - Con la riscrittura tornano a sovrapporsi: tiramisù 0,597 e guacamole 0,627, mentre la fonte del
    sambuco ha 0,576. La riscrittura infatti aggiunge parole di cucina anche a domande fuori dal
    libro.
  - Una soglia sullo score resta inaffidabile e va tarata sulla configurazione finale.

**Configurazione consigliata:** bge-m3, titolo nel testo e riscrittura (collezione `ricette_bge`).
Costa circa 20 s di modello di chat per ogni domanda e un'ingestion di 262 s invece di 160 s. Se la
latenza conta più delle parafrasi, conviene la configurazione 2 (nomic e titolo, nessuna chiamata
in più), che trova comunque tutte le domande scritte con le parole del libro. I predefiniti di
`.env.example` restano quelli della §20, e la scelta passa dalle variabili d'ambiente.

## Esercizio 2: modifiche A e B (§22)

Misure del 2026-11-23 sulle stesse 19 domande (17 con fonte attesa). Tutte le valutazioni sono
fatte senza riscrittura.

| Valutazione | Collezione | Primi 5 | Primi 10 | Parole del libro (primi 5) | Parafrasi (primi 5) |
|---|---|---|---|---|---|
| Partenza (§20) | `ricette` | 6/17 | 7/17 | 6/9 | 0/8 |
| Dopo A, senza filtro | `ricette` con `contiene_dosi` | 6/17 | 7/17 | 6/9 | 0/8 |
| Dopo A, con `--solo-dosi` su tutte le domande | `ricette` | 3/17 | 3/17 | 3/9 | 0/8 |
| Dopo B (titolo e capitolo nel testo indicizzato) | `ricette_b` | **9/17** | 9/17 | **9/9** | 0/8 |

### Modifica A: campo `contiene_dosi` e filtro

- **Il campo:** è vero se il chunk ha almeno due righe d'elenco del tipo «ingrediente, quantità»,
  per esempio «Patate grosse e gialle, grammi 400.» o «Sale, quanto basta.». La riga dev'essere
  corta (al più 90 caratteri), così non conta la prosa con una virgola.
  - Risultato: **397 chunk su 1106** (346 ricette su 790).
  - L'ingestion scrive il campo e crea l'indice booleano sul payload. Sul server l'indice
    risulta in `payload_schema` insieme a `capitolo` e `ricetta`.
- **I punti esistenti ricevono il campo senza ricalcolare gli embedding:**
  - `python -m rag.metadati` legge il testo dal payload e scrive solo il campo.
  - È stato eseguito su tutte e cinque le collezioni (`ricette`, `ricette_prefissi`,
    `ricette_titolo`, `ricette_bge`, `ricette_b`): ogni volta 1106 punti, 397 veri e 709 falsi,
    in pochi secondi e senza chiamate a LM Studio.
  - La prova che i vettori sono invariati: la valutazione di `ricette` dopo l'aggiornamento è
    identica, riga per riga, a quella di partenza.
  - Un test confronta anche i vettori prima e dopo.
- **Il filtro:** l'opzione `--solo-dosi` invia a Qdrant la condizione `contiene_dosi = true`
  durante la ricerca, in `must` insieme a quella sul capitolo.
  - Tutti i risultati hanno il campo vero e sono al più k.
  - Esempio: «Quanta farina e quante patate servono per gli gnocchi?» con
    `--capitolo "minestre asciutte e di magro" --solo-dosi --k 3` restituisce al 1° posto la 89
    «Gnocchi di patate» (0,780, chunk 0 con le dosi), poi due ricette dello stesso capitolo, tutte
    con l'elenco di dosi.
- **Cosa dice la valutazione con il filtro applicato a tutte le domande:**
  - La domanda sulle dosi degli gnocchi resta 1ª.
  - «Quanti cappelletti bastano…» sale dal 6° al **3° posto**, perché il filtro toglie i chunk di
    racconto che la precedevano. Però il chunk trovato è il chunk 0 della ricetta 7 (le dosi
    della pasta e del ripieno). La frase che risponde («A un mangiatore discreto bastano due
    dozzine») sta nel chunk 1, che non ha l'elenco e quindi viene escluso dal filtro. È una fonte
    giusta come ricetta, ma non come passaggio.
  - Le domande che non chiedono dosi (cacciucco, minestrone, salsa verde, agnello, ponce) escono
    tutte, come previsto.
  - **Conclusione:** il filtro serve quando la domanda chiede le quantità e chi cerca lo sceglie.
    Non va applicato a tutte le domande: da 6 a 3 su 17.

### Modifica B: titolo nel testo indicizzato, senza ricreare la collezione

- **Che cosa cambia rispetto alla §21:** nella §21 il titolo era stato misurato in una collezione
  nuova (`ricette_titolo`), e la collezione bloccava un'ingestion con impostazioni diverse. Ora
  l'ingestion **ricalcola tutti i vettori nella stessa collezione** e alla fine registra le nuove
  impostazioni.
  - Mentre lavora segna la collezione come «ingestion incompleta», e la ricerca si ferma finché il
    segno resta.
  - Il cambio di modello resta bloccato.
- **Prova sulla collezione `ricette_b`:**

| Ingestion | Configurazione | Punti prima | Punti dopo | Rimossi | Tempo |
|---|---|---|---|---|---|
| 1ª | partenza (senza titolo) | 0 | 1106 | 0 | 118,2 s |
| 2ª, stessa collezione | `INDICE_CON_TITOLO=si` | 1106 | **1106** | 0 | 121,7 s |

- **Dopo la 2ª ingestion:** i metadati della collezione riportano `titolo_nel_testo: true` e
  `ingestion_incompleta: false`. Gli indici sono `capitolo` (keyword), `ricetta` (integer) e
  `contiene_dosi` (bool).
- **Valutazione dopo B:** è identica, posizione per posizione, a quella di `ricette_titolo`
  (configurazione 2 della §21).
  - Da 6 a **9 su 17** nei primi 5.
  - Le domande con le parole del libro passano da 6 a 9 su 9: cacciatora e ponce salgono al 1°
    posto perché il nome del piatto, prima solo nel titolo, ora è nel testo indicizzato.
  - La ricerca restituisce comunque il testo originale del chunk.
  - Un test verifica il testo passato all'embedder («titolo — capitolo», riga vuota, testo).
- **Sulle parafrasi B non cambia nulla:** per quelle servono la riscrittura e bge-m3 (§21).

### Test a servizi spenti (dopo l'Esercizio 2)

Con Qdrant fermato (`docker compose stop qdrant`) e il server di LM Studio fermato
(`lms server stop`), con entrambe le porte che rifiutano la connessione, la suite intera dà
**602 passed, 28 skipped**. Con i servizi spenti `python -m rag.metadati` termina con
`Errore: Qdrant non raggiungibile su http://localhost:6333: ...` e codice di uscita 1, senza
traceback.
