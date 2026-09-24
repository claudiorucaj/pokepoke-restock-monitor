# Bot avviso restock Amazon.it — Piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ricevere su Telegram un avviso immediato con link ufficiale Amazon quando uno dei 7 prodotti Pokémon monitorati diventa acquistabile direttamente da Amazon.

**Architecture:** Un pacchetto Python di quattro moduli a responsabilità singola (scaricamento/parsing Amazon, stato persistente, notifiche Telegram, ciclo di controllo). Lo stesso codice viene lanciato in fase 1 da un task di Windows sul PC e in fase 2 dai due workflow GitHub Actions (runner PC primario, runner cloud di riserva).

**Tech Stack:** Python 3.13, `requests` 2.34, stdlib (`re`, `json`, `dataclasses`, `pathlib`, `argparse`). Nessuna dipendenza HTML esterna: il parsing è a espressioni regolari, verificato su pagine reali salvate.

**Spec:** `docs/superpowers/specs/2026-09-24-amazon-restock-bot-design.md`

## Global Constraints

- Dominio unico: `amazon.it`. Link notificato sempre in forma canonica `https://www.amazon.it/dp/<ASIN>`.
- Tre stati, mai due: `ACQUISTABILE`, `NON_ACQUISTABILE`, `SCONOSCIUTO`.
- `SCONOSCIUTO` non genera mai un avviso e non aggiorna mai lo stato salvato.
- Un prodotto è `ACQUISTABILE` solo se **tutte** e quattro: `buy-now-button` presente, venditore Amazon, testo disponibilità privo di termini negativi, prezzo leggibile.
- Termini negativi: `su invito`, `non disponibile`, `attualmente non disponibile`.
- Rilevamento blocco anti-bot: assenza di `<title>`, oppure corpo sotto 50.000 byte, oppure testo `Continua con gli acquisti`, oppure HTTP 503.
- Ciclo completo dei 7 prodotti ogni ~60 secondi.
- ASIN canarino: `B00LH3DMUO` (Amazon Basics batterie AAA, venduto da Amazon, sempre disponibile).
- Segreti solo in `.env` locale o GitHub Secrets. Mai committati. `.env` è già in `.gitignore`.
- Tutti i messaggi utente e i nomi pubblici in italiano, coerenti con i bot esistenti dell'utente.

---

### Task 1: Parser della disponibilità

Il cuore del sistema e il punto in cui fallirebbe per primo. Va scritto per primo e con i test più severi.

**Files:**
- Create: `amazon.py`
- Create: `tests/test_amazon.py`
- Create: `tests/fixtures/nondisponibile_sintetica.html`

**Interfaces:**
- Consumes: le fixture reali già in `tests/fixtures/`.
- Produces:
  - `@dataclass Esito(stato: str, titolo: str|None, prezzo: str|None, venditore: str|None, motivo: str)`
  - `analizza(testo_html: str) -> Esito`
  - Costanti `ACQUISTABILE`, `NON_ACQUISTABILE`, `SCONOSCIUTO` (stringhe).

- [ ] **Step 1: Creare la fixture sintetica "non disponibile"**

Derivarla dalla pagina reale su invito sostituendo il testo di disponibilità e togliendo il buy-now. Va etichettata come sintetica in testa al file.

```python
import pathlib, re
src = pathlib.Path("tests/fixtures/invito_B0H9HFPRRD.html").read_text(encoding="utf-8", errors="ignore")
out = re.sub(r'(id="availability"[^>]*>)(.*?)(</div>)',
             r'\1<span class="a-color-price">Attualmente non disponibile.</span>\3',
             src, count=1, flags=re.S)
out = out.replace("buy-now-button", "xx-rimosso-xx")
out = "<!-- FIXTURE SINTETICA: derivata da invito_B0H9HFPRRD.html, disponibilita sostituita -->\n" + out
pathlib.Path("tests/fixtures/nondisponibile_sintetica.html").write_text(out, encoding="utf-8")
```

- [ ] **Step 2: Scrivere i test che falliscono**

