"""Convertitore di unità: server MCP con un solo strumento, `convert_units`.

Avvio isolato: python convertitore.py  (parla MCP su stdin/stdout)

Il file è diviso in sezioni:
1. unità ammesse (elenco chiuso) e fattori di conversione;
2. sinonimi accettati, ricondotti al simbolo ufficiale;
3. schema degli argomenti (modello Pydantic): descrive lo strumento al modello
   e fa tutta la validazione;
4. conversione e messaggi in italiano;
5. server MCP: strato sottile che espone lo schema e chiama la sezione 4.
"""

import math
from typing import Literal

import anyio
import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from pydantic_core import ErrorDetails

# ── 1. Unità ammesse ────────────────────────────────────────────────────────────
# Per ogni unità: grandezza e fattore verso l'unità base della grandezza
# (m, kg, s, l, m/s). La temperatura non è un semplice fattore: vedi _a_kelvin.

_POLLICE = 0.0254
_PIEDE = 0.3048
_MIGLIO = 1609.344
_LIBBRA = 0.45359237
_GALLONE_USA = 3.785411784

_TABELLA: dict[str, tuple[str, float | None]] = {
    "mm": ("lunghezza", 0.001),
    "cm": ("lunghezza", 0.01),
    "m": ("lunghezza", 1.0),
    "km": ("lunghezza", 1000.0),
    "in": ("lunghezza", _POLLICE),
    "ft": ("lunghezza", _PIEDE),
    "mi": ("lunghezza", _MIGLIO),
    "g": ("massa", 0.001),
    "kg": ("massa", 1.0),
    "lb": ("massa", _LIBBRA),
    "oz": ("massa", _LIBBRA / 16),
    "s": ("tempo", 1.0),
    "min": ("tempo", 60.0),
    "h": ("tempo", 3600.0),
    "°C": ("temperatura", None),
    "°F": ("temperatura", None),
    "K": ("temperatura", None),
    "ml": ("volume", 0.001),
    "l": ("volume", 1.0),
    "gal": ("volume", _GALLONE_USA),
    "m/s": ("velocità", 1.0),
    "km/h": ("velocità", 1000.0 / 3600.0),
    "mph": ("velocità", _MIGLIO / 3600.0),
}

UNITA: tuple[str, ...] = tuple(_TABELLA)
GRANDEZZE: dict[str, str] = {simbolo: grandezza for simbolo, (grandezza, _) in _TABELLA.items()}
_FATTORI: dict[str, float] = {s: f for s, (_, f) in _TABELLA.items() if f is not None}

Unita = Literal[
    "mm", "cm", "m", "km", "in", "ft", "mi",
    "g", "kg", "lb", "oz",
    "s", "min", "h",
    "°C", "°F", "K",
    "ml", "l", "gal",
    "m/s", "km/h", "mph",
]

# Limite inferiore della temperatura, espresso nell'unità di partenza.
ZERO_ASSOLUTO = {"K": 0.0, "°C": -273.15, "°F": -459.67}

# ── 2. Sinonimi ─────────────────────────────────────────────────────────────────
# Anche questa tabella è chiusa: ciò che non è un simbolo né un sinonimo è un errore.

