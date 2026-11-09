"""Ponte sincrono verso un server MCP via stdio (server veri, nessun modello)."""

import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool
from mcp import StdioServerParameters

from assistente.mcp_remoto import ClientMCP, ErroreMCP, parametri_calcolatrice, parametri_convertitore, parametri_scadenze

NON_RAGGIUNGIBILE = "Errore: server MCP non raggiungibile"


@pytest.fixture
def convertitore():
    client = ClientMCP.apri(parametri_convertitore())
    yield client
    client.chiudi()


def _strumento(client):
    (strumento,) = client.strumenti()
    return strumento


def test_apre_e_espone_convert_units(convertitore):
    strumento = _strumento(convertitore)
    assert strumento.name == "convert_units"
    parametri = convert_to_openai_tool(strumento)["function"]["parameters"]
    assert "°C" in parametri["properties"]["from_unit"]["enum"]


def test_invoke_passa_argomenti_intatti(convertitore):
    risposta = _strumento(convertitore).invoke({"value": 10, "from_unit": "KM", "to_unit": "miglia"})
    assert risposta == "10 km = 6.21371 mi"


def test_errore_dal_server(convertitore):
    risposta = _strumento(convertitore).invoke({"value": 5, "from_unit": "kg", "to_unit": "m"})
    assert risposta.startswith("Errore: impossibile convertire")


def test_server_che_non_parte():
    parametri = StdioServerParameters(command=sys.executable, args=["-c", "import sys; sys.exit(1)"])
    inizio = time.perf_counter()
    with pytest.raises(ErroreMCP):
        ClientMCP.apri(parametri, timeout=10)
    assert time.perf_counter() - inizio < 10


def test_server_morto_a_meta():
    file_server = Path(__file__).with_name("server_che_muore.py")
    client = ClientMCP.apri(StdioServerParameters(command=sys.executable, args=[str(file_server)]))
    try:
        inizio = time.perf_counter()
        assert client.chiama("muori", {}, timeout=5) == NON_RAGGIUNGIBILE
        assert client.chiama("muori", {}, timeout=5) == NON_RAGGIUNGIBILE
        assert time.perf_counter() - inizio < 11
    finally:
        client.chiudi()


def test_chiudi_idempotente_e_thread_finito():
    client = ClientMCP.apri(parametri_convertitore())
    client.chiudi()
    client.chiudi()
    assert not client.attivo
    assert client.chiama("convert_units", {"value": 1, "from_unit": "m", "to_unit": "m"}) == NON_RAGGIUNGIBILE


class _LoopChiuso:
    """Un event loop che si chiude proprio mentre gli si chiede qualcosa."""

    def is_closed(self):
        return False

    def call_soon_threadsafe(self, *args):
        raise RuntimeError("Event loop is closed")


def test_annulla_con_loop_appena_chiuso_non_solleva():
    client = ClientMCP(parametri_convertitore(), timeout=1)
    client._loop, client._compito = _LoopChiuso(), SimpleNamespace(cancel=lambda: None)
    client._annulla()  # non deve far uscire RuntimeError da apri()


def test_chiama_con_loop_appena_chiuso_restituisce_errore(convertitore, monkeypatch):
    def loop_chiuso(coro, loop):
        coro.close()
        raise RuntimeError("Event loop is closed")

    monkeypatch.setattr("assistente.mcp_remoto.asyncio.run_coroutine_threadsafe", loop_chiuso)
    assert convertitore.chiama("convert_units", {"value": 1, "from_unit": "m", "to_unit": "m"}) == NON_RAGGIUNGIBILE


def test_apre_e_espone_calculate():
    client = ClientMCP.apri(parametri_calcolatrice())
    try:
        (strumento,) = client.strumenti()
        assert strumento.name == "calculate"
        assert strumento.invoke({"expression": "2^10"}) == "2^10 = 1024"
        assert strumento.invoke({"expression": "10 / 0"}) == "Errore: divisione per zero"
    finally:
        client.chiudi()


def test_apre_e_espone_le_scadenze():
    client = ClientMCP.apri(parametri_scadenze())
    try:
        nomi = [s.name for s in client.strumenti()]
        assert sorted(nomi) == sorted([
            "compute_deadline", "add_business_days", "count_business_days",
            "days_between", "date_info", "list_holidays",
        ])
        strumento = next(s for s in client.strumenti() if s.name == "date_info")
        assert strumento.invoke({"date": "2027-06-02"}) == "2027-06-02 (mercoledì): festivo, Festa della Repubblica."
    finally:
        client.chiudi()
