"""Calcolatrice sicura: server MCP con un solo strumento, `calculate`.

Avvio isolato: python calcolatrice.py  (parla MCP su stdin/stdout)

Il testo dell'espressione non viene mai passato a Python per essere eseguito: lo legge
un piccolo analizzatore con una grammatica fissa, e i calcoli usano numeri esatti.

Il file è diviso in sezioni:
1. limiti e simboli accettati;
2. lettura dei pezzi (numeri, operatori, parentesi) con posizioni;
3. analisi (discesa ricorsiva, un metodo per regola) e calcolo con controllo dei limiti;
4. formato del risultato e messaggi in italiano;
5. server MCP: strato sottile che espone lo schema e chiama la sezione 4.
"""

import math
from dataclasses import dataclass
from fractions import Fraction

import anyio
import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

# ── 1. Limiti e simboli ─────────────────────────────────────────────────────────

LUNGHEZZA_MASSIMA = 200
PROFONDITA_MASSIMA = 30
LIMITE_GRANDE = Fraction(10) ** 100
LIMITE_PICCOLO = Fraction(1, 10**100)
# Potenza intera esatta solo se numeratore e denominatore del risultato restano sotto
# questo numero di bit: una base vicinissima a 1 produrrebbe milioni di cifre.
BIT_MASSIMI_POTENZA_ESATTA = 10_000

_OPERATORI = "+-*/^"
_SINONIMI = {"×": "*", "÷": "/"}  # "**" è trattato a parte: occupa due caratteri
_CARATTERI_NUMERO = "0123456789,."

MESSAGGIO_ARGOMENTO = "serve un'espressione scritta come testo, per esempio '(3,5 + 2) * 4'"


class ErroreCalcolo(Exception):
    """Rifiuto dell'espressione: str(errore) è il messaggio in italiano, senza «Errore: »."""


# ── 2. Lettura dei pezzi ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Pezzo:
    tipo: str  # "numero", un operatore, "(", ")" oppure "fine"
    testo: str
    posizione: int  # 1-based sull'espressione originale
    valore: Fraction | None = None


def _numero_valido(testo: str) -> bool:
    """Solo cifre, con al più un separatore che abbia cifre da entrambi i lati."""
    parti = testo.replace(",", ".").split(".")
    return len(parti) <= 2 and all(p != "" and p.isascii() and p.isdigit() for p in parti)


def _leggi_numero(espressione: str, inizio: int) -> tuple[_Pezzo, int]:
    """Legge la sequenza massima di cifre e separatori, poi la valida."""
    fine = inizio
    while fine < len(espressione) and espressione[fine] in _CARATTERI_NUMERO:
        fine += 1
    testo = espressione[inizio:fine]
    if not _numero_valido(testo):
        raise ErroreCalcolo(f"numero scritto male '{testo}' in posizione {inizio + 1}")
    return _Pezzo("numero", testo, inizio + 1, Fraction(testo.replace(",", "."))), fine


def _leggi(espressione: str) -> list[_Pezzo]:
    pezzi: list[_Pezzo] = []
    i = 0
    while i < len(espressione):
        c = espressione[i]
        if c.isspace():
            i += 1
        elif c in _CARATTERI_NUMERO:
            pezzo, i = _leggi_numero(espressione, i)
            pezzi.append(pezzo)
        elif espressione.startswith("**", i):
            pezzi.append(_Pezzo("^", "**", i + 1))
            i += 2
        elif c in _SINONIMI:
            pezzi.append(_Pezzo(_SINONIMI[c], c, i + 1))
            i += 1
        elif c in _OPERATORI or c in "()":
            pezzi.append(_Pezzo(c, c, i + 1))
            i += 1
        else:
            raise ErroreCalcolo(
                f"carattere non consentito '{c}' in posizione {i + 1}: "
                "sono ammessi numeri, + - * / ^ e parentesi"
            )
    return pezzi


# ── 3. Analisi e calcolo ────────────────────────────────────────────────────────

Numero = Fraction | float


def _nei_limiti(x: Numero) -> bool:
    return x == 0 or LIMITE_PICCOLO <= abs(x) <= LIMITE_GRANDE


def _controlla(x: Numero) -> Numero:
    """Ogni operazione passa di qui: fuori dai limiti il risultato è rifiutato."""
    if _nei_limiti(x):
        return x
    if abs(x) > LIMITE_GRANDE:
        raise ErroreCalcolo("risultato troppo grande (oltre 10^100)")
    raise ErroreCalcolo("risultato troppo piccolo (sotto 10^-100)")


