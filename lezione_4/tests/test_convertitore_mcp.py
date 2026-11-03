"""Server MCP del convertitore: in-process e come processo vero via stdio."""

import sys
from pathlib import Path

import anyio
from mcp import Client, StdioServerParameters

from convertitore import UNITA, crea_server

FILE_SERVER = Path(__file__).resolve().parent.parent / "convertitore.py"


def _con_client(server, azione):
    async def principale():
        async with Client(server) as client:
            return await azione(client)

    return anyio.run(principale)


def _chiama(argomenti, nome="convert_units"):
    async def azione(client):
        return await client.call_tool(nome, argomenti)

    risultato = _con_client(crea_server(), azione)
    return risultato.is_error, risultato.content[0].text


def test_un_solo_strumento_con_schema():
    async def azione(client):
        return (await client.list_tools()).tools

    strumenti = _con_client(crea_server(), azione)
    assert [s.name for s in strumenti] == ["convert_units"]
    assert strumenti[0].input_schema["properties"]["to_unit"]["enum"] == list(UNITA)
    assert "gallone USA" in strumenti[0].description


def test_chiamata_riuscita():
    assert _chiama({"value": 10, "from_unit": "km", "to_unit": "mi"}) == (False, "10 km = 6.21371 mi")


def test_chiamata_incompatibile():
    assert _chiama({"value": 5, "from_unit": "kg", "to_unit": "m"}) == (
        True,
        "Errore: impossibile convertire 'kg' (massa) in 'm' (lunghezza): grandezze diverse",
    )


def test_unita_fuori_elenco_messaggio_italiano():
    errore, testo = _chiama({"value": 1, "from_unit": "anni luce", "to_unit": "km"})
    assert errore
    assert testo.startswith("Errore: unità 'anni luce' non ammessa")


def test_sinonimo_accettato():
    assert _chiama({"value": 10, "from_unit": "KM", "to_unit": "miglia"}) == (False, "10 km = 6.21371 mi")


def test_strumento_sconosciuto():
    errore, testo = _chiama({}, nome="pippo")
    assert errore
    assert testo == "Errore: strumento 'pippo' non disponibile"


def test_server_vero_via_stdio():
    parametri = StdioServerParameters(command=sys.executable, args=[str(FILE_SERVER)])

    async def azione(client):
        caldo = await client.call_tool("convert_units", {"value": 100, "from_unit": "°C", "to_unit": "°F"})
        sbagliato = await client.call_tool("convert_units", {"value": 5, "from_unit": "kg", "to_unit": "m"})
        return caldo, sbagliato

    caldo, sbagliato = _con_client(parametri, azione)
    assert (caldo.is_error, caldo.content[0].text) == (False, "100 °C = 212 °F")
    assert sbagliato.is_error
