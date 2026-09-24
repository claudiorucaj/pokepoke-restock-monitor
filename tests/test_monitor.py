"""Test del giro di controllo, senza rete e senza Telegram."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from amazon import ACQUISTABILE, NON_ACQUISTABILE, SCONOSCIUTO, Esito
from monitor import giro


class TelegramFinto:
    def __init__(self):
        self.inviati = []

    def invia(self, testo, silenzioso=False):
        self.inviati.append(testo)
        return True


CFG = {
    "prodotti": [{"asin": "B01", "nome": "Uno"}],
    "canarino": None,
    "ogni_quanti_giri_canarino": 0,
    "pausa_tra_prodotti_s": 0,
    "tentativi_per_prodotto": 1,
    "pausa_retry_s": 0,
    "minuti_cecita_avviso": 15,
    "cooldown_avvisi_tecnici_min": 60,
}


def disponibile(asin, sess, **kw):
    return Esito(ACQUISTABILE, "Uno", "10 EUR", "Amazon", "acquistabile a 10 EUR")


def non_disponibile(asin, sess, **kw):
    return Esito(NON_ACQUISTABILE, "Uno", None, "Amazon", "disponibilita: Disponibile su invito")


def bloccato(asin, sess, **kw):
    return Esito(SCONOSCIUTO, motivo="bloccato dopo tutti i tentativi")


def test_restock_invia_un_avviso():
    tg = TelegramFinto()
    dati = {"B01": {"stato": NON_ACQUISTABILE}}
    giro(CFG, None, tg, dati, controllore=disponibile)
    assert len(tg.inviati) == 1
    assert "DISPONIBILE ORA" in tg.inviati[0]
    assert "https://www.amazon.it/dp/B01" in tg.inviati[0]
    assert dati["B01"]["stato"] == ACQUISTABILE


def test_stato_invariato_non_invia_nulla():
    tg = TelegramFinto()
    dati = {"B01": {"stato": ACQUISTABILE}}
    giro(CFG, None, tg, dati, controllore=disponibile)
    assert tg.inviati == []


def test_blocco_non_invia_e_non_sovrascrive_lo_stato():
    """Il caso che rovinerebbe tutto: Amazon ci blocca e il bot conclude
    che il prodotto non e piu disponibile."""
    tg = TelegramFinto()
    dati = {"B01": {"stato": ACQUISTABILE}}
    giro(CFG, None, tg, dati, controllore=bloccato)
    assert tg.inviati == []
    assert dati["B01"]["stato"] == ACQUISTABILE


def test_esaurito_avvisa_una_volta_sola():
    tg = TelegramFinto()
    dati = {"B01": {"stato": ACQUISTABILE}}
    giro(CFG, None, tg, dati, controllore=non_disponibile)
    giro(CFG, None, tg, dati, controllore=non_disponibile)
    assert len(tg.inviati) == 1
    assert "Finito" in tg.inviati[0]


def test_dry_run_non_invia():
    tg = TelegramFinto()
    dati = {"B01": {"stato": NON_ACQUISTABILE}}
    giro(CFG, None, tg, dati, dry_run=True, controllore=disponibile)
    assert tg.inviati == []


def test_riepilogo_conta_gli_sconosciuti():
    riepilogo = giro(CFG, None, TelegramFinto(), {}, controllore=bloccato)
    assert riepilogo["sconosciuti"] == 1
    assert riepilogo["letti"] == 0


def test_nome_da_config_se_amazon_non_da_il_titolo():
    tg = TelegramFinto()

    def senza_titolo(asin, sess, **kw):
        return Esito(ACQUISTABILE, None, "10 EUR", "Amazon")

    giro(CFG, None, tg, {}, controllore=senza_titolo)
    assert "Uno" in tg.inviati[0]
