# RAG parte 1 (ingestion e ricerca sull'Artusi): piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** indice vettoriale ripetibile delle 790 ricette dell'Artusi in Qdrant e ricerca top-k con filtro per capitolo, misurata sulle domande con fonte attesa.

**Architecture:** nuovo pacchetto `lezione_4/rag/`, separato da `assistente/` (l'assistente non cambia). Moduli piccoli: configurazione, corpus (pulizia e ricette), chunking, embedder (LM Studio via `openai`), indice (Qdrant), ingestion, ricerca, valutazione; i tre comandi sono `python -m rag.ingestion`, `python -m rag.ricerca`, `python -m rag.valutazione`. I test usano un embedder finto deterministico e `QdrantClient(":memory:")`.

**Tech Stack:** Python 3.12 (venv di `lezione_4`), `qdrant-client` (nuova, versione fissata), `openai` (già presente) per `/v1/embeddings`, `python-dotenv`, pytest; Qdrant in Docker Compose; LM Studio sull'host con `text-embedding-nomic-embed-text-v1.5`.

**Spec:** `lezione_4/specs.md` §20 (approvata il 2026-11-23). Leggerla prima di ogni task.

## Global Constraints

- Lavorare solo in `lezione_4/`, branch `RAG`. Comandi da `lezione_4/` con `./venv/Scripts/python.exe`.
- **Mai** in Git: `COPIONE.md`, `dati/` (con `dati/artusi.txt`), il `Ricettario.txt`, `.env`, la §16 di `specs.md` (commit parziale di `specs.md`), la modifica locale di `docs/superpowers/handoff.md`.
- **Commit:** a fine task il controllore **propone** il commit all'utente con un messaggio Conventional Commits suggerito; si esegue **solo su suo ordine** e con il messaggio che sceglie (se lo detta: esatto, senza Co-Authored-By). I subagenti non fanno mai commit.
- Nome del modello di embedding solo da `EMBEDDING_MODEL`, mai nel codice (neppure come predefinito: il predefinito sta in `.env.example`).
- Predefiniti: `QDRANT_URL=http://localhost:6333`, `QDRANT_COLLECTION=ricette`, `RAG_CORPUS=dati/artusi.txt`, `CHUNK_STRATEGIA=paragrafi`, `CHUNK_DIMENSIONE=1200`, `CHUNK_OVERLAP=200`, `RICERCA_K_MAX=10`; k predefinito 5; distanza coseno.
- Errori previsti → messaggio in italiano su stderr, codice di uscita 1, **nessun traceback**.
- Testi, messaggi, nomi di dominio e docstring in italiano, come il resto del progetto.
- Test automatici **senza servizi**: nessun test (salvo quelli `reale`, saltati senza `RUN_REAL_TESTS=1`) apre connessioni di rete.
- La suite esistente dell'assistente resta verde; `assistente/` non si tocca.

## Review Focus

- **File con CRLF (com'è il `Ricettario.txt`) o con BOM** → stesse 790 ricette e nessun `\r` nei testi. Test in Task 2.
- **Riga del corpo che inizia con il numero giusto** (es. una riga «140. …» dentro la ricetta 139 non preceduta da riga vuota) → non è un titolo: il titolo richiede numero successivo **e** riga vuota prima. Test in Task 2.
- **Capitolo scritto in minuscolo o con spazi** (`--capitolo fritti`, `" Fritti "`) → accettato e ricondotto al nome canonico «Fritti»; nome inesistente → errore con l'elenco. Test in Task 6.
- **Qdrant spento o LM Studio senza modello di embedding** → messaggio chiaro con il rimedio, exit 1, nessun traceback e nessuna scrittura parziale. Test in Task 4 (embedder) e Task 5 (ingestion con client che solleva).
- **Ricerca su collezione assente** (ingestion mai eseguita) → errore «esegui prima `python -m rag.ingestion`», non una lista vuota. Test in Task 6.

---

### Task 1: dipendenza, configurazione e regole stabili

**Files:**
- Modify: `requirements.txt`, `.gitignore`, `compose.yaml`, `.env.example`, `CLAUDE.md`
- Create: `rag/__init__.py`, `rag/config.py`, `rag/errori.py`, `tests/test_rag_config.py`

**Interfaces:**
- Produces: `rag.errori.ErroreRag(Exception)` (base di tutti gli errori previsti; il messaggio è per l'utente). `rag.config.ConfigRag` (dataclass frozen: `lm_base_url: str`, `embedding_model: str`, `qdrant_url: str`, `collezione: str`, `corpus: Path`, `strategia: Literal["paragrafi","finestra"]`, `dimensione: int`, `overlap: int`, `k_max: int`). `rag.config.carica_config_rag(env: Mapping[str,str] | None = None) -> ConfigRag` (senza argomenti: `load_dotenv` sul `.env` di `lezione_4` come `assistente/config.py`, poi `os.environ`). Errori: `rag.config.ErroreConfigurazioneRag(ErroreRag)`.

- [ ] **Step 1: verifica della dipendenza (controllore).** Installare `qdrant-client` nel venv (`./venv/Scripts/python.exe -m pip install qdrant-client==<ultima>`), poi provare: `from qdrant_client import QdrantClient, models; c = QdrantClient(":memory:")`, `create_collection(..., vectors_config=models.VectorParams(size=4, distance=models.Distance.COSINE), metadata={"modello": "x"})`, `get_collection(...).config.metadata`, upsert e `query_points` con `query_filter`. Se Smart App Control blocca una DLL → **fermarsi e chiedere all'utente** (spec §20.15). Se i metadati di collezione non esistono in memoria, annotare l'alternativa scelta per il Task 5 (per esempio un punto riservato con ID fisso, escluso da conteggi e ricerche) nel registro SDD.
- [ ] **Step 2:** fissare in `requirements.txt` `qdrant-client` e le dipendenze **nuove** che porta (`pip freeze` prima/dopo, in ordine alfabetico come il file). Scegliere l'immagine `qdrant/qdrant:v<X.Y.Z>` con la stessa minor del client (controllare che il tag esista).
- [ ] **Step 3: test che falliscono** in `tests/test_rag_config.py`:
  - `test_predefiniti`: `carica_config_rag({"LM_BASE_URL": "http://h:1234/v1", "EMBEDDING_MODEL": "m"})` → `qdrant_url == "http://localhost:6333"`, `collezione == "ricette"`, `corpus == Path("dati/artusi.txt")` risolto rispetto a `lezione_4/` se relativo, `strategia == "paragrafi"`, `dimensione == 1200`, `overlap == 200`, `k_max == 10`.
  - `test_embedding_model_obbligatorio`: senza `EMBEDDING_MODEL` → `ErroreConfigurazioneRag` con «EMBEDDING_MODEL» nel messaggio.
  - parametrico `test_valori_non_validi`: `CHUNK_STRATEGIA="frasi"`, `CHUNK_DIMENSIONE="0"`, `CHUNK_DIMENSIONE="abc"`, `CHUNK_OVERLAP="-1"`, `CHUNK_OVERLAP="1200"` (con dimensione 1200), `RICERCA_K_MAX="0"` → `ErroreConfigurazioneRag` con il nome della variabile.
  - `test_assistente_non_richiede_variabili_rag`: `assistente.config.carica_config` con le sole variabili dell'assistente funziona (nessun legame).
- [ ] **Step 4:** eseguire `./venv/Scripts/python.exe -m pytest tests/test_rag_config.py -q` → FAIL (modulo assente).
- [ ] **Step 5:** implementare `rag/errori.py`, `rag/config.py` (stesso stile di `assistente/config.py`), `rag/__init__.py` (docstring di una riga).
- [ ] **Step 6:** test → PASS; suite intera `./venv/Scripts/python.exe -m pytest -q` → verde (solo skip dei reali).
- [ ] **Step 7: file di progetto.**
  - `.gitignore`: aggiungere `dati/`.
  - `compose.yaml`: servizio `qdrant` (immagine fissata, `ports: ["6333:6333"]`, volume con nome `qdrant_dati:/qdrant/storage`, `volumes:` in fondo); `assistente` invariato.
  - `.env.example`: blocco commentato «RAG (specs.md §20)» con `EMBEDDING_MODEL=text-embedding-nomic-embed-text-v1.5`, `QDRANT_URL`, `QDRANT_COLLECTION`, `RAG_CORPUS`, `CHUNK_STRATEGIA`, `CHUNK_DIMENSIONE`, `CHUNK_OVERLAP`, `RICERCA_K_MAX` con i predefiniti. Aggiungere le stesse righe al `.env` locale (fuori da Git).
  - `CLAUDE.md`: in «Struttura» la riga `rag/`; in «Obiettivo» una riga RAG (§20); in «Confini» togliere «workflow e RAG non vanno anticipati» (resta «workflow») e mettere il branch `RAG` per il RAG; nuova sezione «RAG: regole stabili»: ingestion come script separato (non strumento dell'agente), modello di embedding dalla configurazione, Qdrant con Docker Compose e volume persistente, dati scaricati (`dati/`) e `.env` fuori da Git, test con embedder finto e Qdrant in memoria a servizi spenti; comandi `docker compose up -d qdrant` e i tre `python -m rag.…`.
  - Copiare il corpus: `mkdir dati` e copia di `…/argomenti verifica agente+tool+nodi+RAG/Ricettario.txt` in `dati/artusi.txt`; `git status` non deve mostrarlo.
- [ ] **Step 8:** `docker compose config` valido. Proporre il commit (es. `build(rag): configurazione, qdrant-client e servizio Qdrant`).

### Task 2: corpus — pulizia e 790 ricette

**Files:**
- Create: `rag/corpus.py`, `tests/test_rag_corpus.py`, `tests/dati_rag/estratto.txt`

**Interfaces:**
- Produces: `rag.corpus.CAPITOLI: tuple[str, ...]` (23 nomi leggibili, in ordine di libro). `@dataclass(frozen=True) Ricetta(numero: int, titolo: str, capitolo: str, testo: str)`. `leggi_ricette(testo: str) -> list[Ricetta]` (testo grezzo del file → ricette pulite, in ordine). `verifica_ricette(ricette: list[Ricetta], attese: int = 790) -> None` (solleva `ErroreCorpus(ErroreRag)` con il primo problema: numero mancante/doppio, titolo/capitolo/testo vuoti, conteggio diverso). `carica_corpus(percorso: Path) -> list[Ricetta]` (legge UTF-8 togliendo il BOM, `leggi_ricette` + `verifica_ricette`; file assente → `ErroreCorpus` con il percorso).

Regole (spec §20.2):
- Si considera solo il testo tra la riga `*** START OF THE PROJECT GUTENBERG` e la prima riga `APPENDICE` successiva alla ricetta 790 (la riga che chiude è la prima `APPENDICE` dopo l'inizio della ricetta 790).
- Capitolo: una riga che, tolti gli spazi, è uguale a una delle 23 intestazioni in maiuscolo (`BRODI, GELATINA E SUGHI`, `MINESTRE IN BRODO`, `MINESTRE ASCIUTTE E DI MAGRO`, `PRINCIPII`, `SALSE`, `UOVA`, `PASTE E PASTELLE`, `RIPIENI`, `FRITTI`, `LESSO`, `TRAMESSI`, `UMIDI`, `RIFREDDI`, `ERBAGGI E LEGUMI`, `PIATTI DI PESCE`, `ARROSTI`, `PASTICCERIA`, `TORTE E DOLCI AL CUCCHIAIO`, `SIROPPI`, `CONSERVE`, `LIQUORI`, `GELATI`, `COSE DIVERSE`) e che sta **dopo** la riga `RICETTE` che precede la ricetta 1; nome leggibile = `intestazione.capitalize()`. Il testo tra un'intestazione e la ricetta successiva (introduzioni) non entra in nessuna ricetta.
- Titolo: riga che corrisponde a `^(\d+)\. (.+)$`, con numero = precedente + 1 (la prima = 1) **e** preceduta da una riga vuota (o inizio del testo).
- Pulizia del testo di una ricetta: CRLF→LF; marcatori `_..._` tolti (resta il testo); righe non rientrate consecutive unite con uno spazio in un paragrafo; paragrafi separati da una riga vuota nel testo finale (`"\n\n"`); righe rientrate (ingredienti) restano righe proprie senza il rientro, e una riga rientrata più della precedente è la sua continuazione (unita con uno spazio); spazi multipli → uno; testo senza spazi in testa e in coda.

- [ ] **Step 1: estratto per i test.** `tests/dati_rag/estratto.txt` (in Git, poche centinaia di righe di dominio pubblico): intestazione Gutenberg breve + `RICETTE` + `BRODI, GELATINA E SUGHI` + ricette 1–3 copiate dal file, `MINESTRE` con due righe di introduzione + `MINESTRE IN BRODO` + ricetta 4 inventata con una riga del corpo «5. Mettete…» **non** preceduta da riga vuota e una riga di ingredienti con continuazione, + riga `APPENDICE` + riga «6. Falso titolo p. 7.». Salvarlo con fine riga CRLF.
- [ ] **Step 2: test che falliscono** (`tests/test_rag_corpus.py`):
  - `test_estratto_quattro_ricette`: `leggi_ricette(estratto)` → numeri `[1, 2, 3, 4]`, capitoli `["Brodi, gelatina e sughi"]*3 + ["Minestre in brodo"]`, titolo della 1 `"Brodo"`.
  - `test_riga_del_corpo_con_numero_non_e_titolo`: la ricetta 4 contiene «5. Mettete» nel testo e non esiste una ricetta 5.
  - `test_appendice_esclusa`: nessuna ricetta con «Falso titolo».
  - `test_introduzione_del_capitolo_esclusa`: le righe di introduzione di `MINESTRE` non sono nel testo di nessuna ricetta.
  - `test_pulizia`: nessun `"\r"`, nessun `"_"` di corsivo, la ricetta 1 non contiene `"\n"` dentro una frase spezzata (le righe del paragrafo sono unite), gli ingredienti della ricetta 4 sono righe proprie con la continuazione unita.
  - `test_bom_ignorato`: `carica_corpus` su un file con BOM (in `tmp_path`) e `attese=4` → 4 ricette, titolo della 1 senza `﻿`.
  - `test_verifica_buco` / `test_verifica_conteggio`: lista senza la 2 → `ErroreCorpus` con «2»; 4 ricette con `attese=790` → `ErroreCorpus` con «790».
  - `test_file_assente`: `carica_corpus(tmp_path / "no.txt")` → `ErroreCorpus` con il percorso.
  - `test_capitoli_sono_23`: `len(CAPITOLI) == 23` e `CAPITOLI[5] == "Uova"`.
  - `test_file_vero` (`skipif` se `dati/artusi.txt` manca): `carica_corpus` → 790 ricette; titoli: 7 `"Cappelletti all'uso di Romagna"`, 89 `"Gnocchi di patate"`, 208 `"Pollo alla cacciatora"`, 455 `"Cacciucco I"`, 790 `"Spezie fini"`; capitoli: 1 «Brodi, gelatina e sughi», 7 «Minestre in brodo», 89 «Minestre asciutte e di magro», 139 «Uova», 208 «Fritti», 455 «Piatti di pesce», 790 «Cose diverse»; ogni ricetta ha un capitolo in `CAPITOLI`; ogni capitolo di `CAPITOLI` ha almeno una ricetta; nessun testo contiene «Project Gutenberg».
- [ ] **Step 3:** test → FAIL. **Step 4:** implementare `rag/corpus.py`. **Step 5:** test → PASS; se un capitolo dell'elenco non risulta sul file vero, correggere l'elenco (spec: il costruttore lo conferma sul file) e annotarlo. **Step 6:** proporre il commit (es. `feat(rag): lettura e pulizia delle 790 ricette`).

### Task 3: chunking e ID stabili

**Files:**
- Create: `rag/chunking.py`, `tests/test_rag_chunking.py`

**Interfaces:**
- Consumes: `Ricetta` (Task 2).
- Produces: `@dataclass(frozen=True) Chunk(ricetta: int, titolo: str, capitolo: str, posizione: int, testo: str)` con proprietà `documento_id -> str` (`f"ricetta-{ricetta:03d}"`) e `id_punto -> str` (`str(uuid.uuid5(NAMESPACE_RAG, f"{documento_id}#{posizione}"))`, `NAMESPACE_RAG` costante UUID fissa nel modulo). `dividi_ricetta(ricetta: Ricetta, strategia: str, dimensione: int, overlap: int) -> list[Chunk]`. `dividi_tutte(ricette, strategia, dimensione, overlap) -> list[Chunk]`.

Regole (spec §20.3): `paragrafi` = ricetta intera se `len(testo) <= dimensione`; altrimenti si accumulano paragrafi (separati da `"\n\n"`) finché il chunk resta `<= dimensione`; un paragrafo più lungo di `dimensione` si spezza a finestra cercando un confine di frase (`. `) o di parola; ogni chunk dopo il primo inizia con gli ultimi ~`overlap` caratteri del precedente, presi da un confine di parola. Lunghezza massima di un chunk: `dimensione + overlap` (l'overlap si somma). `finestra` = finestre di `dimensione` caratteri che avanzano di `dimensione - overlap`, allineate a confini di parola.

- [ ] **Step 1: test che falliscono:**
  - `test_ricetta_breve_un_chunk`: ricetta di 300 caratteri → 1 chunk, `posizione == 0`, testo identico.
  - `test_ricetta_lunga_piu_chunk`: ricetta di 6 paragrafi da ~400 caratteri, `paragrafi/1200/200` → ≥ 2 chunk, posizioni `0..n-1`, ogni `len(testo) <= 1400`, ogni chunk dopo il primo inizia con testo presente alla fine del precedente (sovrapposizione ≥ 100 caratteri), l'unione copre ogni paragrafo.
  - `test_paragrafo_gigante`: un solo paragrafo di 5000 caratteri → più chunk, nessuno oltre 1400, nessuna parola spezzata a metà.
  - `test_strategia_finestra`: testo di 3000 caratteri, `finestra/1000/200` → 4 chunk, sovrapposizione presente.
  - `test_nessun_testo_di_altre_ricette`: `dividi_tutte` su due ricette → ogni chunk contiene solo testo della propria.
  - `test_id_stabili`: stesso input due volte → stessi `id_punto`; `(1,0)`, `(1,1)`, `(2,0)` → tre ID diversi; `documento_id` di 89 → `"ricetta-089"`.
  - `test_metadati_copiati`: ogni chunk ha `ricetta`, `titolo`, `capitolo` della ricetta.
- [ ] **Step 2:** FAIL. **Step 3:** implementare. **Step 4:** PASS e, se presente `dati/artusi.txt`, stampare (non testare) numero di chunk e min/medio/max per il resoconto. **Step 5:** proporre il commit (es. `feat(rag): chunking per ricetta e paragrafi con ID stabili`).

### Task 4: embedder LM Studio e embedder finto

**Files:**
- Create: `rag/embedding.py`, `tests/finti_rag.py`, `tests/test_rag_embedding.py`

**Interfaces:**
- Produces: protocollo `Embedder` con `modello: str` e `incorpora(testi: list[str]) -> list[list[float]]`. `EmbedderLMStudio(base_url: str, modello: str, lotto: int = 32, client=None)`: usa `openai.OpenAI(base_url=..., api_key="lm-studio", timeout=60, max_retries=0)` e `client.embeddings.create(model=modello, input=lotto_di_testi)`, a lotti, mantenendo l'ordine. Errori di connessione → `ErroreEmbedding(ErroreRag)` «LM Studio non raggiungibile su <url>: avvialo …»; modello sconosciuto / risposta 4xx → `ErroreEmbedding` «modello di embedding <nome> non disponibile in LM Studio (lms load …)». `tests/finti_rag.py`: `EmbedderFinto(modello="finto", dimensione=64)`: vettore = conteggio delle parole minuscole (regex `\w+`) proiettate con un hash stabile (`zlib.crc32`) su `dimensione` celle, normalizzato; deterministico; conta le chiamate in `chiamate: int` e i testi ricevuti in `testi: list[str]`.

- [ ] **Step 1: test che falliscono:**
  - `test_lotti_e_ordine`: `EmbedderLMStudio` con `client` finto (oggetto con `embeddings.create` che registra gli input e restituisce `data=[{embedding:[i]}...]`), 70 testi, `lotto=32` → 3 chiamate da 32/32/6, risultati nell'ordine dei testi, `model` uguale al modello configurato in ogni chiamata.
  - `test_connessione_rifiutata`: `client` che solleva `openai.APIConnectionError` → `ErroreEmbedding` con l'URL.
  - `test_modello_assente`: `client` che solleva `openai.NotFoundError`/`BadRequestError` → `ErroreEmbedding` con il nome del modello.
  - `test_embedder_finto`: stesso testo → stesso vettore; «gnocchi di patate» più vicino a «patate per gli gnocchi» che a «pollo fritto» (coseno).
- [ ] **Step 2:** FAIL. **Step 3:** implementare. **Step 4:** PASS. **Step 5:** proporre il commit (es. `feat(rag): embedder LM Studio a lotti`).

### Task 5: indice Qdrant e comando di ingestion

**Files:**
- Create: `rag/indice.py`, `rag/ingestion.py`, `tests/test_rag_ingestion.py`

**Interfaces:**
- Consumes: `ConfigRag`, `carica_corpus`, `dividi_tutte`, `Chunk`, `Embedder`.
- Produces (`rag/indice.py`): `crea_client(url: str) -> QdrantClient`. `prepara_collezione(client, nome: str, modello: str, dimensione: int) -> None` (crea se assente con coseno, metadati `{"modello_embedding": modello, "dimensione": dimensione}` e indici payload `capitolo` keyword e `ricetta` integer; se esiste chiama `verifica_modello`). `verifica_modello(client, nome, modello, dimensione) -> None` (collezione assente → `ErroreCollezioneAssente(ErroreRag)` «esegui prima python -m rag.ingestion»; modello o dimensione diversi → `ErroreModelloDiverso(ErroreRag)` con i due modelli e il rimedio). `conta_punti(client, nome) -> int` (esatto). Connessione rifiutata → `ErroreQdrant(ErroreRag)` «Qdrant non raggiungibile su <url>: docker compose up -d qdrant e controlla QDRANT_URL».
- Produces (`rag/ingestion.py`): `@dataclass EsitoIngestion(ricette: int, chunk: int, punti_prima: int, punti_dopo: int, rimossi: int, modello: str, dimensione: int, secondi: float, caratteri_min: int, caratteri_medi: int, caratteri_max: int)`. `esegui_ingestion(config: ConfigRag, embedder: Embedder, client) -> EsitoIngestion`. `main(argv=None) -> int` (carica config, configura log INFO su stderr con `assistente.log.configura_log`, crea embedder/client veri, stampa il riepilogo, cattura `ErroreRag` → messaggio su stderr e `return 1`); `if __name__ == "__main__": sys.exit(main())`.

Ordine in `esegui_ingestion`: corpus (`carica_corpus`, si ferma prima di qualsiasi scrittura) → chunk → embedding del primo lotto (ricava la dimensione) → `prepara_collezione` → `punti_prima` → embedding e upsert a lotti con `PointStruct(id=chunk.id_punto, vector=…, payload={"ricetta", "titolo", "capitolo", "posizione", "testo", "fonte": "Pellegrino Artusi, La scienza in cucina e l'arte di mangiar bene", "documento_id"})` → rimozione dei punti il cui ID non è tra quelli scritti (scroll degli ID + `delete`) → `punti_dopo`. Log INFO di ogni passo con i numeri di spec §20.6.

- [ ] **Step 1: test che falliscono** (embedder finto, `QdrantClient(":memory:")`, corpus = estratto del Task 2 con `attese=4` tramite parametro o monkeypatch, `dimensione=200`, `overlap=50` per avere più chunk):
  - `test_punti_uguali_ai_chunk` e `test_payload_completo` (tutte le chiavi, `fonte` non vuota, `documento_id` coerente).
  - `test_due_ingestion_stesso_numero_di_punti`: due chiamate → `punti_dopo` uguale, seconda con `punti_prima == punti_dopo`, `rimossi == 0`.
  - `test_punti_obsoleti_rimossi`: prima con `dimensione=200`, poi con `dimensione=2000` → seconda `punti_dopo == chunk` e `rimossi > 0`.
  - `test_modello_registrato` e `test_cambio_modello_bloccato`: seconda ingestion con `EmbedderFinto(modello="altro")` → `ErroreModelloDiverso` con «finto» e «altro»; punti invariati. Idem con dimensione diversa.
  - `test_indici_payload`: `get_collection(...).payload_schema` contiene `capitolo` e `ricetta` (se il modo in memoria non li riporta, verificare la chiamata con uno spy sul client).
  - `test_corpus_incompleto_nessuna_scrittura`: estratto con `attese=790` → `ErroreCorpus`, collezione non creata, embedder mai chiamato.
  - `test_main_errore_senza_traceback`: `main()` con config che punta a file assente → `1`, stderr con il messaggio e senza «Traceback» (capsys).
  - `test_qdrant_irraggiungibile`: client finto che solleva l'eccezione di connessione del client → `ErroreQdrant` (nessun accesso di rete vero).
- [ ] **Step 2:** FAIL. **Step 3:** implementare `rag/indice.py` e `rag/ingestion.py` (se al Task 1 i metadati in memoria non funzionano, usare l'alternativa annotata). **Step 4:** PASS + suite intera verde. **Step 5:** proporre il commit (es. `feat(rag): ingestion ripetibile in Qdrant con modello registrato`).

### Task 6: ricerca e comando

**Files:**
- Create: `rag/ricerca.py`, `tests/test_rag_ricerca.py`

**Interfaces:**
- Consumes: `ConfigRag`, `Embedder`, `crea_client`, `verifica_modello`, `CAPITOLI`, `esegui_ingestion` (nei test, per preparare l'indice).
- Produces: `@dataclass(frozen=True) Risultato(posizione: int, score: float, ricetta: int, titolo: str, capitolo: str, posizione_chunk: int, testo: str)`. `@dataclass(frozen=True) EsitoRicerca(risultati: list[Risultato], k: int, capitolo: str | None, nota: str | None)`. `normalizza_capitolo(nome: str) -> str` (confronto senza maiuscole/spazi esterni con `CAPITOLI`; sconosciuto → `ErroreCapitolo(ErroreRag)` con l'elenco). `cerca(domanda: str, client, embedder: Embedder, config: ConfigRag, k: int = 5, capitolo: str | None = None) -> EsitoRicerca`: domanda vuota/solo spazi → `ErroreRag`; `verifica_modello` con `embedder.modello` e la dimensione del vettore della domanda; k fuori da `1..config.k_max` → riportato nell'intervallo con `nota` («k ridotto a 10, il massimo consentito» / «k portato a 1»); filtro `models.Filter(must=[FieldCondition(key="capitolo", match=MatchValue(value=canonico))])` passato a `query_points`. `main(argv=None) -> int`: argomenti `domanda`, `--k`, `--capitolo`; stampa per ogni risultato posizione, score (3 decimali), «Ricetta N — Titolo», capitolo, chunk, testo; nota se presente; stdout in UTF-8 (`sys.stdout.reconfigure(encoding="utf-8")`); `ErroreRag` → stderr, `1`.

- [ ] **Step 1: test che falliscono** (indice preparato con `esegui_ingestion` sull'estratto, embedder finto, Qdrant in memoria):
  - `test_ordinati_per_score` e `test_k_predefinito` (≤ 5 risultati, posizioni 1..n, score non crescenti).
  - `test_k_oltre_il_massimo`: `k=50`, `k_max=10` → `esito.k == 10`, `nota` con «10».
  - `test_k_minore_di_uno`: `k=0` → `esito.k == 1`, `nota` presente.
  - `test_domanda_vuota`: `"  "` → `ErroreRag`.
  - `test_filtro_capitolo`: `capitolo="Minestre in brodo"` → tutti i risultati con quel capitolo; `test_filtro_durante_la_ricerca`: con k=1 e domanda più vicina a una ricetta di un altro capitolo, il filtro restituisce comunque 1 risultato del capitolo richiesto.
  - `test_capitolo_minuscolo`: `" minestre in brodo "` → accettato, `esito.capitolo == "Minestre in brodo"`.
  - `test_capitolo_sconosciuto`: `"Antipasti"` → `ErroreCapitolo` che contiene «Fritti» e «Uova».
  - `test_collezione_assente`: Qdrant in memoria vuoto → `ErroreCollezioneAssente`.
  - `test_deterministica`: due chiamate uguali → stessi risultati.
  - `test_main_stampa` (capsys, con `cerca` sostituita da monkeypatch): righe con «Ricetta», capitolo e score.
- [ ] **Step 2:** FAIL. **Step 3:** implementare. **Step 4:** PASS + suite verde. **Step 5:** proporre il commit (es. `feat(rag): ricerca top-k con filtro per capitolo`).

### Task 7: valutazione con fonte attesa

**Files:**
- Create: `rag/valutazione.py`, `rag/domande_valutazione.json`, `tests/test_rag_valutazione.py`

**Interfaces:**
- Consumes: `cerca`, `EsitoRicerca`, `Risultato`.
- Produces: `@dataclass(frozen=True) Domanda(testo: str, attese: tuple[int, ...], origine: str)` (`origine`: `"aula"` o `"propria"`). `carica_domande(percorso: Path) -> list[Domanda]` (JSON: lista di `{"domanda", "attese", "origine"}`; errori di formato → `ErroreRag`). `@dataclass(frozen=True) Riga(domanda: Domanda, posizione: int | None, score_fonte: float | None, score_migliore: float, prima: Risultato | None)`. `valuta(domande, cerca_fn: Callable[[str, int], EsitoRicerca], k: int) -> list[Riga]` (posizione = rango del primo risultato con `ricetta in attese`). `tabella_markdown(righe, k: int) -> str`: colonne «Domanda | Fonte attesa | Posizione | Score fonte | Score migliore | Primo risultato»; «assente» se la fonte non c'è; «nessuna (non nel libro)» per `attese` vuote; score con 3 decimali e virgola decimale; in fondo «Fonte attesa nei primi k: x su y» e «Score migliore delle domande senza risposta: …». `main(argv=None) -> int`: `--k` (predefinito 5), `--domande` (predefinito `rag/domande_valutazione.json`); stampa la tabella su stdout UTF-8.

- [ ] **Step 1:** `rag/domande_valutazione.json` con le 6 domande d'aula di spec §20.8 (`origine: "aula"`): 89, 208, [455, 456], 7, 89, [] (tiramisù).
- [ ] **Step 2: test che falliscono** (con `cerca_fn` finta che restituisce risultati preparati, nessun Qdrant):
  - `test_posizione_della_fonte`: attesa 89 al terzo posto → `posizione == 3`, `score_fonte` di quel risultato.
  - `test_fonte_assente`: → `posizione is None`, «assente» nella tabella.
  - `test_piu_ricette_attese`: attese (455, 456), 456 al secondo posto → `posizione == 2`.
  - `test_senza_risposta`: attese vuote → «nessuna (non nel libro)», conteggio x su y esclude questa domanda, score migliore riportato in fondo.
  - `test_riepilogo`: 3 domande con risposta, 2 trovate → «2 su 3».
  - `test_file_domande_aula`: `carica_domande` del file vero → 6 domande, quella sul tiramisù con `attese == ()`.
  - `test_file_malformato`: JSON senza `attese` → `ErroreRag`.
- [ ] **Step 3:** FAIL. **Step 4:** implementare. **Step 5:** PASS + suite intera verde (annotare il conteggio). **Step 6:** proporre il commit (es. `feat(rag): valutazione sulle domande con fonte attesa`).

### Task 8: prove reali, due ingestion e valutazione di partenza (controllore)

**Files:**
- Create: `docs/retrieval.md`
- Modify: `README.md` (sezione «RAG: ingestion e ricerca»: avvio di Qdrant, LM Studio con il modello di embedding, variabili, tre comandi PowerShell, diagnosi degli errori tipici della slide), `specs.md` §20 (stato «implementata», solo se tutto verificato)

- [ ] **Step 1: test a servizi spenti** (evidenza 2): con Qdrant fermo (`docker compose stop qdrant` o mai avviato) e LM Studio spento o con il server fermo (`lms server stop`), `./venv/Scripts/python.exe -m pytest -q` → tutto verde (solo skip dei reali); salvare l'output nel registro SDD. Poi riaccendere LM Studio (`lms server start`, modello di embedding caricato).
- [ ] **Step 2:** `docker compose up -d qdrant`; `docker compose ps` → in esecuzione.
- [ ] **Step 3: due ingestion complete** (evidenza 3): `python -m rag.ingestion` due volte; annotare per ciascuna ricette, chunk, punti prima/dopo, rimossi, tempo. Atteso: 790 ricette; seconda con `punti_prima == punti_dopo == chunk`, rimossi 0.
- [ ] **Step 4:** `docker compose restart qdrant`, poi ricontare i punti (stesso numero: volume persistente).
- [ ] **Step 5:** ricerca con filtro: `python -m rag.ricerca "Come si frigge il pollo?" --capitolo Fritti --k 3` → 3 risultati tutti «Fritti»; `--capitolo Antipasti` → errore con l'elenco; Qdrant fermo → messaggio senza traceback (poi riavviarlo).
- [ ] **Step 6: valutazione di partenza** (evidenza 4): `python -m rag.valutazione --k 5`; per ogni fonte trovata leggere il testo del chunk e annotare se contiene davvero l'informazione (criterio della slide). Confronto con la tabella d'aula (6 su 8, nomic, 1200/200).
- [ ] **Step 7:** `docs/retrieval.md`: configurazione (modello, chunking, k), conteggi delle due ingestion, comando e tabella di partenza, nota sul contenuto dei chunk, due query commentate (una trovata e una mancata, con la causa probabile secondo la tabella «errori tipici»). README e stato della §20.
- [ ] **Step 8:** resoconto all'utente; proporre il commit (es. `docs(rag): conteggi delle ingestion e valutazione di partenza`).

### Task 9: domande di prova senza le parole del testo (controllore + utente)

**Files:**
- Modify: `rag/domande_valutazione.json`, `docs/retrieval.md`

- [ ] **Step 1:** scegliere almeno tre ricette (diverse da quelle d'aula) e leggerne il testo in `dati/artusi.txt`; scrivere almeno **tre domande con risposta e una senza risposta nel libro**, in italiano di oggi, **senza le parole chiave del testo né del titolo** (sinonimi, parafrasi); per ciascuna la ricetta attesa e la frase del libro che contiene la risposta.
- [ ] **Step 2: PAUSA.** Mostrare all'utente domande, ricette attese e frasi del libro, con le parole evitate. **Non lanciare nessuna ricerca su queste domande prima della sua approvazione** (spec §20.8, §20.14).
- [ ] **Step 3:** dopo l'approvazione, aggiungerle al JSON con `origine: "propria"`; test `test_file_domande_aula` aggiornato in modo che conti le domande per origine (6 d'aula + le proprie); suite verde.
- [ ] **Step 4:** `python -m rag.valutazione --k 5`; aggiornare `docs/retrieval.md` (tabella completa, commento sulle proprie: trovate o no, e perché).
- [ ] **Step 5:** resoconto finale all'utente con le cinque evidenze di §20.10; proporre il commit (es. `test(rag): domande di prova parafrasate e valutazione`). Ricordare all'utente di aggiornare memoria e `handoff.md` se lo vuole.