def _e_intero(x: Numero) -> bool:
    return x.denominator == 1 if isinstance(x, Fraction) else x.is_integer()


def _potenza(base: Numero, esponente: Numero) -> Numero:
    if base == 0:
        if esponente == 0:
            raise ErroreCalcolo("0^0 è una forma indeterminata")
        if esponente < 0:
            raise ErroreCalcolo("divisione per zero")
        return Fraction(0)
    intero = _e_intero(esponente)
    if base == 1:
        return Fraction(1)
    if base == -1 and intero:  # il segno dipende solo dalla parità dell'esponente esatto
        return Fraction(-1 if int(esponente) % 2 else 1)
    # Logaritmo naturale di |base|. Vicino a 1 la conversione a float perderebbe la
    # differenza da 1: la sottrazione tra Fraction è esatta, log1p la mantiene precisa.
    modulo = abs(base)
    if Fraction(1, 2) <= modulo <= 2:
        ln = math.log1p(float(modulo - 1))
    else:
        ln = math.log(modulo)
    # Stima prima di calcolare: evita potenze con milioni di cifre.
    stima = float(esponente) * ln
    if stima > 100 * math.log(10):
        raise ErroreCalcolo("risultato troppo grande (oltre 10^100)")
    if stima < -100 * math.log(10):
        raise ErroreCalcolo("risultato troppo piccolo (sotto 10^-100)")
    if not intero and base < 0:
        raise ErroreCalcolo("potenza con base negativa ed esponente non intero non supportata")
    if intero and isinstance(base, Fraction):
        bit = base.numerator.bit_length() + base.denominator.bit_length()
        if bit * abs(int(esponente)) <= BIT_MASSIMI_POTENZA_ESATTA:
            return _controlla(base ** int(esponente))
    segno = -1 if base < 0 and int(esponente) % 2 else 1  # solo se l'esponente è intero
    return _controlla(segno * math.exp(stima))


class _Analizzatore:
    """espressione := termine (("+"|"-") termine)*
    termine     := unario (("*"|"/") unario)*
    unario      := ("+"|"-") unario | potenza
    potenza     := primario ("^" unario)?
    primario    := numero | "(" espressione ")"
    """

    def __init__(self, espressione: str) -> None:
        self._pezzi = _leggi(espressione)
        self._indice = 0
        self._fine = _Pezzo("fine", "", len(espressione) + 1)
        self._profondita = 0

    def _corrente(self) -> _Pezzo:
        return self._pezzi[self._indice] if self._indice < len(self._pezzi) else self._fine

    def _avanza(self) -> None:
        self._indice += 1

    def _manca_operatore(self, pezzo: _Pezzo) -> ErroreCalcolo:
        return ErroreCalcolo(
            f"manca un operatore prima di '{pezzo.testo}' in posizione {pezzo.posizione}"
        )

    def analizza(self) -> Numero:
        valore = self._espressione()
        resto = self._corrente()
        if resto.tipo == ")":
            raise ErroreCalcolo(f"parentesi chiusa in posizione {resto.posizione} senza apertura")
        if resto.tipo != "fine":
            raise self._manca_operatore(resto)
        return valore

    def _espressione(self) -> Numero:
        valore = self._termine()
        while self._corrente().tipo in ("+", "-"):
            segno = self._corrente().tipo
            self._avanza()
            altro = self._termine()
            valore = _controlla(valore + altro if segno == "+" else valore - altro)
        return valore

    def _termine(self) -> Numero:
        valore = self._unario()
        while self._corrente().tipo in ("*", "/"):
            operatore = self._corrente().tipo
            self._avanza()
            altro = self._unario()
            if operatore == "*":
                valore = _controlla(valore * altro)
            elif altro == 0:
                raise ErroreCalcolo("divisione per zero")
            else:
                valore = _controlla(valore / altro)
        return valore

    def _unario(self) -> Numero:
        negativo = False
        while self._corrente().tipo in ("+", "-"):  # ciclo, non ricorsione: "-" * 150 + "2"
            if self._corrente().tipo == "-":
                negativo = not negativo
            self._avanza()
        valore = self._potenza()
        return -valore if negativo else valore

    def _potenza(self) -> Numero:
        base = self._primario()
        if self._corrente().tipo != "^":
            return base
        self._avanza()
        return _potenza(base, self._unario())

    def _primario(self) -> Numero:
        pezzo = self._corrente()
        if pezzo.tipo == "numero":
            self._avanza()
            assert pezzo.valore is not None  # i pezzi "numero" hanno sempre un valore
            return _controlla(pezzo.valore)
        if pezzo.tipo != "(":
            raise ErroreCalcolo(f"manca un numero in posizione {pezzo.posizione}")
        self._profondita += 1
        if self._profondita > PROFONDITA_MASSIMA:
            raise ErroreCalcolo(
                f"troppe parentesi annidate (massimo {PROFONDITA_MASSIMA} livelli)"
            )
        self._avanza()
        valore = self._espressione()
        chiusura = self._corrente()
        if chiusura.tipo == "fine":
            raise ErroreCalcolo(f"parentesi aperta in posizione {pezzo.posizione} non chiusa")
        if chiusura.tipo != ")":
            raise self._manca_operatore(chiusura)
        self._avanza()
        self._profondita -= 1
        return valore