```python
import pathlib, pytest
from amazon import analizza, ACQUISTABILE, NON_ACQUISTABILE, SCONOSCIUTO

FIX = pathlib.Path(__file__).parent / "fixtures"

def leggi(nome):
    return (FIX / nome).read_text(encoding="utf-8", errors="ignore")

def test_su_invito_non_e_acquistabile():
    """Il caso critico: 'Disponibile su invito' ha gia il pulsante
    Aggiungi al carrello. Non deve mai risultare acquistabile."""
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
```

- [ ] **Step 3: Verificare che falliscano**

Run: `python -m pytest tests/test_amazon.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'amazon'`

- [ ] **Step 4: Implementare `amazon.py` (sola parte di parsing)**

Regex verificate sulle fixture reali: il blocco `id="availability"` contiene coda JSON da tagliare al primo `{`; le coppie venditore stanno in `offer-display-feature-name` / `offer-display-feature-text-message`, con etichetta `Venditore` oppure `Speditore / Venditore`.

```python
ACQUISTABILE = "ACQUISTABILE"
NON_ACQUISTABILE = "NON_ACQUISTABILE"
SCONOSCIUTO = "SCONOSCIUTO"

NEGATIVI = ("su invito", "non disponibile", "attualmente non disponibile")
SOGLIA_PAGINA_VALIDA = 50_000

@dataclass
class Esito:
    stato: str
    titolo: str | None = None
    prezzo: str | None = None
    venditore: str | None = None
    motivo: str = ""

def _testo(frammento: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", frammento)).split())

def e_bloccata(testo_html: str) -> bool:
    if len(testo_html) < SOGLIA_PAGINA_VALIDA:
        return True
    if "Continua con gli acquisti" in testo_html:
        return True
    return re.search(r"<title>", testo_html) is None

def analizza(testo_html: str) -> Esito:
    if e_bloccata(testo_html):
        return Esito(SCONOSCIUTO, motivo="pagina anti-bot o risposta troncata")
    titolo = _titolo(testo_html)
    disponibilita = _disponibilita(testo_html)
    venditore = _venditore(testo_html)
    prezzo = _prezzo(testo_html)
    compra_subito = "buy-now-button" in testo_html
    base = dict(titolo=titolo, prezzo=prezzo, venditore=venditore)

    negativo = next((n for n in NEGATIVI if n in (disponibilita or "").lower()), None)
    if negativo:
        return Esito(NON_ACQUISTABILE, motivo=f"disponibilita: {disponibilita}", **base)
    if not compra_subito:
        return Esito(NON_ACQUISTABILE, motivo="manca il pulsante Acquista ora", **base)
    if not venditore or not venditore.startswith("Amazon"):
        return Esito(NON_ACQUISTABILE, motivo=f"venditore terzo: {venditore}", **base)
    if not prezzo:
        return Esito(NON_ACQUISTABILE, motivo="prezzo non leggibile", **base)
    return Esito(ACQUISTABILE, motivo=f"acquistabile a {prezzo}", **base)
```

Funzioni di estrazione, tutte tolleranti al fallimento (`None` invece di eccezione):

```python
def _titolo(t):
    m = re.search(r"<title>([^<]*)</title>", t)
    return html.unescape(m.group(1)).split(" : Amazon")[0].strip() if m else None

def _disponibilita(t):
    m = re.search(r'id="availability"[^>]*>(.*?)</div>', t, re.S)
    if not m:
        return None
    return _testo(m.group(1)).split("{")[0].strip() or None

def _venditore(t):
    m = re.search(r'id="offer-display-features".*?(?=id="desktop_qualifiedBuyBox"|id="addToCart")', t, re.S)
    segmento = m.group(0) if m else t
    for blocco in re.finditer(
        r"offer-display-feature-name[^>]*>(.*?)</div>.*?offer-display-feature-text-message[^>]*>(.*?)</span>",
        segmento, re.S):
        nome = _testo(blocco.group(1))
        if "Venditore" in nome:
            return _testo(blocco.group(2)) or None
    return None

def _prezzo(t):
    m = re.search(r'class="a-price-whole">([\d.]+)', t)
    if not m:
        return None
    f = re.search(r'class="a-price-fraction">(\d+)', t)
    return f"{m.group(1)},{f.group(1) if f else '00'} EUR"
```

