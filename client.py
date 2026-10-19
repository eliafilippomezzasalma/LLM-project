"""Client minimo per il server locale di LM Studio.

Chiede domande da terminale, le invia al modello locale
e stampa le risposte in streaming. La cronologia resta in memoria
per la sessione. Si termina scrivendo "esci".
"""

import json
import os
import sys

import requests
from dotenv import load_dotenv

# --- Configurazione -------------------------------------------------------
load_dotenv()
base_url = os.environ["LM_BASE_URL"].rstrip("/")
if not base_url.endswith("/v1"):
    base_url += "/v1"  # il README usa http://localhost:1234/v1
model = os.environ["LM_MODEL"]
sys.stdout.reconfigure(encoding="utf-8")  # accenti corretti anche con console non UTF-8

# --- Cronologia della sessione (in memoria, persa alla chiusura) ----------
messages = [
    {"role": "system", "content": "Sei un assistente utile. Rispondi sempre in italiano, in modo chiaro e conciso."},
]

# --- Ciclo domande (si esce con "esci") -----------------------------------
while True:
    domanda = input("Domanda (esci per terminare): ").strip()
    if domanda.lower() == "esci":
        break
    if not domanda:
        continue

    messages.append({"role": "user", "content": domanda})
    risposta = []
    completata = False
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1000,
        "reasoning_effort": "none",
        "stream": True,
    }

    try:
        response = requests.post(f"{base_url}/chat/completions", json=payload, timeout=120, stream=True)
        response.raise_for_status()
        # Le righe arrivano come byte: decodifica esplicita in UTF-8,
        # altrimenti requests può assumere ISO-8859-1 e rovinare gli accenti.
        for riga in response.iter_lines():
            if not riga.startswith(b"data: "):
                continue
            dati = riga[len(b"data: "):].decode("utf-8")
            if dati == "[DONE]":
                break
            delta = json.loads(dati)["choices"][0]["delta"]
            testo = delta.get("content") or ""
            risposta.append(testo)
            print(testo, end="", flush=True)
        print()
        completata = True
    except requests.exceptions.Timeout:
        print("Attesa scaduta: controllare server, carico e tempi.")
    except requests.exceptions.ConnectionError:
        print("Connessione fallita: controllare server, URL e porta.")
    except requests.exceptions.HTTPError:
        print("Errore HTTP:", response.status_code, response.text)

    if completata:
        messages.append({"role": "assistant", "content": "".join(risposta)})
    else:
        messages.pop()  # domanda senza risposta: non entra nella cronologia
