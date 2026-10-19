"""Client minimo per il server locale di LM Studio.

Scheletro da completare con Claude Code (slide 19-22):
configurazione, messaggi, payload e chiamata HTTP.
Import e gestione degli errori sono gia' presenti: conservarli.
"""

import os

import requests
from dotenv import load_dotenv

# --- Configurazione -------------------------------------------------------
# DA COMPLETARE: caricare .env e leggere LM_BASE_URL e LM_MODEL,
# senza scrivere URL o nome del modello nel codice.

# --- Messaggi -------------------------------------------------------------
# DA COMPLETARE: un'istruzione "system" in italiano e una domanda "user" fissa.

# --- Payload --------------------------------------------------------------
# DA COMPLETARE: dizionario con model, messages, temperature, max_tokens,
# reasoning_effort ("none", senza ragionamento) e stream.

# --- Chiamata -------------------------------------------------------------
try:
    # DA COMPLETARE: inviare il payload a {base_url}/chat/completions,
    # controllare lo stato HTTP e stampare choices[0].message.content.
    print("client.py non ancora completato: vedere il piano concordato.")
except requests.exceptions.Timeout:
    print("Attesa scaduta: controllare server, carico e tempi.")
except requests.exceptions.ConnectionError:
    print("Connessione fallita: controllare server, URL e porta.")
except requests.exceptions.HTTPError:
    print("Errore HTTP:", response.status_code, response.text)
