"""Invio messaggi Telegram e lettura dei comandi in arrivo.

Nessuna funzione qui solleva eccezioni verso il chiamante: un guasto di
Telegram non deve fermare il monitoraggio di Amazon, che e il lavoro vero.
"""

from __future__ import annotations

import html as html_mod
import os
import re
from datetime import datetime
from pathlib import Path

import requests

from amazon import url_prodotto

API = "https://api.telegram.org/bot{token}/{metodo}"


def leggi_credenziali(cartella) -> tuple[str | None, str | None]:
    """Token e chat id, dalle variabili d'ambiente o dal file .env accanto
    allo script. L'ambiente ha la precedenza, cosi i GitHub Secrets
    sovrascrivono il file locale senza toccarlo."""
    token = os.environ.get("TG_BOT_TOKEN")
    chat = os.environ.get("TG_CHAT_ID")
    if token and chat:
        return token, chat
    percorso = Path(cartella) / ".env"
    try:
        contenuto = percorso.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return token, chat
    valori = dict(re.findall(r"^\s*(\w+)\s*=\s*(.*?)\s*$", contenuto, re.M))
    return token or valori.get("TG_BOT_TOKEN"), chat or valori.get("TG_CHAT_ID")


def messaggio_restock(asin: str, esito) -> str:
    return (
        "\U0001f6a8 <b>DISPONIBILE ORA</b>\n\n"
        f"{html_mod.escape(esito.titolo or asin)}\n"
        f"Prezzo: <b>{html_mod.escape(esito.prezzo or 'n/d')}</b>\n"
        f"Venditore: {html_mod.escape(esito.venditore or 'n/d')}\n\n"
        f"{url_prodotto(asin)}\n\n"
        f"<i>{datetime.now().strftime('%d/%m %H:%M:%S')}</i>"
    )


def messaggio_esaurito(asin: str, esito) -> str:
    return (
        f"⚪ Finito: {html_mod.escape(esito.titolo or asin)}\n"
        f"{url_prodotto(asin)}"
    )


class Telegram:
    """Client minimo: invio messaggi e lettura comandi."""

    def __init__(self, token, chat_id, sess=None):
        self.token = token
        self.chat_id = chat_id
        self.sess = sess or requests.Session()
        self._offset = None

    def _chiama(self, metodo, **parametri):
        try:
            r = self.sess.post(
                API.format(token=self.token, metodo=metodo), data=parametri, timeout=20
            )
            dati = r.json()
            return dati if dati.get("ok") else None
        except Exception:
            return None

    def invia(self, testo: str, silenzioso: bool = False) -> bool:
        risposta = self._chiama(
            "sendMessage",
            chat_id=self.chat_id,
            text=testo,
            parse_mode="HTML",
            disable_web_page_preview="false",
            disable_notification="true" if silenzioso else "false",
        )
        return risposta is not None

    def comandi(self) -> list[str]:
        """Comandi arrivati dall'ultima lettura. Lista vuota se Telegram non
        risponde: i comandi sono un extra, non possono bloccare il ciclo."""
        parametri = {"timeout": 0}
        if self._offset is not None:
            parametri["offset"] = self._offset
        risposta = self._chiama("getUpdates", **parametri)
        if not risposta:
            return []
        trovati = []
        for aggiornamento in risposta.get("result", []):
            self._offset = aggiornamento["update_id"] + 1
            testo = (aggiornamento.get("message") or {}).get("text", "")
            if testo.startswith("/"):
                trovati.append(testo.split("@")[0].strip().lower())
        return trovati
