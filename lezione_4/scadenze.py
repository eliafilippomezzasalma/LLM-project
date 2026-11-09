"""Scadenze e date: server MCP per calcoli su date, giorni lavorativi e scadenze.

Avvio isolato: python scadenze.py  (parla MCP su stdin/stdout)

Le date coprono dal 2020-01-01 al 2040-12-31. Le festività nazionali italiane non sono
calcolate dal programma: si leggono solo da `festivita.json`.

Il file è diviso in sezioni:
1. intervallo coperto e nomi di giorni e mesi;
2. festività: lettura e controllo di `festivita.json`;
3. calendario: lettura delle date, giorni lavorativi e calcoli;
4. richieste e messaggi in italiano;
5. server MCP: strato sottile che espone lo schema e chiama la sezione 4.
"""

import calendar
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

import anyio
import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from pydantic import BaseModel, Field, StrictInt, ValidationError, field_validator
from pydantic_core import ErrorDetails

# ── 1. Intervallo e nomi ────────────────────────────────────────────────────────

PRIMA_DATA = date(2020, 1, 1)
ULTIMA_DATA = date(2040, 12, 31)

# L'indice è quello di `date.weekday()`: lunedì = 0.
GIORNI_SETTIMANA = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
MESI = (
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)

# ── 2. Festività ────────────────────────────────────────────────────────────────

FILE_FESTIVITA = Path(__file__).resolve().parent / "festivita.json"

_FORMA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ANNO_PRIMO_SAN_FRANCESCO = 2026  # dal 2026 il 4 ottobre è festa nazionale


class ErroreFestivita(Exception):
    """File delle festività mancante, non valido o incoerente (messaggio in italiano)."""


def _festivita_attese(anno: int) -> int:
    return 11 if anno < _ANNO_PRIMO_SAN_FRANCESCO else 12


def carica_festivita(percorso: Path = FILE_FESTIVITA) -> dict[date, str]:
    """Legge il file delle festività e restituisce data -> nome, dopo averlo controllato."""
    try:
        contenuto = json.loads(Path(percorso).read_text(encoding="utf-8"))
    except OSError:
        raise ErroreFestivita(f"file delle festività non trovato o illeggibile: {percorso}") from None
    except ValueError:
        raise ErroreFestivita(f"il file delle festività non è un JSON valido: {percorso}") from None

    anni_attesi = {str(a) for a in range(PRIMA_DATA.year, ULTIMA_DATA.year + 1)}
    if not isinstance(contenuto, dict) or set(contenuto) != anni_attesi:
        raise ErroreFestivita(
            f"il file delle festività deve avere esattamente gli anni "
            f"{PRIMA_DATA.year}-{ULTIMA_DATA.year}"
        )

    festivita: dict[date, str] = {}
    for chiave, voci in contenuto.items():
        anno = int(chiave)
        if not isinstance(voci, list):
            raise ErroreFestivita(f"anno {anno}: serve un elenco di festività")
        for voce in voci:
            if not isinstance(voce, dict):
                raise ErroreFestivita(f"anno {anno}: ogni festività deve essere un oggetto")
            testo, nome = voce.get("data"), voce.get("nome")
            if not isinstance(testo, str) or not _FORMA_ISO.match(testo):
                raise ErroreFestivita(f"anno {anno}: data non valida: {testo!r}")
            try:
                giorno = date.fromisoformat(testo)
            except ValueError:
                raise ErroreFestivita(f"anno {anno}: data inesistente: {testo}") from None
            if giorno.year != anno:
                raise ErroreFestivita(f"anno {anno}: la data {testo} è di un altro anno")
            if not isinstance(nome, str) or not nome.strip():
                raise ErroreFestivita(f"anno {anno}: nome mancante per la data {testo}")
            if giorno in festivita:
                raise ErroreFestivita(f"data ripetuta: {testo}")
            festivita[giorno] = nome.strip()
        if len(voci) != _festivita_attese(anno):
            raise ErroreFestivita(
                f"anno {anno}: servono {_festivita_attese(anno)} festività, ce ne sono {len(voci)}"
            )
    return festivita

# ── 3. Calendario ───────────────────────────────────────────────────────────────