_SINONIMI_PER_SIMBOLO = {
    "m": ("metri", "metro", "meter", "meters"),
    "mm": ("millimetri", "millimetro"),
    "cm": ("centimetri", "centimetro"),
    "km": ("chilometri", "chilometro", "kilometri", "kilometer", "kilometers"),
    "in": ("pollici", "pollice", "inch", "inches"),
    "ft": ("piedi", "piede", "foot", "feet"),
    "mi": ("miglia", "miglio", "mile", "miles"),
    "g": ("grammi", "grammo", "gram", "grams"),
    "kg": ("chilogrammi", "chilogrammo", "chili", "kilo", "kilogram", "kilograms"),
    "lb": ("libbre", "libbra", "pound", "pounds", "lbs"),
    "oz": ("once", "oncia", "ounce", "ounces"),
    "s": ("secondi", "secondo", "sec", "second", "seconds"),
    "min": ("minuti", "minuto", "minute", "minutes"),
    "h": ("ore", "ora", "hour", "hours"),
    "°C": ("c", "celsius", "gradi celsius"),
    "°F": ("f", "fahrenheit", "gradi fahrenheit"),
    "K": ("kelvin",),
    "ml": ("millilitri", "millilitro"),
    "l": ("litri", "litro", "liter", "liters", "litre", "litres"),
    "gal": ("galloni", "gallone", "gallon", "gallons"),
    "m/s": ("mps", "metri al secondo"),
    "km/h": ("kmh", "kph", "chilometri orari", "chilometri all'ora"),
    "mph": ("miglia orarie", "miles per hour"),
}
SINONIMI: dict[str, str] = {
    sinonimo: simbolo for simbolo, elenco in _SINONIMI_PER_SIMBOLO.items() for sinonimo in elenco
}
_SIMBOLI_MINUSCOLI = {simbolo.lower(): simbolo for simbolo in UNITA}

MESSAGGIO_NUMERO = "il valore deve essere un numero finito"


def normalizza_unita(testo: object) -> str:
    """Riconduce un simbolo o un sinonimo al simbolo ufficiale; altrimenti ValueError."""
    if isinstance(testo, str):
        pulito = testo.strip()
        if pulito in _TABELLA:
            return pulito
        minuscolo = pulito.lower()
        simbolo = _SIMBOLI_MINUSCOLI.get(minuscolo) or SINONIMI.get(minuscolo)
        if simbolo:
            return simbolo
    raise ValueError(f"unità '{testo}' non ammessa. Unità ammesse: {', '.join(UNITA)}")


# ── 3. Schema degli argomenti ───────────────────────────────────────────────────


class RichiestaConversione(BaseModel):
    """Argomenti di convert_units: lo schema JSON di questo modello è quello visto dal modello."""

    value: float = Field(allow_inf_nan=False, description="Valore numerico da convertire")
    from_unit: Unita = Field(description="Unità di partenza (simbolo dell'elenco)")
    to_unit: Unita = Field(description="Unità di arrivo (simbolo dell'elenco)")

    @field_validator("value", mode="before")
    @classmethod
    def _niente_booleani(cls, valore: object) -> object:
        # In modalità lax Pydantic trasformerebbe True in 1.0.
        if isinstance(valore, bool):
            raise ValueError(MESSAGGIO_NUMERO)
        return valore

    @field_validator("from_unit", "to_unit", mode="before")
    @classmethod
    def _normalizza(cls, valore: object) -> str:
        return normalizza_unita(valore)

    @model_validator(mode="after")
    def _controlla_coerenza(self) -> "RichiestaConversione":
        da, a = GRANDEZZE[self.from_unit], GRANDEZZE[self.to_unit]
        if da != a:
            raise ValueError(
                f"impossibile convertire '{self.from_unit}' ({da}) in '{self.to_unit}' ({a}): "
                "grandezze diverse"
            )
        limite = ZERO_ASSOLUTO.get(self.from_unit)
        if limite is not None and self.value < limite:
            raise ValueError(
                f"{self.value:g} {self.from_unit} è sotto lo zero assoluto "
                f"({limite:g} {self.from_unit})"
            )
        return self


# ── 4. Conversione e messaggi ───────────────────────────────────────────────────


def _a_kelvin(valore: float, unita: str) -> float:
    if unita == "°C":
        return valore + 273.15
    if unita == "°F":
        return (valore - 32) * 5 / 9 + 273.15
    return valore


def _da_kelvin(kelvin: float, unita: str) -> float:
    if unita == "°C":
        return kelvin - 273.15
    if unita == "°F":
        return (kelvin - 273.15) * 9 / 5 + 32
    return kelvin


