"""Doppioni di test del RAG (non è un file di test)."""

import math
import re
import zlib


class EmbedderFinto:
    """Embedder deterministico: parole minuscole proiettate con crc32 su `dimensione` celle."""

    def __init__(self, modello: str = "finto", dimensione: int = 64):
        self.modello = modello
        self.dimensione = dimensione
        self.chiamate = 0
        self.testi: list[str] = []

    def incorpora(self, testi: list[str]) -> list[list[float]]:
        self.chiamate += 1
        self.testi.extend(testi)
        return [self._vettore(t) for t in testi]

    def _vettore(self, testo: str) -> list[float]:
        v = [0.0] * self.dimensione
        for parola in re.findall(r"\w+", testo.lower()):
            v[zlib.crc32(parola.encode("utf-8")) % self.dimensione] += 1.0
        norma = math.sqrt(sum(x * x for x in v))
        return [x / norma for x in v] if norma else v
