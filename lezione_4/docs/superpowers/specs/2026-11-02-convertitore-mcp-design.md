# Convertitore di unità come server MCP — documento di progetto

Data: 2026-11-02 · Progetto: `lezione_4/` · Branch: `feature/nuove-funzionalita`

## Intento

Prima di una serie di funzionalità aggiuntive, da fare una alla volta. Testo del compito:

> Convertitore di unità. Unità ammesse come elenco chiuso; errore per conversioni
> incompatibili. Allena schemi e validazione.

Si aggiunge all'assistente della lezione 4 (LangGraph + LM Studio + orologio) un **server MCP
separato e circoscritto** che offre **un solo strumento**: il convertitore di unità.
L'assistente si collega a quel server e mette il convertitore a disposizione del modello
accanto all'orologio (che resta uno strumento interno, invariato).

Il valore didattico sta in due cose, che vanno rese ben visibili nel codice:
1. **lo schema**: come lo strumento descrive al modello i propri argomenti (unità ammesse come
   elenco chiuso, visibile nello schema JSON dello strumento);
2. **la validazione**: come il server rifiuta le richieste sbagliate con messaggi chiari,
   comprensibili sia dal modello sia da chi legge i log.

## Comportamento atteso (dall'utente)

- «converti 10 km in miglia» → l'assistente chiama lo strumento e risponde con il risultato
  (circa 6,21 mi).
- «converti 5 kg in metri» → lo strumento restituisce un errore (massa e lunghezza non sono
  compatibili) e l'assistente lo spiega all'utente, senza inventare un numero.

## Unità ammesse (elenco chiuso, scelto dall'utente: opzione «D»)

| Grandezza   | Unità (simboli usati nello schema) |
|-------------|-------------------------------------|
| Lunghezza   | mm, cm, m, km, in, ft, mi           |
| Massa       | g, kg, lb, oz                       |
| Tempo       | s, min, h                           |
| Temperatura | °C, °F, K                           |
| Volume      | ml, l, gal                          |
| Velocità    | m/s, km/h, mph                      |

Sono 23 unità in 6 grandezze. Nessun'altra unità è ammessa.

*Scelte mie (approvate in sintesi dall'utente, da confermare nella lettura):*
- `gal` è il **gallone USA** (3,785411784 l); va scritto nella descrizione dello strumento.
- Gli argomenti usano i **simboli** della tabella; è il modello a tradurre «miglia» in `mi`,
  «gradi Fahrenheit» in `°F`, ecc. (lo schema elenca i simboli ammessi).
- Fattori di conversione esatti dove definiti (in = 0,0254 m, ft = 0,3048 m,
  mi = 1609,344 m, lb = 0,45359237 kg, oz = lb/16).

## Dove sta la validazione (deciso dall'utente: opzione «b»)

**La validazione la fa lo schema**, non un controllo scritto a mano a parte. Gli argomenti
dello strumento sono descritti da un modello Pydantic sul server: l'elenco chiuso delle unità
è un tipo enumerato (`Literal`/enum) che compare nello schema JSON esposto al modello, e le
altre regole (compatibilità delle grandezze, zero assoluto, valore finito) sono validatori
dello stesso modello. Così lo schema è insieme la descrizione per il modello e il controllo
vero. I messaggi di errore però vanno **personalizzati in italiano** (il messaggio generico
in inglese della libreria non basta): il modello deve ricevere un testo chiaro, che per
un'unità sbagliata elenca le unità ammesse.

Conseguenza sul lato assistente: l'adattatore **non deve rivalidare né rifiutare** gli
argomenti prima di mandarli al server (altrimenti un sinonimo o un'unità sbagliata non
arriverebbero mai allo schema del server e l'errore sarebbe quello generico di
`strumenti.py`). Il controllo avviene in un solo posto: lo schema del server.

## Sinonimi delle unità (deciso dall'utente: «con varianti»)

L'elenco chiuso resta quello della tabella, ma lo schema accetta anche **una tabella fissa
di sinonimi**, normalizzati al simbolo canonico prima del controllo sull'elenco (per esempio
con un validatore Pydantic «before»): maiuscole/minuscole (`KM` → `km`, `L` → `l`),
`C`/`celsius` → `°C`, `F`/`fahrenheit` → `°F`, `kph` → `km/h`, `miglia`/`miles` → `mi`, ecc.
Anche la tabella dei sinonimi è chiusa e coperta dai test: tutto ciò che non è né un simbolo
né un sinonimo resta un errore. Nello schema JSON l'elenco enumerato mostra i simboli
canonici; la descrizione dell'argomento può accennare che sono accettate alcune varianti.
Il contenuto preciso della tabella dei sinonimi è lasciato al costruttore (pochi sinonimi
ovvi, in italiano e in inglese; attenzione alle ambiguità: `m` resta metri, `min` minuti).

## Regole di validazione

Ogni regola produce un errore con messaggio chiaro in italiano; nessuna fa cadere il server
né la chat.

1. **Unità fuori elenco** (es. «anni luce», «stone»), dopo la normalizzazione dei sinonimi:
   errore che elenca le unità ammesse.
2. **Grandezze incompatibili** (es. kg → m): errore che nomina le due grandezze
   («massa» e «lunghezza») e dice che non sono convertibili tra loro.
