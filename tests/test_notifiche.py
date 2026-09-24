"""Test dei messaggi Telegram e della lettura credenziali."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from amazon import ACQUISTABILE, NON_ACQUISTABILE, Esito
from notifiche import leggi_credenziali, messaggio_esaurito, messaggio_restock


def test_messaggio_restock_contiene_link_canonico():
    e = Esito(ACQUISTABILE, titolo="Set Allenatore", prezzo="54,99 EUR", venditore="Amazon")
    m = messaggio_restock("B0H9HFPRRD", e)
    assert "https://www.amazon.it/dp/B0H9HFPRRD" in m
    assert "amzn.eu" not in m
    assert "54,99" in m
    assert "Set Allenatore" in m


def test_messaggio_esaurito_e_breve():
    e = Esito(NON_ACQUISTABILE, titolo="Set Allenatore")
    m = messaggio_esaurito("B0H9HFPRRD", e)
    assert "Set Allenatore" in m
    assert len(m) < 300


def test_titolo_con_html_viene_neutralizzato():
    """Un titolo prodotto con caratteri speciali non deve rompere il
    parse_mode HTML di Telegram."""
    e = Esito(ACQUISTABILE, titolo="Carte <b>rare</b> & altro", prezzo="1 EUR", venditore="Amazon")
    m = messaggio_restock("B0", e)
    assert "&lt;b&gt;" in m
    assert "&amp;" in m


def test_credenziali_da_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("TG_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TG_CHAT_ID", raising=False)
    (tmp_path / ".env").write_text("TG_BOT_TOKEN=abc\nTG_CHAT_ID=123\n", encoding="utf-8")
    assert leggi_credenziali(tmp_path) == ("abc", "123")


def test_variabili_ambiente_hanno_precedenza(tmp_path, monkeypatch):
    monkeypatch.setenv("TG_BOT_TOKEN", "da-env")
    monkeypatch.setenv("TG_CHAT_ID", "999")
    (tmp_path / ".env").write_text("TG_BOT_TOKEN=da-file\nTG_CHAT_ID=1\n", encoding="utf-8")
    assert leggi_credenziali(tmp_path) == ("da-env", "999")


def test_credenziali_assenti_danno_none(tmp_path, monkeypatch):
    monkeypatch.delenv("TG_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TG_CHAT_ID", raising=False)
    assert leggi_credenziali(tmp_path) == (None, None)
