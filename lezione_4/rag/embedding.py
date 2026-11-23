"""Embedding dei testi con il server LM Studio (endpoint OpenAI-compatibile /v1/embeddings)."""

from typing import Protocol

import openai

from rag.errori import ErroreRag


class ErroreEmbedding(ErroreRag):
    """LM Studio non raggiungibile o modello di embedding non disponibile."""


class Embedder(Protocol):
    modello: str

    def incorpora(self, testi: list[str]) -> list[list[float]]: ...


def _vettore(elemento) -> list[float]:
    # La libreria restituisce oggetti con .embedding; accettiamo anche dizionari.
    return list(elemento["embedding"] if isinstance(elemento, dict) else elemento.embedding)


class EmbedderLMStudio:
    def __init__(self, base_url: str, modello: str, lotto: int = 32, client=None):
        if lotto < 1:
            raise ValueError("lotto deve essere almeno 1")
        self.base_url = base_url
        self.modello = modello
        self.lotto = lotto
        self._client = client or openai.OpenAI(
            base_url=base_url, api_key="lm-studio", timeout=60, max_retries=0
        )

    def incorpora(self, testi: list[str]) -> list[list[float]]:
        vettori: list[list[float]] = []
        for i in range(0, len(testi), self.lotto):
            vettori.extend(self._lotto(testi[i : i + self.lotto]))
        return vettori

    def _lotto(self, testi: list[str]) -> list[list[float]]:
        try:
            risposta = self._client.embeddings.create(model=self.modello, input=testi)
        except openai.APIConnectionError as e:  # include APITimeoutError
            raise ErroreEmbedding(
                f"LM Studio non raggiungibile su {self.base_url}: avvialo e attiva il server locale"
            ) from e
        except openai.APIStatusError as e:
            if 400 <= e.status_code < 500:
                raise ErroreEmbedding(
                    f"modello di embedding {self.modello} non disponibile in LM Studio "
                    f"(caricalo con: lms load {self.modello})"
                ) from e
            raise ErroreEmbedding(
                f"LM Studio ha risposto con un errore {e.status_code} su {self.base_url}: riprova"
            ) from e
        return [_vettore(d) for d in risposta.data]