3. **Valore non numerico o non finito** (testo, NaN, infinito): errore.
4. **Temperatura sotto lo zero assoluto** (sotto 0 K, −273,15 °C, −459,67 °F): errore.
5. *Scelta mia:* valori negativi ammessi per tutte le altre grandezze (servono per esempio
   per una differenza di tempo o una velocità in verso opposto; non c'è motivo di rifiutarli).
6. Conversione verso la stessa unità (km → km): ammessa, restituisce il valore invariato.

La temperatura non è un semplice fattore moltiplicativo: serve anche uno scostamento
(°F = °C × 9/5 + 32). Tutte le altre grandezze sono solo fattori.

## Risultato restituito al modello

*Scelta mia:* un testo breve e leggibile, ad esempio `10 km = 6.2137 mi`, con il valore
arrotondato a un numero ragionevole di cifre significative (il formato preciso è lasciato al
costruttore, purché coerente e verificato dai test). Gli errori seguono la convenzione già
usata dall'orologio: testo che inizia con `Errore:` oppure, se il meccanismo MCP lo prevede,
un risultato marcato come errore; in entrambi i casi il modello deve ricevere il messaggio
e il log deve registrarlo come avviso (`WARNING`), come già avviene per gli strumenti interni.

## Come si costruisce (scelte tecniche: lasciate a me dall'utente)

- **Server**: libreria ufficiale `mcp` (Python SDK, versione da fissare in
  `requirements.txt`), un modulo/pacchetto dentro `lezione_4/` avviabile da solo
  (per esempio `python -m convertitore`), che espone **un solo strumento**.
- **Trasporto**: `stdio`. L'assistente avvia il server come processo figlio e ci parla via
  standard input/output. Niente porte di rete, niente servizi in più in Docker Compose: il
  server gira nello stesso container dell'assistente (il `Dockerfile` deve copiarne il codice).
- **Logica separata dal protocollo**: la conversione e lo schema di validazione (modello
  Pydantic) stanno in codice Python puro, testabile senza MCP; il server MCP è uno strato
  sottile sopra.
- **Lato assistente**: il resto del programma resta **sincrono** (scelta della lezione 4).
  Il client MCP è asincrono, quindi serve un piccolo adattatore che apre la sessione MCP
  all'avvio, la tiene aperta per tutta la chat, la chiude all'uscita, e presenta lo strumento
  remoto al grafo come un normale strumento LangChain (`BaseTool`) nel registro esistente.
  Come realizzare l'adattatore (`langchain-mcp-adapters` oppure un piccolo ponte scritto a
  mano sul client `mcp`) è lasciato al costruttore: criterio di scelta, meno dipendenze e
  codice più semplice da spiegare a lezione. Ogni dipendenza nuova va motivata e fissata.
- **Grafo, registro e esecuzione delle chiamate** (`grafo.py`, `strumenti.py`) non devono
  cambiare struttura: lo strumento remoto entra nella stessa lista dell'orologio.
- **Prompt di sistema** (`sessione.py`): va esteso per dire al modello di usare il
  convertitore per le conversioni di unità e di non calcolarle a mente.
- *Scelta mia:* se il server MCP non si avvia, l'assistente **parte comunque** con il solo
  orologio e lo segnala con un avviso nel log e una riga nell'intestazione della chat.
- *Scelta mia:* se il server MCP si interrompe durante la chat, **nessun riavvio automatico**:
  le chiamate successive al convertitore restituiscono un `Errore:` (la chat non cade) e il
  problema finisce nel log; per ripristinarlo si riavvia l'assistente.

## Test e verifiche

Stessa impostazione della lezione 4:
- test automatici senza modello attivo: logica di conversione (tutte le grandezze, inclusa
  la temperatura), ogni regola di validazione, sinonimi, schema dello strumento (l'elenco
  chiuso compare davvero nello schema JSON esposto), e almeno un test che avvia il server
  MCP vero via stdio e chiama lo strumento (conversione riuscita, conversione incompatibile,
  unità fuori elenco con il messaggio italiano, sinonimo accettato);
- prova reale con LM Studio, separata e attivata esplicitamente (come `test_reale.py`):
  «converti 10 km in miglia» e «converti 5 kg in metri»;
- prova Docker: il convertitore funziona anche dentro il container.

## Obiettivi

- Server MCP separato, un solo strumento, unità come elenco chiuso nello schema.
- Errori chiari per unità sconosciute e grandezze incompatibili (e gli altri casi sopra).
- L'assistente usa il convertitore tramite MCP nella chat, anche con Docker.

## Non-obiettivi

- Altre funzionalità o altri strumenti nel server (arriveranno una alla volta, dopo).
- Spostare l'orologio sul server MCP.
- Unità composte o libere («kg/m³»), prefissi arbitrari, conversione di valute.
- Trasporto HTTP, autenticazione, uso del server da client esterni (Claude Desktop ecc.):
  non vietato dal disegno, ma non richiesto né verificato.

## Anti-obiettivi (sarebbe un fallimento anche se «funziona»)

- Il modello che fa le conversioni a mente o inventa un numero per kg → m.
- Un'unità fuori elenco accettata in silenzio.
- Un errore dello strumento o del server che fa cadere la chat.
- Logica di conversione mescolata al codice del protocollo, difficile da mostrare a lezione.

## Vincoli di lavoro

- Si lavora solo in `lezione_4/`, sul branch `feature/nuove-funzionalita`.
- **Commit e push solo su richiesta esplicita dell'utente.**
- `CLAUDE.md` e `README.md` vanno aggiornati: oggi `CLAUDE.md` dice di non anticipare MCP e
  di non creare branch; con questa funzionalità quelle regole cambiano.
- Specifica e piano in `lezione_4/docs/superpowers/`.
- Comandi documentati per PowerShell.

## Lasciato al costruttore

- Struttura precisa dei moduli del server e nome del comando di avvio.
- Adattatore sincrono per il client MCP (vedi sopra).
- Formato numerico esatto del risultato e numero di cifre.
- Nomi esatti dello strumento e degli argomenti (purché chiari in inglese per il modello,
  come `get_current_time`, ad esempio `convert_units` con `value`, `from_unit`, `to_unit`).
