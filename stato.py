"""Stato persistente dei prodotti e regole di transizione.

La regola che conta: SCONOSCIUTO non e uno stato del prodotto, e la
confessione che non siamo riusciti a leggerlo. Non genera avvisi e non
sovrascrive mai l'ultimo stato buono, altrimenti un blocco anti-bot
diventerebbe un falso "non piu disponibile" seguito, al giro dopo, da un
falso restock.
"""

from __future__ import annotations

import json
from pathlib import Path

from amazon import ACQUISTABILE, SCONOSCIUTO

RESTOCK = "RESTOCK"
ESAURITO = "ESAURITO"


def carica(percorso) -> dict:
    """Stato salvato, oppure dizionario vuoto se il file manca o e illeggibile.
    Un file corrotto non deve impedire l'avvio del monitoraggio."""
    try:
        return json.loads(Path(percorso).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def salva(percorso, dati: dict) -> None:
    """Scrittura atomica: il file definitivo non resta mai a meta."""
    p = Path(percorso)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(dati, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def transizione(precedente: str | None, nuovo: str) -> str | None:
    """Che avviso merita il passaggio da uno stato all'altro.

    Il primo avvistamento di un prodotto gia acquistabile vale come
    RESTOCK: e la prima volta che possiamo dirlo all'utente.
    """
    if nuovo == SCONOSCIUTO or nuovo == precedente:
        return None
    if nuovo == ACQUISTABILE:
        return RESTOCK
    if precedente == ACQUISTABILE:
        return ESAURITO
    return None
