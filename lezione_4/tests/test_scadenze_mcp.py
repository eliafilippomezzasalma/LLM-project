"""Server MCP delle scadenze: in-process e come processo vero via stdio."""

import sys
from pathlib import Path

import anyio
import pytest
from mcp import Client, StdioServerParameters

import scadenze
from scadenze import NOMI_STRUMENTI, RIGA_NOTA, crea_server

FILE_SERVER = Path(__file__).resolve().parent.parent / "scadenze.py"


def _con_client(server, azione):
    async def principale():
        async with Client(server) as client:
            return await azione(client)

    return anyio.run(principale)


def _chiama(argomenti, nome):
    async def azione(client):
        return await client.call_tool(nome, argomenti)

    risultato = _con_client(crea_server(), azione)
    return risultato.is_error, risultato.content[0].text


def test_sei_strumenti_con_schema():
    async def azione(client):
        return (await client.list_tools()).tools

    strumenti = _con_client(crea_server(), azione)
    assert tuple(s.name for s in strumenti) == NOMI_STRUMENTI
    scadenza = next(s for s in strumenti if s.name == "compute_deadline")
    assert set(scadenza.input_schema["properties"]["unit"]["enum"]) == {
        "days", "business_days", "weeks", "months", "years",
    }
    assert {"start_date", "amount", "unit"} <= set(scadenza.input_schema["required"])
    assert all("YYYY-MM-DD" in s.description for s in strumenti)


def test_chiamata_riuscita():
    errore, testo = _chiama({"start_date": "2024-03-15", "amount": 4, "unit": "years"}, "compute_deadline")
    assert not errore
    assert testo.startswith("Scadenza: 2028-03-15 (mercoledì)")
    assert testo.endswith(RIGA_NOTA)


def test_errore_marcato():
    errore, testo = _chiama({"date": "15/03/2024"}, "date_info")
    assert errore
    assert testo.startswith("Errore: data")


def test_strumento_sconosciuto():
    assert _chiama({}, "pippo") == (True, "Errore: strumento 'pippo' non disponibile")


def test_file_festivita_rovinato_server_non_parte(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(scadenze, "FILE_FESTIVITA", tmp_path / "manca.json")
    with pytest.raises(SystemExit) as uscita:
        scadenze.main()
    assert uscita.value.code == 1
    assert "scadenze:" in capsys.readouterr().err


def test_server_vero_via_stdio():
    parametri = StdioServerParameters(command=sys.executable, args=[str(FILE_SERVER)])

    async def azione(client):
        festivita = await client.call_tool("list_holidays", {"year": 2026, "month": 12})
        fuori = await client.call_tool("date_info", {"date": "2045-01-01"})
        return festivita, fuori

    festivita, fuori = _con_client(parametri, azione)
    assert not festivita.is_error
    assert "Santo Stefano" in festivita.content[0].text
    assert "lunedì" in festivita.content[0].text or "martedì" in festivita.content[0].text
    assert fuori.is_error
