"""Interfaccia da terminale: legge le domande, stampa le risposte, gestisce uscita ed errori."""

import logging
import sys
from collections.abc import Callable

import openai

from assistente.config import ErroreConfigurazione, carica_config
from assistente.grafo import costruisci_grafo
from assistente.log import configura_log
from assistente.modello import crea_modello
from assistente.orologio import crea_orologio
from assistente.sessione import LimitePassaggiRaggiunto, Sessione
from assistente.strumenti import crea_registro

log = logging.getLogger("sessione")

AIUTO = "Scrivi la tua domanda. Per uscire: esci, exit, Ctrl+D o Ctrl+C."
COMANDI_USCITA = {"esci", "exit"}
AVVISO_LIMITE = "Limite di passaggi raggiunto, riprova riformulando la domanda."


def esegui_chat(
    sessione: Sessione,
    intestazione: str,
    indirizzo: str,
    leggi: Callable[[str], str] = input,
    scrivi: Callable[[str], None] = print,
) -> None:
    """Ciclo Tu>/Assistente> fino all'uscita; gli errori di un turno non chiudono la chat."""
    scrivi(intestazione)
    scrivi(AIUTO)
    try:
        while True:
            domanda = leggi("Tu> ").strip()
            if not domanda:
                continue
            if domanda.lower() in COMANDI_USCITA:
                scrivi("Ciao!")
                return
            scrivi("(sto pensando...)")
            try:
                scrivi(f"Assistente> {sessione.chiedi(domanda)}")
            except LimitePassaggiRaggiunto:
                log.warning("limite di passaggi raggiunto")
                scrivi(AVVISO_LIMITE)
            except openai.APIError as errore:
                log.warning("errore del modello: %s", errore)
                scrivi(f"Impossibile contattare il modello su {indirizzo}: {errore}")
    except (EOFError, KeyboardInterrupt):
        scrivi("\nCiao!")


def _usa_utf8() -> None:
    # Su Windows, con output rediretto, Python userebbe cp1252 e rovinerebbe «—» e «lunedì».
    for flusso in (sys.stdout, sys.stderr):
        flusso.reconfigure(encoding="utf-8")


def main() -> int:
    """Avvia l'assistente: configurazione, log, strumenti, modello, grafo e chat."""
    _usa_utf8()
    try:
        config = carica_config()
    except ErroreConfigurazione as errore:
        print(f"Configurazione non valida: {errore}", file=sys.stderr)
        return 1
    configura_log(config.log_level)
    strumenti = [crea_orologio()]
    modello = crea_modello(config, strumenti)
    grafo = costruisci_grafo(modello, crea_registro(strumenti), config.max_tool_steps)
    intestazione = f"Assistente del laboratorio — modello: {config.lm_model} @ {config.lm_base_url}"
    esegui_chat(Sessione(grafo), intestazione, config.lm_base_url)
    return 0
