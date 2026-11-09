import io
import sys
from types import SimpleNamespace

import httpx
import openai
import pytest

from assistente import terminale
from assistente.config import ErroreConfigurazione
from assistente.sessione import LimitePassaggiRaggiunto
from assistente.terminale import esegui_chat

URL = "http://localhost:1234/v1"


class SessioneFinta:
    """Per ogni domanda restituisce (o solleva) l'elemento successivo della lista."""

    def __init__(self, esiti):
        self.esiti = list(esiti)
        self.domande = []

    def chiedi(self, domanda):
        self.domande.append(domanda)
        esito = self.esiti.pop(0)
        if isinstance(esito, BaseException):
            raise esito
        return esito


def _chat(righe, sessione=None):
    """Esegue la chat con un input preparato; restituisce le righe scritte."""
    sessione = sessione or SessioneFinta([])
    ingressi = iter(righe)
    scritte = []

    def leggi(prompt):
        assert prompt == "Tu> "
        valore = next(ingressi)
        if isinstance(valore, BaseException):
            raise valore
        return valore

    esegui_chat(sessione, "Intestazione", URL, leggi=leggi, scrivi=scritte.append)
    return scritte


def test_intestazione_e_aiuto():
    scritte = _chat(["esci"])
    assert scritte[0] == "Intestazione"
    assert "esci" in scritte[1] and "Ctrl+C" in scritte[1]


def test_esci_saluta():
    assert _chat(["esci"])[-1].strip() == "Ciao!"


def test_exit_maiuscolo():
    assert _chat(["  EXIT  "])[-1].strip() == "Ciao!"


def test_eof_saluta():
    assert _chat([EOFError()])[-1].strip() == "Ciao!"


def test_ctrl_c_saluta_senza_traceback():
    assert _chat([KeyboardInterrupt()])[-1].strip() == "Ciao!"


def test_ctrl_c_durante_attesa_modello():
    sessione = SessioneFinta([KeyboardInterrupt()])
    assert _chat(["Che ore sono?"], sessione)[-1].strip() == "Ciao!"


def test_riga_vuota_ignorata():
    sessione = SessioneFinta(["Ciao!"])
    _chat(["", "   ", "Ciao", "esci"], sessione)
    assert sessione.domande == ["Ciao"]


def test_stampa_sto_pensando_e_risposta():
    scritte = _chat(["Ciao", "esci"], SessioneFinta(["Ciao Elia!"]))
    assert scritte[2:4] == ["(sto pensando...)", "Assistente> Ciao Elia!"]


def test_limite_mostra_avviso_e_continua():
    sessione = SessioneFinta([LimitePassaggiRaggiunto(), "Ok"])
    scritte = _chat(["Che ore sono?", "Riprovo", "esci"], sessione)
    assert any("Limite di passaggi raggiunto" in r for r in scritte)
    assert "Assistente> Ok" in scritte


def test_errore_connessione_e_continua():
    errore = openai.APIConnectionError(request=httpx.Request("POST", URL))
    sessione = SessioneFinta([errore, "Eccomi"])
    scritte = _chat(["Ciao", "Ci sei?", "esci"], sessione)
    assert any(r.startswith(f"Impossibile contattare il modello su {URL}") for r in scritte)
    assert "Assistente> Eccomi" in scritte


def _config_mancante():
    raise ErroreConfigurazione("Variabile d'ambiente mancante: LM_MODEL")


def test_main_config_mancante_esce_con_1(monkeypatch, capsys):
    monkeypatch.setattr(terminale, "carica_config", _config_mancante)
    assert terminale.main() == 1
    assert "LM_MODEL" in capsys.readouterr().err


@pytest.mark.parametrize("comando", ["esci", "exit", "Esci"])
def test_comandi_di_uscita(comando):
    assert _chat([comando])[-1].strip() == "Ciao!"


def test_main_scrive_in_utf8(monkeypatch):
    # Su Windows, con output rediretto, Python userebbe cp1252 e «—» o «lunedì» si rovinerebbero.
    for nome in ("stdout", "stderr"):
        monkeypatch.setattr(sys, nome, io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))
    monkeypatch.setattr(terminale, "carica_config", _config_mancante)
    terminale.main()
    assert sys.stdout.encoding == "utf-8"
    assert sys.stderr.encoding == "utf-8"


def test_errore_imprevisto_del_modello_non_chiude_la_chat():
    # Es. LM_BASE_URL senza /v1: LM Studio risponde 200 con un errore e langchain solleva ValueError.
    scritte = _chat(["Ciao", "Ciao", "esci"], SessioneFinta([ValueError("risposta non valida"), "Ciao!"]))
    assert f"Impossibile contattare il modello su {URL}: risposta non valida" in scritte
    assert "Assistente> Ciao!" in scritte
    assert scritte[-1].strip() == "Ciao!"


def test_errore_http_del_modello_non_parla_di_connessione():
    # Es. cronologia oltre il contesto del modello: il server risponde, ma con un errore.
    risposta = httpx.Response(400, request=httpx.Request("POST", URL))
    errore = openai.BadRequestError("contesto troppo lungo", response=risposta, body=None)
    scritte = _chat(["Ciao", "esci"], SessioneFinta([errore]))
    assert "Errore dal modello (HTTP 400): contesto troppo lungo" in scritte
    assert not any(s.startswith("Impossibile contattare") for s in scritte)


