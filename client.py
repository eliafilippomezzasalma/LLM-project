"""Client minimo per il server locale di LM Studio.

Chiede una domanda da terminale, la invia al modello locale
e stampa la risposta.
"""

import os

import requests
from dotenv import load_dotenv

# --- Configurazione -------------------------------------------------------
load_dotenv()
base_url = os.environ["LM_BASE_URL"].rstrip("/")
if not base_url.endswith("/v1"):
    base_url += "/v1"  # il README usa http://localhost:1234/v1
model = os.environ["LM_MODEL"]

# --- Messaggi -------------------------------------------------------------
domanda = input("Domanda: ")
messages = [
    {"role": "system", "content": "Sei un assistente utile. Rispondi sempre in italiano, in modo chiaro e conciso."},
    {"role": "user", "content": domanda},
]

# --- Payload --------------------------------------------------------------
payload = {
    "model": model,
    "messages": messages,
    "temperature": 0.2,
    "max_tokens": 1000,
    "reasoning_effort": "none",
    "stream": False,
}

# --- Chiamata -------------------------------------------------------------
try:
    response = requests.post(f"{base_url}/chat/completions", json=payload, timeout=120)
    response.raise_for_status()
    print(response.json()["choices"][0]["message"]["content"])
except requests.exceptions.Timeout:
    print("Attesa scaduta: controllare server, carico e tempi.")
except requests.exceptions.ConnectionError:
    print("Connessione fallita: controllare server, URL e porta.")
except requests.exceptions.HTTPError:
    print("Errore HTTP:", response.status_code, response.text)
