import logging
import re

from assistente.log import configura_log


def test_formato_riga(capsys):
    configura_log("INFO")
    logging.getLogger("strumenti").info("ciao")
    err = capsys.readouterr().err
    assert re.fullmatch(r"\d\d:\d\d:\d\d INFO strumenti: ciao\n", err)


def test_log_non_va_su_stdout(capsys):
    configura_log("INFO")
    logging.getLogger("strumenti").info("ciao")
    assert capsys.readouterr().out == ""


def test_librerie_esterne_a_warning(capsys):
    configura_log("DEBUG")
    for nome in ("httpx", "openai", "langchain", "langchain_core", "langchain_openai", "langgraph"):
        logging.getLogger(nome).info("rumore")
    assert capsys.readouterr().err == ""


def test_debug_abilitato(capsys):
    configura_log("DEBUG")
    logging.getLogger("modello").debug("dettaglio")
    assert "DEBUG modello: dettaglio" in capsys.readouterr().err


def test_info_nasconde_debug(capsys):
    configura_log("INFO")
    logging.getLogger("modello").debug("dettaglio")
    assert capsys.readouterr().err == ""


def test_httpx2_e_httpcore_a_warning(capsys):
    # openai 3.x usa i pacchetti httpx2 e httpcore2: il primo scrive a INFO a ogni richiesta,
    # i trasporti a DEBUG a ogni connessione.
    configura_log("DEBUG")
    logging.getLogger("httpx2").info('HTTP Request: POST .../chat/completions "HTTP/1.1 200 OK"')
    for nome in ("httpcore", "httpcore2.connection", "httpcore2.http11"):
        logging.getLogger(nome).debug("connessione")
    assert capsys.readouterr().err == ""
