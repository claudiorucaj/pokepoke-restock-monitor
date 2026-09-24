"""Lettura e interpretazione delle pagine prodotto di amazon.it.

Il parsing e a espressioni regolari, tarato su pagine reali salvate in
tests/fixtures/. Nessuna dipendenza da librerie HTML: la struttura che ci
serve (disponibilita, venditore, prezzo, pulsante Acquista ora) e stabile
e localizzata, e il costo di una dipendenza in piu non si giustifica.

Il punto delicato, verificato sul campo: sui prodotti "Disponibile su
invito" il pulsante Aggiungi al carrello e gia presente. Usarlo come
segnale di disponibilita produrrebbe falsi allarmi su tutti i prodotti
monitorati. Il discriminante affidabile e il pulsante Acquista ora.
"""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass

import requests

ACQUISTABILE = "ACQUISTABILE"
NON_ACQUISTABILE = "NON_ACQUISTABILE"
SCONOSCIUTO = "SCONOSCIUTO"

NEGATIVI = ("su invito", "non disponibile", "attualmente non disponibile")

# Una pagina prodotto vera sta sopra i 400 KB; la pagina anti-bot di Amazon
# ("Fai clic sul pulsante qui sotto per continuare a fare acquisti") sta
# sotto i 4 KB. La soglia sta comodamente in mezzo.
SOGLIA_PAGINA_VALIDA = 50_000


@dataclass
class Esito:
    """Cosa sappiamo di un prodotto dopo un controllo."""

    stato: str
    titolo: str | None = None
    prezzo: str | None = None
    venditore: str | None = None
    motivo: str = ""


def _testo(frammento: str) -> str:
    """Toglie i tag e normalizza gli spazi."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", frammento)).split())


def e_bloccata(testo_html: str) -> bool:
    """Vero se la risposta non e una pagina prodotto leggibile."""
    if len(testo_html) < SOGLIA_PAGINA_VALIDA:
        return True
    if "Continua con gli acquisti" in testo_html:
        return True
    return re.search(r"<title>", testo_html) is None


def _titolo(testo_html: str) -> str | None:
    m = re.search(r"<title>([^<]*)</title>", testo_html)
    if not m:
        return None
    return html.unescape(m.group(1)).split(" : Amazon")[0].strip() or None


def _disponibilita(testo_html: str) -> str | None:
    """Testo del blocco disponibilita, ripulito dalla coda JSON che Amazon
    infila dentro lo stesso div."""
    m = re.search(r'id="availability"[^>]*>(.*?)</div>', testo_html, re.S)
    if not m:
        return None
    return _testo(m.group(1)).split("{")[0].strip() or None


def _venditore(testo_html: str) -> str | None:
    """Il buybox espone coppie etichetta/valore. L'etichetta e 'Venditore'
    quando spedizione e vendita sono separate, 'Speditore / Venditore'
    quando coincidono."""
    m = re.search(
        r'id="offer-display-features".*?(?=id="desktop_qualifiedBuyBox"|id="addToCart")',
        testo_html,
        re.S,
    )
    segmento = m.group(0) if m else testo_html
    for blocco in re.finditer(
        r"offer-display-feature-name[^>]*>(.*?)</div>"
        r".*?offer-display-feature-text-message[^>]*>(.*?)</span>",
        segmento,
        re.S,
    ):
        if "Venditore" in _testo(blocco.group(1)):
            return _testo(blocco.group(2)) or None
    return None


def _prezzo(testo_html: str) -> str | None:
    m = re.search(r'class="a-price-whole">([\d.]+)', testo_html)
    if not m:
        return None
    f = re.search(r'class="a-price-fraction">(\d+)', testo_html)
    return f"{m.group(1)},{f.group(1) if f else '00'} EUR"


def analizza(testo_html: str) -> Esito:
    """Decide lo stato di un prodotto a partire dall'HTML della sua pagina.

    Acquistabile solo se tutte e quattro le condizioni reggono: nessun
    termine negativo nella disponibilita, pulsante Acquista ora presente,
    venditore Amazon, prezzo leggibile.
    """
    if e_bloccata(testo_html):
        return Esito(SCONOSCIUTO, motivo="pagina anti-bot o risposta troncata")

    titolo = _titolo(testo_html)
    disponibilita = _disponibilita(testo_html)
    venditore = _venditore(testo_html)
    prezzo = _prezzo(testo_html)
    compra_subito = "buy-now-button" in testo_html
    base = dict(titolo=titolo, prezzo=prezzo, venditore=venditore)

    if any(n in (disponibilita or "").lower() for n in NEGATIVI):
        return Esito(NON_ACQUISTABILE, motivo=f"disponibilita: {disponibilita}", **base)
    if not compra_subito:
        return Esito(NON_ACQUISTABILE, motivo="manca il pulsante Acquista ora", **base)
    if not venditore or not venditore.startswith("Amazon"):
        return Esito(NON_ACQUISTABILE, motivo=f"venditore terzo: {venditore}", **base)
    if not prezzo:
        return Esito(NON_ACQUISTABILE, motivo="prezzo non leggibile", **base)
    return Esito(ACQUISTABILE, motivo=f"acquistabile a {prezzo}", **base)


# --- scaricamento -----------------------------------------------------------

UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def url_prodotto(asin: str) -> str:
    """Forma canonica del link, senza i parametri di tracciamento degli
    short link amzn.eu."""
    return f"https://www.amazon.it/dp/{asin}"


def sessione() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    return s


def scarica(asin, sess, tentativi=3, pausa=5.0, dormi=time.sleep) -> str | None:
    """HTML della pagina prodotto, oppure None se Amazon ci blocca a ogni
    tentativo. Ogni tentativo cambia User-Agent: sul campo basta a far
    passare la richiesta successiva."""
    for i in range(tentativi):
        try:
            r = sess.get(
                url_prodotto(asin), timeout=30, headers={"User-Agent": UA[i % len(UA)]}
            )
            if r.status_code == 200 and not e_bloccata(r.text):
                return r.text
        except Exception:
            pass
        if i < tentativi - 1:
            dormi(pausa)
    return None


def controlla(asin, sess, **kw) -> Esito:
    testo = scarica(asin, sess, **kw)
    if testo is None:
        return Esito(SCONOSCIUTO, motivo="bloccato dopo tutti i tentativi")
    return analizza(testo)
