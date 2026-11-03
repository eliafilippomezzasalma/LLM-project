"""Server MCP della calcolatrice: in-process e come processo vero via stdio."""

import sys
from pathlib import Path

import anyio
from mcp import Client, StdioServerParameters

from calcolatrice import crea_server

FILE_SERVER = Path(__file__).resolve().parent.parent / "calcolatrice.py"


def _con_client(server, azione):
    async def principale():
        async with Client(server) as client:
            return await azione(client)

    return anyio.run(principale)


def _chiama(argomenti, nome="calculate"):
    async def azione(client):
        return await client.call_tool(nome, argomenti)

    risultato = _con_client(crea_server(), azione)
    return risultato.is_error, risultato.content[0].text


def test_un_solo_strumento_con_schema():
    async def azione(client):
        return (await client.list_tools()).tools

    strumenti = _con_client(crea_server(), azione)
    assert [s.name for s in strumenti] == ["calculate"]
    assert strumenti[0].input_schema["properties"]["expression"]["type"] == "string"
    assert "expression" in strumenti[0].input_schema["required"]


def test_chiamata_riuscita():
    assert _chiama({"expression": "(3,5 + 2) * 4"}) == (False, "(3,5 + 2) * 4 = 22")


def test_divisione_per_zero():
    assert _chiama({"expression": "10 / 0"}) == (True, "Errore: divisione per zero")


def test_argomento_mancante():
    errore, testo = _chiama({})
    assert errore
    assert testo.startswith("Errore: serve un'espressione")


def test_strumento_sconosciuto():
    errore, testo = _chiama({}, nome="pippo")
    assert errore
    assert testo == "Errore: strumento 'pippo' non disponibile"


def test_server_vero_via_stdio():
    parametri = StdioServerParameters(command=sys.executable, args=[str(FILE_SERVER)])

    async def azione(client):
        ok = await client.call_tool("calculate", {"expression": "6 × 7"})
        zero = await client.call_tool("calculate", {"expression": "10 / 0"})
        return ok, zero

    ok, zero = _con_client(parametri, azione)
    assert (ok.is_error, ok.content[0].text) == (False, "6 × 7 = 42")
    assert zero.is_error
