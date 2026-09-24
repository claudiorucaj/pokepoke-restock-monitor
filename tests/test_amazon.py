"""Test del parser di disponibilita, tutti offline su pagine reali salvate."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from amazon import ACQUISTABILE, NON_ACQUISTABILE, SCONOSCIUTO, analizza

FIX = pathlib.Path(__file__).parent / "fixtures"


def leggi(nome):
    return (FIX / nome).read_text(encoding="utf-8", errors="ignore")


def test_su_invito_non_e_acquistabile():
    """Il caso critico: 'Disponibile su invito' ha gia il pulsante Aggiungi
    al carrello. Non deve mai risultare acquistabile."""
    e = analizza(leggi("invito_B0H9HFPRRD.html"))
    assert e.stato == NON_ACQUISTABILE
    assert "invito" in e.motivo.lower()


def test_prodotto_venduto_da_amazon_e_acquistabile():
    e = analizza(leggi("acquistabile_amazon_B00LH3DMUO.html"))
    assert e.stato == ACQUISTABILE
    assert e.prezzo is not None
    assert e.venditore.startswith("Amazon")
    assert "Amazon Basics" in e.titolo


def test_venditore_terzo_non_e_acquistabile():
    """Acquistabile ma venduto da NetStone: l'utente non vuole i terzi."""
    e = analizza(leggi("terzi_acquistabile_B0F8VZ7QVX.html"))
    assert e.stato == NON_ACQUISTABILE
    assert "vendit" in e.motivo.lower()


def test_pagina_antibot_e_sconosciuto():
    e = analizza(leggi("blocco_antibot.html"))
    assert e.stato == SCONOSCIUTO


def test_non_disponibile():
    e = analizza(leggi("nondisponibile_sintetica.html"))
    assert e.stato == NON_ACQUISTABILE


def test_stringa_vuota_e_sconosciuto():
    assert analizza("").stato == SCONOSCIUTO