def calcola(espressione: str) -> Numero:
    """Calcola l'espressione; ogni rifiuto è un ErroreCalcolo."""
    if len(espressione) > LUNGHEZZA_MASSIMA:
        raise ErroreCalcolo(f"espressione troppo lunga (massimo {LUNGHEZZA_MASSIMA} caratteri)")
    if not espressione.strip():
        raise ErroreCalcolo("espressione vuota")
    return _Analizzatore(espressione).analizza()


# ── 4. Formato e messaggi ───────────────────────────────────────────────────────


def formatta_numero(valore: Numero) -> str:
    if isinstance(valore, Fraction) and valore.denominator == 1 and abs(valore) < 10**15:
        return str(valore.numerator)
    testo = format(float(valore), ".10g")
    return "0" if testo == "-0" else testo


def esegui_calcolo(argomenti: dict) -> tuple[str, bool]:
    """Calcola e formatta; restituisce (testo, è_errore)."""
    espressione = argomenti.get("expression")
    if not isinstance(espressione, str):
        return f"Errore: {MESSAGGIO_ARGOMENTO}", True
    try:
        risultato = calcola(espressione)
    except ErroreCalcolo as errore:
        return f"Errore: {errore}", True
    return f"{espressione.strip()} = {formatta_numero(risultato)}", False


# ── 5. Server MCP ───────────────────────────────────────────────────────────────
# Strato sottile, come in convertitore.py: nessuna logica di calcolo, solo schema e
# instradamento verso esegui_calcolo (che valida gli argomenti e scrive gli errori).

NOME_STRUMENTO = "calculate"
DESCRIZIONE = (
    "Calculates an arithmetic expression given as text. Allowed operations: + - * / ^ "
    "and parentheses; decimals with a comma or a point. No functions and no variables. "
    "Send every calculation to this tool, even ones that look impossible (for example "
    "a division by zero), and report its result or its error message."
)
SCHEMA = {
    "type": "object",
    "properties": {
        "expression": {
            "type": "string",
            "description": "Arithmetic expression, e.g. '(3,5 + 2) * 4' or '2^10'",
        }
    },
    "required": ["expression"],
}


def _testo(testo: str, errore: bool) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=testo)], is_error=errore)


async def _elenca_strumenti(contesto, parametri) -> types.ListToolsResult:
    strumento = types.Tool(name=NOME_STRUMENTO, description=DESCRIZIONE, input_schema=SCHEMA)
    return types.ListToolsResult(tools=[strumento])


async def _chiama_strumento(contesto, parametri: types.CallToolRequestParams) -> types.CallToolResult:
    if parametri.name != NOME_STRUMENTO:
        return _testo(f"Errore: strumento '{parametri.name}' non disponibile", True)
    return _testo(*esegui_calcolo(parametri.arguments or {}))


def crea_server() -> Server:
    """Server MCP con il solo strumento calculate."""
    return Server("calcolatrice", on_list_tools=_elenca_strumenti, on_call_tool=_chiama_strumento)


def main() -> None:
    """Esegue il server su stdin/stdout finché il client non chiude la connessione."""
    server = crea_server()

    async def principale() -> None:
        async with stdio_server() as (lettura, scrittura):
            await server.run(lettura, scrittura, server.create_initialization_options())

    anyio.run(principale)


if __name__ == "__main__":
    main()
