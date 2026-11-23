"""Riscrittura della domanda con il lessico del ricettario, prima della ricerca (specs.md §21.3, leva 3)."""

import re
from typing import Protocol

import openai

from rag.errori import ErroreRag

PROMPT = (
    "Riscrivi la domanda dell'utente con le parole che userebbe il ricettario di Pellegrino Artusi "
    "(«La scienza in cucina e l'arte di mangiar bene», italiano di fine Ottocento): indica il nome "
    "probabile del piatto e gli ingredienti principali con i termini del libro. "
    "Rispondi con una sola riga, senza spiegazioni."
)
# Come in assistente/modello.py: LM Studio accetta reasoning_effort solo nel body grezzo.
RAGIONAMENTO_DISATTIVATO = {"reasoning_effort": "none"}
_BLOCCO_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class ErroreRiscrittura(ErroreRag):
    """LM Studio non raggiungibile o modello di chat non disponibile."""


class Riscrittore(Protocol):
    def riscrivi(self, domanda: str) -> str: ...


def pulisci(testo: str | None) -> str:
    """Toglie i blocchi <think> e tiene la prima riga non vuota (stringa vuota se non resta nulla)."""
    senza = _BLOCCO_THINK.sub("", testo or "")
    righe = [r.strip() for r in senza.splitlines() if r.strip()]
    return righe[0] if righe else ""


class RiscrittoreLMStudio:
    def __init__(self, base_url: str, modello: str, client=None):
        self.base_url = base_url
        self.modello = modello
        self._client = client or openai.OpenAI(
            base_url=base_url, api_key="lm-studio", timeout=120, max_retries=0
        )

    def riscrivi(self, domanda: str) -> str:
        try:
            risposta = self._client.chat.completions.create(
                model=self.modello,
                temperature=0,
                messages=[{"role": "system", "content": PROMPT}, {"role": "user", "content": domanda}],
                extra_body=RAGIONAMENTO_DISATTIVATO,
            )
        except openai.APIConnectionError as e:
            raise ErroreRiscrittura(
                f"LM Studio non raggiungibile su {self.base_url}: avvialo e attiva il server locale"
            ) from e
        except openai.APIStatusError as e:
            if 400 <= e.status_code < 500:
                raise ErroreRiscrittura(
                    f"modello di riscrittura {self.modello} non disponibile in LM Studio "
                    f"(caricalo con: lms load {self.modello})"
                ) from e
            raise ErroreRiscrittura(
                f"LM Studio ha risposto con un errore {e.status_code} su {self.base_url}: riprova"
            ) from e
        return pulisci(risposta.choices[0].message.content)
