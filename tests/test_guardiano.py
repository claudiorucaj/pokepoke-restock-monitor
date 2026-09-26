"""Test del guardiano della catena, senza GitHub e senza Telegram."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from guardiano import catena_viva, sorveglia


class Risposta:
    def __init__(self, corpo, codice=200):
        self.status_code = codice
        self._corpo = corpo

    def json(self):
        return self._corpo


class GitHubFinto:
    def __init__(self, stati, codice=200):
        self.corpo = {"workflow_runs": [{"status": s} for s in stati]}
        self.codice = codice
        self.lanciati = 0

    def get(self, url, params=None, headers=None, timeout=None):
        return Risposta(self.corpo, self.codice)

    def post(self, url, json=None, headers=None, timeout=None):
        self.lanciati += 1
        return Risposta({}, 204)


class GitHubGuasto:
    def get(self, *a, **k):
        raise RuntimeError("rete assente")

    post = get


class TelegramFinto:
    def __init__(self):
        self.inviati = []

    def invia(self, testo, silenzioso=False):
        self.inviati.append(testo)
        return True


def test_run_in_corso_o_in_attesa_significa_catena_viva():
    for stato in ("in_progress", "queued", "pending", "waiting", "requested"):
        assert catena_viva("u/r", "t", sess=GitHubFinto(["completed", stato])) is True


def test_solo_run_conclusi_significa_catena_spezzata():
    assert catena_viva("u/r", "t", sess=GitHubFinto(["completed", "completed"])) is False


def test_github_irraggiungibile_non_e_una_risposta():
    """Nel dubbio non si avvisa: un falso allarme ogni dieci minuti
    insegnerebbe a ignorare quello vero."""
    assert catena_viva("u/r", "t", sess=GitHubGuasto()) is None
    assert catena_viva("u/r", "t", sess=GitHubFinto([], codice=500)) is None


def test_catena_spezzata_riavvia_e_avvisa():
    gh, tg = GitHubFinto(["completed"]), TelegramFinto()
    assert sorveglia("u/r", "t", tg, sess=gh) == "riavviata"
    assert gh.lanciati == 1
    assert len(tg.inviati) == 1


def test_catena_viva_non_fa_nulla():
    gh, tg = GitHubFinto(["in_progress"]), TelegramFinto()
    assert sorveglia("u/r", "t", tg, sess=gh) == "viva"
    assert gh.lanciati == 0
    assert tg.inviati == []
