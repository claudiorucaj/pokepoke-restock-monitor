"""Test della scelta di chi controlla, senza toccare le API di GitHub."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from leader import pc_attivo


class SessioneFinta:
    def __init__(self, corpo, codice=200):
        self.corpo = corpo
        self.codice = codice

    def get(self, url, headers=None, timeout=None):
        class R:
            pass

        r = R()
        r.status_code = self.codice
        r.json = lambda: self.corpo
        return r


class SessioneCheEsplode:
    def get(self, *a, **k):
        raise RuntimeError("rete assente")


def test_runner_online_e_occupato_significa_pc_attivo():
    sess = SessioneFinta({"runners": [{"status": "online", "busy": True}]})
    assert pc_attivo("tizio/repo", "tok", sess) is True


def test_runner_online_ma_fermo_significa_pc_non_attivo():
    """Se il runner e acceso ma non sta girando nulla, il job del PC e morto:
    il cloud deve subentrare."""
    sess = SessioneFinta({"runners": [{"status": "online", "busy": False}]})
    assert pc_attivo("tizio/repo", "tok", sess) is False


def test_runner_offline_significa_pc_spento():
    sess = SessioneFinta({"runners": [{"status": "offline", "busy": False}]})
    assert pc_attivo("tizio/repo", "tok", sess) is False


def test_nessun_runner_registrato():
    assert pc_attivo("tizio/repo", "tok", SessioneFinta({"runners": []})) is False


def test_errore_api_fa_lavorare_il_cloud():
    """Meglio un avviso doppio che un restock perso."""
    assert pc_attivo("tizio/repo", "tok", SessioneFinta({}, codice=403)) is False
    assert pc_attivo("tizio/repo", "tok", SessioneCheEsplode()) is False


def test_credenziali_mancanti_fanno_lavorare_il_cloud():
    assert pc_attivo("", "tok") is False
    assert pc_attivo("tizio/repo", "") is False
