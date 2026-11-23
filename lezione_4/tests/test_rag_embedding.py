import httpx
import openai
import pytest

from finti_rag import EmbedderFinto
from rag.embedding import EmbedderLMStudio, ErroreEmbedding
from rag.errori import ErroreRag

URL = "http://localhost:1234/v1"
RICHIESTA = httpx.Request("POST", URL + "/embeddings")


class _Embeddings:
    def __init__(self, errore=None):
        self.chiamate = []
        self.errore = errore

    def create(self, model, input):
        self.chiamate.append((model, list(input)))
        if self.errore:
            raise self.errore
        return type("R", (), {"data": [{"embedding": [float(t)]} for t in input]})()


class _Client:
    def __init__(self, errore=None):
        self.embeddings = _Embeddings(errore)


def test_lotti_e_ordine():
    client = _Client()
    emb = EmbedderLMStudio(URL, "modello-x", lotto=32, client=client)
    testi = [str(i) for i in range(70)]
    assert emb.incorpora(testi) == [[float(i)] for i in range(70)]
    assert [len(i) for _, i in client.embeddings.chiamate] == [32, 32, 6]
    assert {m for m, _ in client.embeddings.chiamate} == {"modello-x"}
    assert emb.modello == "modello-x"


def test_connessione_rifiutata():
    emb = EmbedderLMStudio(URL, "m", client=_Client(openai.APIConnectionError(request=RICHIESTA)))
    with pytest.raises(ErroreEmbedding, match="localhost:1234") as e:
        emb.incorpora(["a"])
    assert isinstance(e.value, ErroreRag)


def test_timeout_e_connessione():
    emb = EmbedderLMStudio(URL, "m", client=_Client(openai.APITimeoutError(request=RICHIESTA)))
    with pytest.raises(ErroreEmbedding, match="non raggiungibile"):
        emb.incorpora(["a"])


@pytest.mark.parametrize("classe,codice", [(openai.NotFoundError, 404), (openai.BadRequestError, 400)])
def test_modello_assente(classe, codice):
    risposta = httpx.Response(codice, request=RICHIESTA)
    emb = EmbedderLMStudio(URL, "nomic-x", client=_Client(classe("no", response=risposta, body=None)))
    with pytest.raises(ErroreEmbedding, match="nomic-x") as e:
        emb.incorpora(["a"])
    assert "lms load" in str(e.value)


def _coseno(a, b):
    return sum(x * y for x, y in zip(a, b))


def test_embedder_finto():
    e = EmbedderFinto()
    a, b, c = e.incorpora(["gnocchi di patate", "patate per gli gnocchi", "pollo fritto"])
    assert e.incorpora(["gnocchi di patate"])[0] == a
    assert _coseno(a, b) > _coseno(a, c)
    assert e.chiamate == 2
    assert e.testi[0] == "gnocchi di patate" and len(e.testi) == 4
    assert len(a) == 64
