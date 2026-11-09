"""Nota non normativa dei calcoli di scadenza: mostrata all'utente una sola volta per sessione."""

from dataclasses import dataclass

from langchain_core.tools import BaseTool, StructuredTool

# Stessa frase di scadenze.py (un test le confronta): il server non ha stato,
# quindi è la sessione a decidere quando la nota non serve più.
FRASE_NOTA = "calcolo indicativo, non ha valore legale."
RIGA_NOTA = f"Nota: {FRASE_NOTA}"
STRUMENTO_CON_NOTA = "compute_deadline"


@dataclass
class NotaNonNormativa:
    """Ricorda se la nota è già arrivata all'utente nella risposta del modello."""

    consegnata: bool = False

    def filtra(self, testo: str) -> str:
        """Se la nota è già stata consegnata, toglie le sue righe dal risultato dello strumento."""
        if not self.consegnata:
            return testo
        righe = testo.split("\n")
        return "\n".join(r for i, r in enumerate(righe) if i == 0 or not r.startswith("Nota:"))

    def completa(self, testo: str, risultati: list[str]) -> str:
        """Aggiunge la riga della nota alla risposta se serve e il modello l'ha omessa."""
        if self.consegnata or "non ha valore legale" in testo.lower():
            return testo
        if any(r.startswith("Nota:") for risultato in risultati for r in risultato.split("\n")):
            return f"{testo}\n\n{RIGA_NOTA}"
        return testo

    def registra_risposta(self, testo: str) -> None:
        """Segna la nota come consegnata se la risposta all'utente la riporta."""
        if "non ha valore legale" in testo.lower():
            self.consegnata = True


def con_nota(strumenti: list[BaseTool], nota: NotaNonNormativa) -> list[BaseTool]:
    """Avvolge compute_deadline perché il suo risultato passi da `nota.filtra`."""
    risultato = []
    for originale in strumenti:
        if originale.name != STRUMENTO_CON_NOTA:
            risultato.append(originale)
            continue

        def esegui(originale=originale, **argomenti) -> str:
            return nota.filtra(str(originale.invoke(argomenti)))

        risultato.append(
            StructuredTool.from_function(
                esegui,
                name=originale.name,
                description=originale.description,
                args_schema=originale.args_schema,
            )
        )
    return risultato