- [ ] **Step 5: Verificare che i test passino**

Run: `python -m pytest tests/test_amazon.py -v`
Expected: 6 passed. Se `test_prodotto_venduto_da_amazon_e_acquistabile` fallisce sul prezzo, ispezionare la fixture e correggere `_prezzo`, non allentare l'asserzione.

- [ ] **Step 6: Commit**

```bash
git add amazon.py tests/test_amazon.py tests/fixtures/nondisponibile_sintetica.html
git commit -m "Parser disponibilita Amazon con test su pagine reali"
```

---

### Task 2: Scaricamento con retry e rilevamento blocco

**Files:**
- Modify: `amazon.py`
- Modify: `tests/test_amazon.py`

**Interfaces:**
- Consumes: `analizza`, `e_bloccata` dal Task 1.
- Produces:
  - `sessione() -> requests.Session`
  - `scarica(asin: str, sess, tentativi: int = 3, pausa: float = 5.0, dormi=time.sleep) -> str | None`
  - `controlla(asin: str, sess, **kw) -> Esito`
  - `url_prodotto(asin: str) -> str`

- [ ] **Step 1: Scrivere i test che falliscono**

Il retry si testa con una sessione finta: nessuna rete nei test.

```python
from amazon import scarica, url_prodotto

class SessioneFinta:
    def __init__(self, risposte): self.risposte = list(risposte); self.chiamate = 0
    def get(self, url, timeout=None, headers=None):
        self.chiamate += 1
        corpo, codice = self.risposte.pop(0)
        class R: pass
        r = R(); r.text = corpo; r.status_code = codice
        return r

def test_url_canonico():
    assert url_prodotto("B0H9HFPRRD") == "https://www.amazon.it/dp/B0H9HFPRRD"

def test_riprova_dopo_blocco_e_riesce():
    buona = leggi("invito_B0H9HFPRRD.html")
    sess = SessioneFinta([("<html>bloccato</html>", 200), (buona, 200)])
    assert scarica("X", sess, dormi=lambda s: None) == buona
    assert sess.chiamate == 2

def test_ritorna_none_se_sempre_bloccato():
    sess = SessioneFinta([("corto", 200)] * 3)
    assert scarica("X", sess, tentativi=3, dormi=lambda s: None) is None

def test_http_503_conta_come_blocco():
    sess = SessioneFinta([("", 503), (leggi("invito_B0H9HFPRRD.html"), 200)])
    assert scarica("X", sess, dormi=lambda s: None) is not None
```

- [ ] **Step 2: Verificare che falliscano**

Run: `python -m pytest tests/test_amazon.py -v`
Expected: FAIL, `ImportError: cannot import name 'scarica'`

- [ ] **Step 3: Implementare**

```python
UA = [
 "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
 "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
 "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

def url_prodotto(asin): return f"https://www.amazon.it/dp/{asin}"

def sessione():
    s = requests.Session()
    s.headers.update({"Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
                      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                      "Upgrade-Insecure-Requests": "1"})
    return s

def scarica(asin, sess, tentativi=3, pausa=5.0, dormi=time.sleep):
    for i in range(tentativi):
        try:
            r = sess.get(url_prodotto(asin), timeout=30,
                         headers={"User-Agent": UA[i % len(UA)]})
            if r.status_code == 200 and not e_bloccata(r.text):
                return r.text
        except Exception:
            pass
        if i < tentativi - 1:
            dormi(pausa)
    return None

def controlla(asin, sess, **kw):
    testo = scarica(asin, sess, **kw)
    if testo is None:
        return Esito(SCONOSCIUTO, motivo="bloccato dopo tutti i tentativi")
    return analizza(testo)
```

- [ ] **Step 4: Verificare che i test passino**

