"""Test della scelta di chi controlla, senza toccare le API di GitHub."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from leader import pc_attivo


class SessioneFinta:
    def __init__(self, corpo, codice=200):
        self.corpo = corpo
        self.codice = codice
        self.parametri = None

    def get(self, url, params=None, headers=None, timeout=None):
        self.parametri = params

        class R:
            pass

        r = R()
        r.status_code = self.codice
        r.json = lambda: self.corpo
        return r


class SessioneCheEsplode:
    def get(self, *a, **k):
        raise RuntimeError("rete assente")


def test_esecuzione_in_corso_significa_pc_attivo():
    sess = SessioneFinta({"total_count": 1})
    assert pc_attivo("tizio/repo", "tok", sess=sess) is True


def test_nessuna_esecuzione_in_corso_significa_pc_fermo():
    """Se il PC e spento il suo job resta in coda, non in esecuzione:
    il cloud deve subentrare."""
    sess = SessioneFinta({"total_count": 0})
    assert pc_attivo("tizio/repo", "tok", sess=sess) is False


def test_chiede_solo_le_esecuzioni_in_corso():
    sess = SessioneFinta({"total_count": 0})
    pc_attivo("tizio/repo", "tok", sess=sess)
    assert sess.parametri["status"] == "in_progress"


def test_errore_api_fa_lavorare_il_cloud():
    """Meglio un avviso doppio che un restock perso."""
    assert pc_attivo("tizio/repo", "tok", sess=SessioneFinta({}, codice=403)) is False
    assert pc_attivo("tizio/repo", "tok", sess=SessioneCheEsplode()) is False


def test_credenziali_mancanti_fanno_lavorare_il_cloud():
    assert pc_attivo("", "tok") is False
    assert pc_attivo("tizio/repo", "") is False