def test_collega_convertitore_fallito(caplog):
    from mcp import StdioServerParameters

    parametri = StdioServerParameters(command=sys.executable, args=["-c", "import sys; sys.exit(1)"])
    with caplog.at_level("WARNING"):
        assert terminale.collega_convertitore(parametri) is None
    assert "convertitore MCP non disponibile" in caplog.text


def test_collega_convertitore_riuscito():
    remoto = terminale.collega_convertitore()
    try:
        assert [s.name for s in remoto.strumenti()] == ["convert_units"]
    finally:
        remoto.chiudi()


def test_collega_calcolatrice_fallito(caplog):
    from mcp import StdioServerParameters

    parametri = StdioServerParameters(command=sys.executable, args=["-c", "import sys; sys.exit(1)"])
    with caplog.at_level("WARNING"):
        assert terminale.collega_calcolatrice(parametri) is None
    assert "calcolatrice MCP non disponibile" in caplog.text


def test_collega_calcolatrice_riuscita():
    remoto = terminale.collega_calcolatrice()
    try:
        assert [s.name for s in remoto.strumenti()] == ["calculate"]
    finally:
        remoto.chiudi()


def test_collega_scadenze_fallito(caplog):
    from mcp import StdioServerParameters

    parametri = StdioServerParameters(command=sys.executable, args=["-c", "import sys; sys.exit(1)"])
    with caplog.at_level("WARNING"):
        assert terminale.collega_scadenze(parametri) is None
    assert "scadenze MCP non disponibile" in caplog.text


def test_collega_scadenze_riuscito():
    remoto = terminale.collega_scadenze()
    try:
        assert "compute_deadline" in [s.name for s in remoto.strumenti()]
    finally:
        remoto.chiudi()


def test_intestazione_server_mcp():
    config = SimpleNamespace(lm_model="m", lm_base_url=URL)
    testo = terminale.intestazione(config, True, False, True)
    assert "Convertitore di unità (MCP): attivo" in testo
    assert "Calcolatrice (MCP): non disponibile" in testo
    assert "Giorni e scadenze (MCP): attivo" in testo
    altro = terminale.intestazione(config, False, True, False)
    assert "Convertitore di unità (MCP): non disponibile" in altro
    assert "Calcolatrice (MCP): attivo" in altro
    assert "Giorni e scadenze (MCP): non disponibile" in altro


class RemotoFinto:
    def __init__(self, *strumenti):
        self._strumenti = list(strumenti)
        self.chiuso = False

    def strumenti(self):
        return self._strumenti

    def chiudi(self):
        self.chiuso = True


def _prepara_main(monkeypatch, convertitore, calcolatrice, scadenze):
    visto = {}

    def chat(sessione, intestazione, indirizzo, **_):
        visto["intestazione"] = intestazione
        visto["sessione"] = sessione

    config = SimpleNamespace(lm_model="m", lm_base_url=URL, log_level="WARNING", max_tool_steps=3)
    monkeypatch.setattr(terminale, "carica_config", lambda: config)
    monkeypatch.setattr(terminale, "configura_log", lambda livello: None)
    monkeypatch.setattr(terminale, "crea_modello",
                        lambda config, strumenti: visto.update(strumenti=strumenti) or object())
    monkeypatch.setattr(terminale, "costruisci_grafo", lambda *a, **k: object())
    monkeypatch.setattr(terminale, "esegui_chat", chat)
    monkeypatch.setattr(terminale, "collega_convertitore", lambda: convertitore)
    monkeypatch.setattr(terminale, "collega_calcolatrice", lambda: calcolatrice)
    monkeypatch.setattr(terminale, "collega_scadenze", lambda: scadenze)
    return visto


def test_main_server_indipendenti_e_chiusi(monkeypatch):
    sentinella = SimpleNamespace(name="calculate")
    calc, scad = RemotoFinto(sentinella), RemotoFinto()
    visto = _prepara_main(monkeypatch, None, calc, scad)
    assert terminale.main() == 0
    assert "Convertitore di unità (MCP): non disponibile" in visto["intestazione"]
    assert "Calcolatrice (MCP): attivo" in visto["intestazione"]
    assert "Giorni e scadenze (MCP): attivo" in visto["intestazione"]
    assert calc.chiuso and scad.chiuso
    assert sentinella in visto["strumenti"]


def test_main_avvolge_compute_deadline(monkeypatch):
    from langchain_core.tools import StructuredTool

    originale = StructuredTool.from_function(
        lambda giorni: "Scadenza: 2026-01-02.", name="compute_deadline", description="finto"
    )
    scad = RemotoFinto(originale)
    visto = _prepara_main(monkeypatch, None, None, scad)
    assert terminale.main() == 0
    (passato,) = [s for s in visto["strumenti"] if s.name == "compute_deadline"]
    assert passato is not originale
    assert visto["sessione"].nota is not None
    assert scad.chiuso