def converti(richiesta: RichiestaConversione) -> float:
    """Converte una richiesta già validata."""
    da, a = richiesta.from_unit, richiesta.to_unit
    if da == a:
        return richiesta.value
    if GRANDEZZE[da] == "temperatura":
        return _da_kelvin(_a_kelvin(richiesta.value, da), a)
    return richiesta.value * _FATTORI[da] / _FATTORI[a]


def formatta_risultato(richiesta: RichiestaConversione, risultato: float) -> str:
    return f"{richiesta.value:g} {richiesta.from_unit} = {risultato:.6g} {richiesta.to_unit}"


def _messaggio(dettaglio: ErrorDetails) -> str:
    luogo = ".".join(str(parte) for parte in dettaglio["loc"])
    if dettaglio["type"] == "missing":
        return f"argomento '{luogo}' mancante"
    if dettaglio["type"] == "value_error":
        return str(dettaglio.get("ctx", {}).get("error"))
    if luogo == "value":
        return MESSAGGIO_NUMERO
    return f"argomento '{luogo}' non valido"


def messaggio_errore(errore: ValidationError) -> str:
    """Traduce gli errori di validazione in un unico testo italiano per il modello."""
    return "Errore: " + "; ".join(_messaggio(dettaglio) for dettaglio in errore.errors())


def esegui_conversione(argomenti: dict) -> tuple[str, bool]:
    """Valida, converte e formatta; restituisce (testo, è_errore)."""
    try:
        richiesta = RichiestaConversione.model_validate(argomenti)
    except ValidationError as errore:
        return messaggio_errore(errore), True
    risultato = converti(richiesta)
    if not math.isfinite(risultato):
        return f"Errore: {MESSAGGIO_NUMERO}", True
    return formatta_risultato(richiesta, risultato), False


# ── 5. Server MCP ───────────────────────────────────────────────────────────────
# Si usa il Server «di basso livello» della libreria mcp: lo schema esposto è proprio
# RichiestaConversione.model_json_schema() e la validazione resta in esegui_conversione,
# con i messaggi in italiano (MCPServer risponderebbe con errori generici in inglese).

NOME_STRUMENTO = "convert_units"
DESCRIZIONE = (
    "Converte un valore tra unità di misura della stessa grandezza "
    "(lunghezza, massa, tempo, temperatura, volume, velocità). "
    "Usa i simboli dell'elenco ammesso; sono accettate anche alcune varianti comuni "
    "(per esempio 'miglia', 'celsius', 'kph'). 'gal' è il gallone USA (3,785 l). "
    "È lo strumento a controllare che le due unità siano compatibili: chiamalo per ogni richiesta "
    "di conversione e riporta il suo risultato o il suo messaggio di errore."
)


def _testo(testo: str, errore: bool) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=testo)], is_error=errore)


async def _elenca_strumenti(contesto, parametri) -> types.ListToolsResult:
    strumento = types.Tool(
        name=NOME_STRUMENTO,
        description=DESCRIZIONE,
        input_schema=RichiestaConversione.model_json_schema(),
    )
    return types.ListToolsResult(tools=[strumento])


async def _chiama_strumento(contesto, parametri: types.CallToolRequestParams) -> types.CallToolResult:
    if parametri.name != NOME_STRUMENTO:
        return _testo(f"Errore: strumento '{parametri.name}' non disponibile", True)
    return _testo(*esegui_conversione(parametri.arguments or {}))


def crea_server() -> Server:
    """Server MCP con il solo strumento convert_units."""
    return Server("convertitore", on_list_tools=_elenca_strumenti, on_call_tool=_chiama_strumento)


def main() -> None:
    """Esegue il server su stdin/stdout finché il client non chiude la connessione."""
    server = crea_server()

    async def principale() -> None:
        async with stdio_server() as (lettura, scrittura):
            await server.run(lettura, scrittura, server.create_initialization_options())

    anyio.run(principale)


if __name__ == "__main__":
    main()