Run: `python -m pytest tests/test_amazon.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add amazon.py tests/test_amazon.py
git commit -m "Scaricamento con retry, rotazione User-Agent e rilevamento blocco"
```

---

### Task 3: Stato persistente e transizioni

**Files:**
- Create: `stato.py`
- Create: `tests/test_stato.py`

**Interfaces:**
- Consumes: costanti di stato da `amazon.py`.
- Produces:
  - `carica(percorso: Path) -> dict`
  - `salva(percorso: Path, dati: dict) -> None`
  - `transizione(precedente: str | None, nuovo: str) -> str | None` che ritorna `"RESTOCK"`, `"ESAURITO"` o `None`.

- [ ] **Step 1: Scrivere i test che falliscono**

```python
import json
from stato import carica, salva, transizione
from amazon import ACQUISTABILE, NON_ACQUISTABILE, SCONOSCIUTO

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
```

- [ ] **Step 2: Verificare che falliscano**

Run: `python -m pytest tests/test_stato.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'stato'`

- [ ] **Step 3: Implementare `stato.py`**

```python
def carica(percorso):
    try:
        return json.loads(Path(percorso).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def salva(percorso, dati):
    p = Path(percorso)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(dati, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)

def transizione(precedente, nuovo):
    if nuovo == SCONOSCIUTO:
        return None
    if nuovo == precedente:
        return None
    if nuovo == ACQUISTABILE:
        return "RESTOCK"
    if precedente in (ACQUISTABILE,):
        return "ESAURITO"
    return None
```

- [ ] **Step 4: Verificare che i test passino**

Run: `python -m pytest tests/test_stato.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add stato.py tests/test_stato.py
git commit -m "Stato persistente e regole di transizione"
```

---

### Task 4: Notifiche Telegram

**Files:**
- Create: `notifiche.py`
- Create: `tests/test_notifiche.py`

**Interfaces:**
- Consumes: `Esito`, `url_prodotto` da `amazon.py`.
- Produces:
  - `class Telegram(token, chat_id, sess=None)` con `invia(testo, silenzioso=False) -> bool` e `comandi() -> list[str]`
  - `messaggio_restock(asin, esito) -> str`
  - `messaggio_esaurito(asin, esito) -> str`
  - `leggi_credenziali(cartella: Path) -> tuple[str|None, str|None]` che legge da variabili d'ambiente e, se assenti, da `.env`.

- [ ] **Step 1: Scrivere i test che falliscono**

```python
from notifiche import messaggio_restock, messaggio_esaurito, leggi_credenziali
from amazon import Esito, ACQUISTABILE

def test_messaggio_restock_contiene_link_canonico():
    e = Esito(ACQUISTABILE, titolo="Set Allenatore", prezzo="54,99 EUR", venditore="Amazon")
    m = messaggio_restock("B0H9HFPRRD", e)
    assert "https://www.amazon.it/dp/B0H9HFPRRD" in m
    assert "amzn.eu" not in m
    assert "54,99" in m
    assert "Set Allenatore" in m

def test_messaggio_esaurito_e_breve():
    e = Esito("NON_ACQUISTABILE", titolo="Set Allenatore")
    m = messaggio_esaurito("B0H9HFPRRD", e)
    assert "Set Allenatore" in m
    assert len(m) < 300

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
```

- [ ] **Step 2: Verificare che falliscano**

Run: `python -m pytest tests/test_notifiche.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'notifiche'`

- [ ] **Step 3: Implementare `notifiche.py`**

I messaggi usano `parse_mode=HTML` e il link va in chiaro perché Telegram lo renda toccabile.

```python
def messaggio_restock(asin, esito):
    return ("\U0001F6A8 <b>DISPONIBILE ORA</b>\n\n"
            f"{html.escape(esito.titolo or asin)}\n"
            f"Prezzo: <b>{esito.prezzo or 'n/d'}</b>\n"
            f"Venditore: {esito.venditore or 'n/d'}\n\n"
            f"{url_prodotto(asin)}\n\n"
            f"<i>{datetime.now().strftime('%d/%m %H:%M:%S')}</i>")

def messaggio_esaurito(asin, esito):
    return (f"⚪ Finito: {html.escape(esito.titolo or asin)}\n"
            f"{url_prodotto(asin)}")
```