MESSAGGIO_INTERVALLO = "posso calcolare solo date tra il 2020-01-01 e il 2040-12-31"
_UNITA_GIORNI = {"days": 1, "weeks": 7}
_UNITA_MESI = {"months": 1, "years": 12}


class ErroreDate(Exception):
    """Data non valida o fuori intervallo: il messaggio in italiano è `str(errore)`."""


def controlla_intervallo(d: date) -> date:
    """Restituisce `d` se sta nell'intervallo coperto, altrimenti solleva `ErroreDate`."""
    if not PRIMA_DATA <= d <= ULTIMA_DATA:
        raise ErroreDate(
            f"data {d.isoformat()} fuori dall'intervallo coperto: {MESSAGGIO_INTERVALLO}"
        )
    return d


def aggiungi_mesi(d: date, mesi: int) -> date:
    """Somma `mesi` (anche negativi); se il giorno non esiste prende l'ultimo del mese."""
    indice = d.year * 12 + (d.month - 1) + mesi
    anno, mese = divmod(indice, 12)
    mese += 1
    giorno = min(d.day, calendar.monthrange(anno, mese)[1])
    return date(anno, mese, giorno)


class Calendario:
    """Giorni lavorativi (non sabato, domenica o festività) e calcoli sulle date."""

    def __init__(self, festivita: dict[date, str]):
        self._festivita = festivita

    def festivita(self, d: date) -> str | None:
        """Nome della festività di `d`, o `None`."""
        return self._festivita.get(d)

    def lavorativo(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self._festivita

    def motivo(self, d: date) -> str | None:
        """Perché `d` non è lavorativo (la festività ha la precedenza); `None` se lo è."""
        nome = self._festivita.get(d)
        if nome is not None:
            return f"è festiva ({nome})"
        if d.weekday() >= 5:
            return f"cade di {GIORNI_SETTIMANA[d.weekday()]}"
        return None

    def sposta(self, d: date, avanti: bool) -> date:
        """Primo giorno lavorativo da `d` compreso, in avanti o all'indietro."""
        passo = timedelta(days=1 if avanti else -1)
        controlla_intervallo(d)
        while not self.lavorativo(d):
            d = controlla_intervallo(d + passo)
        return d

    def aggiungi(self, d: date, quantita: int, unita: str, avanti: bool) -> date:
        """Somma (o sottrae) `quantita` `unita` a `d`, senza spostare il risultato."""
        n = quantita if avanti else -quantita
        if unita in _UNITA_GIORNI:
            risultato = d + timedelta(days=n * _UNITA_GIORNI[unita])
        elif unita in _UNITA_MESI:
            risultato = aggiungi_mesi(d, n * _UNITA_MESI[unita])
        elif unita == "business_days":
            risultato = self.aggiungi_lavorativi(d, quantita, avanti)
        else:
            raise ValueError(f"unità non prevista: {unita}")
        return controlla_intervallo(risultato)

    def aggiungi_lavorativi(self, d: date, n: int, avanti: bool) -> date:
        """Avanza (o arretra) di `n` giorni lavorativi, partenza esclusa."""
        passo = timedelta(days=1 if avanti else -1)
        while n > 0:
            d = controlla_intervallo(d + passo)
            if self.lavorativo(d):
                n -= 1
        return d

    def conta_lavorativi(self, inizio: date, fine: date) -> int:
        """Giorni lavorativi tra `inizio` e `fine`, estremi compresi (`inizio <= fine`)."""
        totale = 0
        d = inizio
        while d <= fine:
            totale += self.lavorativo(d)
            d += timedelta(days=1)
        return totale

    def festivita_di(self, anno: int, mese: int | None) -> list[tuple[date, str]]:
        """Festività di un anno (o di un solo mese), in ordine di data."""
        return sorted(
            (g, nome)
            for g, nome in self._festivita.items()
            if g.year == anno and (mese is None or g.month == mese)
        )


# ── 4. Richieste, formato e messaggi ────────────────────────────────────────────

FRASE_NOTA = "calcolo indicativo, non ha valore legale."
RIGA_NOTA = f"Nota: {FRASE_NOTA}"

NOMI_STRUMENTI = (
    "compute_deadline", "add_business_days", "count_business_days",
    "days_between", "date_info", "list_holidays",
)

_MSG_FORMATO = "data '{}' non valida: usa il formato AAAA-MM-GG, es. 2024-03-15"
_MSG_QUANTITA = "la quantità deve essere un numero intero da 1 in su"
_MSG_UNITA = "unità non valida: usa days, business_days, weeks, months o years"
_MSG_DIREZIONE = "direzione non valida: usa forward o backward"
_MSG_ANNO = f"anno non valido: {MESSAGGIO_INTERVALLO}"
_MSG_MESE = "mese non valido: usa un numero da 1 a 12"
_MSG_CALCOLO = f"la data calcolata è fuori dall'intervallo coperto: {MESSAGGIO_INTERVALLO}"

# Messaggio italiano per i campi che non sono date: vale per qualunque errore di quel campo.
_MESSAGGI_CAMPO = {
    "amount": _MSG_QUANTITA,
    "days": _MSG_QUANTITA,
    "unit": _MSG_UNITA,
    "direction": _MSG_DIREZIONE,
    "year": _MSG_ANNO,
    "month": _MSG_MESE,
}

# (singolare, plurale) di ogni unità
_NOMI_UNITA = {
    "days": ("giorno", "giorni"),
    "business_days": ("giorno lavorativo", "giorni lavorativi"),
    "weeks": ("settimana", "settimane"),
    "months": ("mese", "mesi"),
    "years": ("anno", "anni"),
}


def leggi_data(valore: object) -> date:
    """Legge una data ISO `AAAA-MM-GG` intera (spazi esterni ammessi) dentro l'intervallo."""
    testo = valore.strip() if isinstance(valore, str) else None
    if testo is None or not _FORMA_ISO.match(testo):
        raise ErroreDate(_MSG_FORMATO.format(valore))
    try:
        giorno = date.fromisoformat(testo)
    except ValueError:
        raise ErroreDate(f"la data '{valore}' non esiste") from None
    return controlla_intervallo(giorno)


def formatta_data(d: date) -> str:
    return f"{d.isoformat()} ({GIORNI_SETTIMANA[d.weekday()]})"


def _data_ammessa(valore: object) -> str:
    """Validatore dei campi data: controlla e restituisce la data in forma ISO."""
    try:
        return leggi_data(valore).isoformat()
    except ErroreDate as errore:
        raise ValueError(str(errore)) from None


_Direzione = Literal["forward", "backward"]
_DESC_DATA = "Date in ISO format YYYY-MM-DD, e.g. 2024-03-15"
_DESC_DIREZIONE = "'forward' goes after the start date, 'backward' goes before it"


class RichiestaScadenza(BaseModel):
    start_date: str = Field(description=_DESC_DATA)
    amount: StrictInt = Field(ge=1, description="Whole number of units, 1 or more")
    unit: Literal["days", "business_days", "weeks", "months", "years"] = Field(
        description="Unit of time: days, business_days, weeks, months or years"
    )
    direction: _Direzione = Field(default="forward", description=_DESC_DIREZIONE)

    _controlla = field_validator("start_date", mode="before")(_data_ammessa)


class RichiestaLavorativi(BaseModel):
    start_date: str = Field(description=_DESC_DATA)
    days: StrictInt = Field(ge=1, description="Whole number of business days, 1 or more")
    direction: _Direzione = Field(default="forward", description=_DESC_DIREZIONE)

    _controlla = field_validator("start_date", mode="before")(_data_ammessa)


class RichiestaConteggio(BaseModel):
    start_date: str = Field(description=_DESC_DATA)
    end_date: str = Field(description="Last date of the count, included. " + _DESC_DATA)

    _controlla = field_validator("start_date", "end_date", mode="before")(_data_ammessa)


class RichiestaDifferenza(BaseModel):
    from_date: str = Field(description=_DESC_DATA)
    to_date: str = Field(description=_DESC_DATA)

    _controlla = field_validator("from_date", "to_date", mode="before")(_data_ammessa)


class RichiestaInfo(BaseModel):
    date: str = Field(description=_DESC_DATA)

    _controlla = field_validator("date", mode="before")(_data_ammessa)


class RichiestaFestivita(BaseModel):
    year: StrictInt = Field(
        ge=PRIMA_DATA.year, le=ULTIMA_DATA.year,
        description="Year from 2020 to 2040, e.g. 2026",
    )
    month: StrictInt | None = Field(
        default=None, ge=1, le=12,
        description="Month number from 1 to 12; leave out for the whole year",
    )


_MODELLI = {
    "compute_deadline": RichiestaScadenza,
    "add_business_days": RichiestaLavorativi,
    "count_business_days": RichiestaConteggio,
    "days_between": RichiestaDifferenza,
    "date_info": RichiestaInfo,
    "list_holidays": RichiestaFestivita,
}


def _messaggio(dettaglio: ErrorDetails) -> str:
    campo = str(dettaglio["loc"][0]) if dettaglio["loc"] else "argomenti"
    if dettaglio["type"] == "missing":
        return f"argomento '{campo}' mancante"
    if dettaglio["type"] == "value_error":
        return str(dettaglio.get("ctx", {}).get("error"))
    return _MESSAGGI_CAMPO.get(campo, f"argomento '{campo}' non valido")


def messaggio_errore(errore: ValidationError) -> str:
    """Traduce gli errori di validazione in un unico testo italiano per il modello."""
    return "Errore: " + "; ".join(_messaggio(dettaglio) for dettaglio in errore.errors())


def _quantita(n: int, unita: str) -> str:
    singolare, plurale = _NOMI_UNITA[unita]
    return f"{n} {singolare if n == 1 else plurale}"


def _scadenza(cal: Calendario, r: RichiestaScadenza) -> str:
    inizio = date.fromisoformat(r.start_date)
    avanti = r.direction == "forward"
    calcolata = cal.aggiungi(inizio, r.amount, r.unit, avanti)
    finale = cal.sposta(calcolata, avanti)
    testo = (
        f"Scadenza: {formatta_data(finale)}, {_quantita(r.amount, r.unit)} "
        f"{'dopo il' if avanti else 'prima del'} {r.start_date}."
    )
    if finale != calcolata:
        testo += (
            f" La data calcolata {formatta_data(calcolata)} {cal.motivo(calcolata)}: "
            f"spostata al giorno lavorativo {'successivo' if avanti else 'precedente'}."
        )
    return f"{testo}\n{RIGA_NOTA}"


def _lavorativi(cal: Calendario, r: RichiestaLavorativi) -> str:
    avanti = r.direction == "forward"
    risultato = cal.aggiungi_lavorativi(date.fromisoformat(r.start_date), r.days, avanti)
    return (
        f"{_quantita(r.days, 'business_days')} {'dopo il' if avanti else 'prima del'} "
        f"{r.start_date}: {formatta_data(risultato)}."
    )


def _conteggio(cal: Calendario, r: RichiestaConteggio) -> str:
    inizio, fine = date.fromisoformat(r.start_date), date.fromisoformat(r.end_date)
    if fine < inizio:
        raise ErroreDate(
            f"la data finale {fine.isoformat()} viene prima di quella iniziale {inizio.isoformat()}"
        )
    n = cal.conta_lavorativi(inizio, fine)
    return f"Dal {r.start_date} al {r.end_date}: {_quantita(n, 'business_days')}."


def _differenza(cal: Calendario, r: RichiestaDifferenza) -> str:
    da, a = date.fromisoformat(r.from_date), date.fromisoformat(r.to_date)
    n = (a - da).days
    if n == 0:
        return f"Le due date coincidono: {formatta_data(da)}."
    posizione = "dopo il" if n > 0 else "prima del"
    return f"Il {r.to_date} viene {_quantita(abs(n), 'days')} {posizione} {r.from_date}."


def _info(cal: Calendario, r: RichiestaInfo) -> str:
    d = date.fromisoformat(r.date)
    nome = cal.festivita(d)
    if nome is not None:
        return f"{formatta_data(d)}: festivo, {nome}."
    if d.weekday() >= 5:
        return f"{formatta_data(d)}: non lavorativo, {GIORNI_SETTIMANA[d.weekday()]}."
    return f"{formatta_data(d)}: giorno lavorativo."


def _festivita(cal: Calendario, r: RichiestaFestivita) -> str:
    voci = cal.festivita_di(r.year, r.month)
    if r.month is not None and not voci:
        return f"Nessuna festività nazionale a {MESI[r.month - 1]} {r.year}."
    titolo = f"Festività di {MESI[r.month - 1]} {r.year}:" if r.month else f"Festività del {r.year}:"
    return titolo + "".join(f"\n- {formatta_data(g)} {nome}" for g, nome in voci)


_ESECUTORI = {
    "compute_deadline": _scadenza,
    "add_business_days": _lavorativi,
    "count_business_days": _conteggio,
    "days_between": _differenza,
    "date_info": _info,
    "list_holidays": _festivita,
}


def esegui_strumento(calendario: Calendario, nome: str, argomenti: dict) -> tuple[str, bool]:
    """Valida, calcola e formatta; restituisce (testo, è_errore). Non solleva mai."""
    if nome not in NOMI_STRUMENTI:
        return f"Errore: strumento '{nome}' non disponibile", True
    try:
        richiesta = _MODELLI[nome].model_validate(argomenti)
    except ValidationError as errore:
        return messaggio_errore(errore), True
    try:
        return _ESECUTORI[nome](calendario, richiesta), False
    except ErroreDate as errore:
        return f"Errore: {errore}", True
    except (OverflowError, ValueError):
        # quantità enormi: l'aritmetica sulle date esce dal range prima del nostro controllo
        return f"Errore: {_MSG_CALCOLO}", True


# ── 5. Server MCP ───────────────────────────────────────────────────────────────
# Strato sottile, come in calcolatrice.py: nessuna logica di date, solo schema e
# instradamento verso esegui_strumento (che valida gli argomenti e scrive gli errori).

_PROMEMORIA = " Dates only in ISO format YYYY-MM-DD; covered years 2020-2040."
DESCRIZIONI = {
    "compute_deadline": (
        "Computes a deadline or term from a start date plus a duration (days, business days, "
        "weeks, months, years), forward or backward (backward for notice periods). A deadline "
        "that falls on a weekend or an Italian national holiday is moved to the next (forward) "
        "or previous (backward) business day, and the result says why. Use it for every "
        "deadline or term, also in business days."
    ),
    "add_business_days": (
        "Gives the date that comes N business days after or before a date, when the question "
        "is not about a deadline."
    ),
    "count_business_days": "Counts the business days between two dates, both included.",
    "days_between": (
        "Counts the calendar days between a reference date (usually today, from "
        "get_current_time) and another date."
    ),
    "date_info": "Gives the weekday of a date and whether it is a business day or an Italian national holiday.",
    "list_holidays": "Lists the Italian national holidays of a year, or of one month.",
}


def _testo(testo: str, errore: bool) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=testo)], is_error=errore)


