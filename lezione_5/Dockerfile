# Immagine solo per l'esecuzione: niente test né strumenti di sviluppo.
FROM python:3.12.15-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY assistente/ assistente/

RUN useradd --create-home app
USER app

CMD ["python", "-m", "assistente"]
