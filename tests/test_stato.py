"""Test dello stato persistente e delle regole di transizione."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from amazon import ACQUISTABILE, NON_ACQUISTABILE, SCONOSCIUTO
from stato import carica, salva, transizione


def test_restock_quando_diventa_acquistabile():
    assert transizione(NON_ACQUISTABILE, ACQUISTABILE) == "RESTOCK"


def test_esaurito_quando_smette_di_esserlo():
    assert transizione(ACQUISTABILE, NON_ACQUISTABILE) == "ESAURITO"


def test_nessun_avviso_se_stato_invariato():
    assert transizione(ACQUISTABILE, ACQUISTABILE) is None
    assert transizione(NON_ACQUISTABILE, NON_ACQUISTABILE) is None


def test_sconosciuto_non_genera_mai_avvisi():
    """Un blocco anti-bot non deve mai sembrare un cambio di stato."""
    assert transizione(ACQUISTABILE, SCONOSCIUTO) is None
    assert transizione(NON_ACQUISTABILE, SCONOSCIUTO) is None
    assert transizione(SCONOSCIUTO, ACQUISTABILE) == "RESTOCK"


def test_primo_avvistamento_acquistabile_avvisa():
    assert transizione(None, ACQUISTABILE) == "RESTOCK"


def test_primo_avvistamento_non_acquistabile_tace():
    assert transizione(None, NON_ACQUISTABILE) is None


def test_salva_e_ricarica(tmp_path):
    p = tmp_path / "state.json"
    assert carica(p) == {}
    salva(p, {"B0": {"stato": ACQUISTABILE}})
    assert carica(p)["B0"]["stato"] == ACQUISTABILE


def test_file_corrotto_non_esplode(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{rotto", encoding="utf-8")
    assert carica(p) == {}