`Telegram.invia` usa `sendMessage` con `disable_notification=silenzioso` e non solleva mai: ritorna `False` in caso di errore, perché un guasto di Telegram non deve fermare il monitoraggio.

`Telegram.comandi` usa `getUpdates` con `offset` memorizzato e `timeout=0`, ritorna la lista dei testi comando ricevuti.

- [ ] **Step 4: Verificare che i test passino**

Run: `python -m pytest tests/test_notifiche.py -v`
Expected: 4 passed.

- [ ] **Step 5: Verifica dal vivo**

Run: `python monitor.py --test-telegram` (dopo il Task 5) e controllare che il messaggio arrivi in chat.

- [ ] **Step 6: Commit**

```bash
git add notifiche.py tests/test_notifiche.py
git commit -m "Notifiche Telegram e lettura credenziali"
```

---

### Task 5: Ciclo di controllo e interfaccia a riga di comando

**Files:**
- Create: `monitor.py`
- Create: `config.json`
- Create: `tests/test_monitor.py`

**Interfaces:**
- Consumes: tutti i moduli precedenti.
- Produces:
  - `giro(cfg, sess, tg, dati_stato, dry_run=False) -> dict` con il riepilogo del giro
  - `main(argv) -> int`
  - Flag CLI: `--once`, `--dry-run`, `--test-telegram`, `--selftest`, `--durata-min N`

- [ ] **Step 1: Scrivere `config.json`**

```json
{
  "prodotti": [
    {"asin": "B0H9HFPRRD", "nome": "Set Allenatore Fuoriclasse 30 Anniversario"},
    {"asin": "B0H9HDZN97", "nome": "Scatola da collezione Greninja-ex"},
    {"asin": "B0H9HGQSWR", "nome": "Scatola da collezione Sylveon-ex"},
    {"asin": "B0H9HPCL27", "nome": "Confezione da due buste"},
    {"asin": "B0H9HBQKF3", "nome": "Collezione Greninja-ex"},
    {"asin": "B0H9HJQ1Z9", "nome": "Collezione Sylveon-ex"},
    {"asin": "B0H99Z9XPG", "nome": "Collezione con raccoglitore"}
  ],
  "canarino": "B00LH3DMUO",
  "ogni_quanti_giri_canarino": 10,
  "intervallo_ciclo_s": 60,
  "pausa_tra_prodotti_s": 6,
  "tentativi_per_prodotto": 3,
  "pausa_retry_s": 5,
  "minuti_cecita_avviso": 15,
  "cooldown_avvisi_tecnici_min": 60
}
```

- [ ] **Step 2: Scrivere i test del giro che falliscono**

Il giro si testa con controllore finto: nessuna rete.