def crea_server(festivita: dict[date, str] | None = None) -> Server:
    """Server MCP con i sei strumenti; `None` legge le festività da `festivita.json`."""
    calendario = Calendario(carica_festivita(FILE_FESTIVITA) if festivita is None else festivita)

    async def elenca_strumenti(contesto, parametri) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=nome,
                    description=DESCRIZIONI[nome] + _PROMEMORIA,
                    input_schema=_MODELLI[nome].model_json_schema(),
                )
                for nome in NOMI_STRUMENTI
            ]
        )

    async def chiama_strumento(contesto, parametri: types.CallToolRequestParams) -> types.CallToolResult:
        return _testo(*esegui_strumento(calendario, parametri.name, parametri.arguments or {}))

    return Server("scadenze", on_list_tools=elenca_strumenti, on_call_tool=chiama_strumento)


def main() -> None:
    """Esegue il server su stdin/stdout; senza festività valide non parte."""
    try:
        server = crea_server()
    except ErroreFestivita as errore:
        print(f"scadenze: {errore}", file=sys.stderr)
        sys.exit(1)

    async def principale() -> None:
        async with stdio_server() as (lettura, scrittura):
            await server.run(lettura, scrittura, server.create_initialization_options())

    anyio.run(principale)


if __name__ == "__main__":
    main()