```python
from monitor import giro
from amazon import Esito, ACQUISTABILE, NON_ACQUISTABILE, SCONOSCIUTO

class TelegramFinto:
    def __init__(self): self.inviati = []
    def invia(self, testo, silenzioso=False): self.inviati.append(testo); return True

CFG = {"prodotti": [{"asin": "B01", "nome": "Uno"}], "canarino": None,
       "ogni_quanti_giri_canarino": 0, "pausa_tra_prodotti_s": 0,
       "tentativi_per_prodotto": 1, "pausa_retry_s": 0, "minuti_cecita_avviso": 15,
       "cooldown_avvisi_tecnici_min": 60}

def test_restock_invia_un_avviso():
    tg = TelegramFinto(); dati = {"B01": {"stato": NON_ACQUISTABILE}}
    giro(CFG, None, tg, dati, controllore=lambda a, s, **k: Esito(ACQUISTABILE, "Uno", "10 EUR", "Amazon"))
    assert len(tg.inviati) == 1 and "DISPONIBILE ORA" in tg.inviati[0]
    assert dati["B01"]["stato"] == ACQUISTABILE

def test_stato_invariato_non_invia_nulla():
    tg = TelegramFinto(); dati = {"B01": {"stato": ACQUISTABILE}}
    giro(CFG, None, tg, dati, controllore=lambda a, s, **k: Esito(ACQUISTABILE, "Uno", "10 EUR", "Amazon"))
    assert tg.inviati == []

def test_blocco_non_invia_e_non_sovrascrive_lo_stato():
    tg = TelegramFinto(); dati = {"B01": {"stato": ACQUISTABILE}}
    giro(CFG, None, tg, dati, controllore=lambda a, s, **k: Esito(SCONOSCIUTO))
    assert tg.inviati == []
    assert dati["B01"]["stato"] == ACQUISTABILE

def test_dry_run_non_invia():
    tg = TelegramFinto(); dati = {"B01": {"stato": NON_ACQUISTABILE}}
    giro(CFG, None, tg, dati, dry_run=True,
         controllore=lambda a, s, **k: Esito(ACQUISTABILE, "Uno", "10 EUR", "Amazon"))
    assert tg.inviati == []
```

- [ ] **Step 3: Verificare che falliscano**

Run: `python -m pytest tests/test_monitor.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'monitor'`

- [ ] **Step 4: Implementare `monitor.py`**

`giro` accetta un parametro `controllore` con default `amazon.controlla`: è ciò che rende il ciclo testabile senza rete. Per ogni prodotto: controlla, calcola la transizione, invia se necessario, aggiorna lo stato solo se non è `SCONOSCIUTO`, rispetta `pausa_tra_prodotti_s`.

Il ciclo principale gira finché non scade `--durata-min` (default 55, per allinearsi al riavvio orario dei workflow), dorme per il tempo residuo fino a `intervallo_ciclo_s`, legge i comandi Telegram a fine giro e risponde a `/status` e `/lista`.

Sorveglianza tecnica: se tutti i prodotti risultano `SCONOSCIUTO` per più di `minuti_cecita_avviso` consecutivi, invia una volta l'avviso di cecità, poi tace per `cooldown_avvisi_tecnici_min`. Se il canarino risulta non acquistabile, invia l'avviso di parser rotto con lo stesso cooldown.

- [ ] **Step 5: Verificare che i test passino**

Run: `python -m pytest tests/ -v`
Expected: tutti verdi (22 test).

- [ ] **Step 6: Giro reale in sola lettura**

Run: `python monitor.py --once --dry-run`
Expected: elenca i 7 prodotti con stato `NON_ACQUISTABILE` e motivo `disponibilita: Disponibile su invito`, senza inviare nulla.

- [ ] **Step 7: Commit**

```bash
git add monitor.py config.json tests/test_monitor.py
git commit -m "Ciclo di controllo, CLI e sorveglianza tecnica"
```

---

### Task 6: Fase 1 — attivazione sul PC

Rende il bot operativo subito, senza alcuna azione dell'utente.

**Files:**
- Create: `.env`
- Create: `avvia.cmd`
- Create: `installa_task_windows.ps1`

- [ ] **Step 1: Scrivere `.env` con le credenziali del bot esistente**

Copiare `TG_BOT_TOKEN` e `TG_CHAT_ID` da `../iphone 17/.env`. Il file è già in `.gitignore`.

- [ ] **Step 2: Verificare la consegna del messaggio**

Run: `python monitor.py --test-telegram`
Expected: messaggio ricevuto in chat Telegram.

- [ ] **Step 3: Scrivere `avvia.cmd`**

```bat
@echo off
cd /d "%~dp0"
python monitor.py --durata-min 55 >> monitor.log 2>&1
```

- [ ] **Step 4: Scrivere e lanciare `installa_task_windows.ps1`**

Task oraria che riavvia il ciclo, con `-StartWhenAvailable` per recuperare i riavvii del PC:

```powershell
$azione = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$PSScriptRoot\avvia.cmd`"" -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)
$impostazioni = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName "PokePoke-Monitor" -Action $azione -Trigger $trigger -Settings $impostazioni -Force
```

- [ ] **Step 5: Verificare che il task sia attivo**

Run: `Get-ScheduledTask -TaskName "PokePoke-Monitor"` e controllare `monitor.log` dopo qualche minuto.

- [ ] **Step 6: Commit**

```bash
git add avvia.cmd installa_task_windows.ps1
git commit -m "Fase 1: avvio automatico sul PC tramite task di Windows"
```

---

### Task 7: Fase 2 — workflow GitHub Actions e documentazione

Pronti all'uso ma inerti finché l'utente non collega la repo a GitHub.

**Files:**
- Create: `.github/workflows/watch-pc.yml`
- Create: `.github/workflows/watch-cloud.yml`
- Create: `requirements.txt`
- Create: `README.md`

- [ ] **Step 1: Scrivere `requirements.txt`**

```
requests>=2.31
```

- [ ] **Step 2: Scrivere `watch-pc.yml`**

Cron orario su `runs-on: self-hosted`, `concurrency` per non sovrapporre, `--durata-min 55`, secrets `TG_BOT_TOKEN` e `TG_CHAT_ID` passati come variabili d'ambiente.

- [ ] **Step 3: Scrivere `watch-cloud.yml`**

Identico ma su `ubuntu-latest` e con `MODO=cloud`: prima di ogni giro interroga `GET /repos/{owner}/{repo}/actions/runners` con `PAT_RUNNERS`; se un runner self-hosted risulta `online` e `busy`, salta il giro senza contattare Amazon.

- [ ] **Step 4: Scrivere `README.md`**

Deve coprire: cosa fa il bot, i 7 prodotti, come si legge `config.json`, i comandi `/status` e `/lista`, come si attiva la fase 2 (creazione repo pubblica, tre secrets, installazione del runner self-hosted su Windows come servizio), e come si sostituisce il bot condiviso con uno dedicato creato con BotFather.

- [ ] **Step 5: Verificare la sintassi YAML**

Run: `python -c "import yaml,glob; [yaml.safe_load(open(f, encoding='utf-8')) for f in glob.glob('.github/workflows/*.yml')]; print('yaml ok')"`
Expected: `yaml ok`

- [ ] **Step 6: Commit**

```bash
git add .github requirements.txt README.md
git commit -m "Fase 2: workflow GitHub Actions e documentazione di attivazione"
```

---

## Self-Review

**Copertura della spec.** Obiettivo e prodotti: Task 5 (`config.json`). Trigger acquistabile da Amazon: Task 1. Frequenza 60s: Task 5. Architettura ibrida e leadership via API GitHub: Task 7. Rilevamento disponibilità e canarino: Task 1 e Task 5. Gestione blocchi e stato `SCONOSCIUTO`: Task 1, 2, 3. Notifiche e comandi: Task 4 e Task 5. Stato persistente: Task 3. Test su fixture reali: Task 1. Fase 1 senza azione utente: Task 6. Nessun requisito della spec resta scoperto.

**Placeholder.** Nessun "TBD" o "gestire gli errori in modo appropriato": ogni passo di codice riporta il codice o, dove il corpo è meccanico (`Telegram.invia`, il ciclo di `monitor.py`, i due YAML), la descrizione esatta di comportamento, firme e nomi.

**Coerenza dei tipi.** `Esito` ha gli stessi cinque campi in tutti i task. `transizione` ritorna `"RESTOCK"`, `"ESAURITO"` o `None` sia nel Task 3 che nel Task 5. `controlla(asin, sess, **kw)` ha la stessa firma nel Task 2 e nel parametro `controllore` del Task 5. `url_prodotto` è definita una volta nel Task 2 e usata nel Task 4.

Lo scostamento dalla spec è uno solo e deliberato: la spec elencava un unico `monitor.py`, il piano lo divide in quattro moduli a responsabilità singola. Il comportamento è identico e i confini sono più facili da testare.
