#!/usr/bin/env python3
"""Monitor di disponibilita Amazon.it con avviso Telegram.

Uso:
    python monitor.py --selftest        verifica il parser su pagine salvate, offline
    python monitor.py --test-telegram   manda un messaggio di prova
    python monitor.py --once --dry-run  un giro solo, senza inviare nulla
    python monitor.py --once            un giro solo
    python monitor.py                   ciclo continuo (default 55 minuti)

Credenziali attese come variabili d'ambiente o nel file .env accanto allo
script:
    TG_BOT_TOKEN=123456:ABC...
    TG_CHAT_ID=123456789
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import amazon
import leader
import stato as stato_mod
from amazon import ACQUISTABILE, NON_ACQUISTABILE, SCONOSCIUTO, Esito
from notifiche import Telegram, leggi_credenziali, messaggio_esaurito, messaggio_restock

BASE = Path(__file__).resolve().parent
CONFIG = BASE / "config.json"
STATO = BASE / "state.json"


REGISTRO = BASE / "monitor.log"


def log(*parti):
    """Scrive su schermo e su monitor.log.

    Il file viene aperto e chiuso a ogni riga di proposito. Tenendolo aperto
    per tutta la vita del processo, come farebbe un redirect del prompt, una
    seconda istanza non riuscirebbe nemmeno ad aprirlo e morirebbe muta: il
    caso che conta di piu da vedere nel registro (una partenza doppia) sarebbe
    l'unico invisibile.
    """
    riga = " ".join([datetime.now().strftime("%H:%M:%S"), *(str(p) for p in parti)])
    print(riga, flush=True)
    try:
        with open(REGISTRO, "a", encoding="utf-8") as f:
            f.write(riga + "\n")
    except OSError:
        pass


def leggi_config(percorso=CONFIG) -> dict:
    return json.loads(Path(percorso).read_text(encoding="utf-8"))


def istanza_unica(porta: int):
    """Impedisce che due monitor girino insieme.

    Il task di Windows parte ogni 5 minuti: cosi, se il PC si riavvia o il
    processo muore, il monitoraggio riprende in fretta. Ma se un'istanza sta
    gia lavorando, la nuova deve farsi da parte. Un socket in ascolto e il
    lucchetto piu semplice che il sistema operativo rilascia da solo quando
    il processo termina, anche se termina male.

    Ritorna il socket (da tenere vivo) oppure None se un'altra istanza c'e gia.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", porta))
        s.listen(1)
        return s
    except OSError:
        s.close()
        return None


# --- un giro di controllo ---------------------------------------------------


def giro(cfg, sess, tg, dati, dry_run=False, controllore=None, dormi=time.sleep) -> dict:
    """Controlla tutti i prodotti una volta, invia gli avvisi dovuti e
    aggiorna lo stato. Ritorna un riepilogo del giro.

    `controllore` esiste per i test: di default e la funzione che va davvero
    in rete, nei test e una funzione che restituisce esiti finti.
    """
    controllore = controllore or amazon.controlla
    riepilogo = {"letti": 0, "sconosciuti": 0, "acquistabili": [], "dettagli": []}
    prodotti = cfg["prodotti"]

    for indice, prodotto in enumerate(prodotti):
        asin = prodotto["asin"]
        esito = controllore(
            asin,
            sess,
            tentativi=cfg.get("tentativi_per_prodotto", 3),
            pausa=cfg.get("pausa_retry_s", 5),
        )
        if not esito.titolo:
            esito.titolo = prodotto.get("nome", asin)

        precedente = dati.get(asin, {}).get("stato")
        evento = stato_mod.transizione(precedente, esito.stato)

        if evento == stato_mod.RESTOCK and not dry_run:
            tg.invia(messaggio_restock(asin, esito))
        elif evento == stato_mod.ESAURITO and not dry_run:
            tg.invia(messaggio_esaurito(asin, esito), silenzioso=True)

        if esito.stato == SCONOSCIUTO:
            riepilogo["sconosciuti"] += 1
        else:
            riepilogo["letti"] += 1
            dati[asin] = {
                "stato": esito.stato,
                "titolo": esito.titolo,
                "prezzo": esito.prezzo,
                "motivo": esito.motivo,
                "aggiornato": datetime.now().isoformat(timespec="seconds"),
            }
            if esito.stato == ACQUISTABILE:
                riepilogo["acquistabili"].append(asin)

        riepilogo["dettagli"].append((asin, esito))
        log(f"  {asin} {esito.stato:17} {esito.motivo[:60]}")

        pausa = cfg.get("pausa_tra_prodotti_s", 6)
        if pausa and indice < len(prodotti) - 1:
            dormi(pausa)

    return riepilogo


# --- sorveglianza tecnica ---------------------------------------------------


class Sorveglianza:
    """Tiene d'occhio il monitor stesso: se smettiamo di vedere Amazon, o se
    il parser si rompe, il silenzio sarebbe il fallimento peggiore."""

    def __init__(self, cfg, tg, dry_run=False):
        self.cfg = cfg
        self.tg = tg
        self.dry_run = dry_run
        self.cieco_da = None
        self.ultimo_avviso = {}

    def _avvisa(self, chiave, testo):
        cooldown = timedelta(minutes=self.cfg.get("cooldown_avvisi_tecnici_min", 60))
        ultimo = self.ultimo_avviso.get(chiave)
        if ultimo and datetime.now() - ultimo < cooldown:
            return
        self.ultimo_avviso[chiave] = datetime.now()
        log("AVVISO TECNICO:", testo)
        if not self.dry_run:
            self.tg.invia(f"⚠️ {testo}")

    def dopo_giro(self, riepilogo):
        tutti_ciechi = riepilogo["letti"] == 0 and riepilogo["sconosciuti"] > 0
        if not tutti_ciechi:
            self.cieco_da = None
            return
        if self.cieco_da is None:
            self.cieco_da = datetime.now()
            return
        minuti = (datetime.now() - self.cieco_da).total_seconds() / 60
        if minuti >= self.cfg.get("minuti_cecita_avviso", 15):
            self._avvisa(
                "cecita",
                f"Non riesco a leggere Amazon da {int(minuti)} minuti. "
                "Gli avvisi di disponibilita potrebbero non arrivare.",
            )

    def controlla_canarino(self, sess, controllore=None):
        """Il canarino e un prodotto sempre disponibile e venduto da Amazon.
        Se risulta non acquistabile non e il mercato a essere cambiato, e il
        parser a essersi rotto perche Amazon ha cambiato l'HTML."""
        asin = self.cfg.get("canarino")
        if not asin:
            return None
        controllore = controllore or amazon.controlla
        esito = controllore(asin, sess, tentativi=self.cfg.get("tentativi_per_prodotto", 3),
                            pausa=self.cfg.get("pausa_retry_s", 5))
        if esito.stato == SCONOSCIUTO:
            return None
        if esito.stato != ACQUISTABILE:
            self._avvisa(
                "canarino",
                f"Il prodotto di controllo {asin} risulta non acquistabile "
                f"({esito.motivo}). Probabile parser da aggiornare.",
            )
            return False
        log(f"  canarino {asin} ok")
        return True


# --- comandi ----------------------------------------------------------------


def rispondi_comandi(tg, cfg, dati, avvio, ultimo_riepilogo):
    for comando in tg.comandi():
        if comando == "/status":
            minuti = int((datetime.now() - avvio).total_seconds() / 60)
            letti = ultimo_riepilogo.get("letti", 0) if ultimo_riepilogo else 0
            sconosciuti = ultimo_riepilogo.get("sconosciuti", 0) if ultimo_riepilogo else 0
            tg.invia(
                f"<b>Stato monitor</b>\nAttivo da {minuti} min\n"
                f"Ultimo giro: {letti} letti, {sconosciuti} non leggibili\n"
                f"Prodotti monitorati: {len(cfg['prodotti'])}",
                silenzioso=True,
            )
        elif comando in ("/lista", "/list"):
            righe = []
            for prodotto in cfg["prodotti"]:
                voce = dati.get(prodotto["asin"], {})
                simbolo = "🟢" if voce.get("stato") == ACQUISTABILE else "⚪"
                righe.append(f"{simbolo} {prodotto['nome']}")
            tg.invia("<b>Prodotti</b>\n" + "\n".join(righe), silenzioso=True)


# --- selftest ---------------------------------------------------------------


def selftest() -> int:
    """Verifica il parser su pagine reali salvate. Non tocca la rete, cosi
    si puo lanciare ovunque, anche dove pytest non e installato."""
    attesi = {
        "invito_B0H9HFPRRD.html": NON_ACQUISTABILE,
        "acquistabile_amazon_B00LH3DMUO.html": ACQUISTABILE,
        "terzi_acquistabile_B0F8VZ7QVX.html": NON_ACQUISTABILE,
        "blocco_antibot.html": SCONOSCIUTO,
        "nondisponibile_sintetica.html": NON_ACQUISTABILE,
    }
    cartella = BASE / "tests" / "fixtures"
    errori = 0
    for nome, atteso in attesi.items():
        percorso = cartella / nome
        if not percorso.exists():
            print(f"MANCA  {nome}")
            errori += 1
            continue
        esito = amazon.analizza(percorso.read_text(encoding="utf-8", errors="ignore"))
        ok = esito.stato == atteso
        errori += 0 if ok else 1
        print(f"{'ok   ' if ok else 'ERRORE'} {nome}: {esito.stato} (atteso {atteso})")
    print("selftest superato" if errori == 0 else f"selftest fallito: {errori} errori")
    return 0 if errori == 0 else 1


# --- avvio ------------------------------------------------------------------


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Monitor disponibilita Amazon.it")
    p.add_argument("--once", action="store_true", help="un solo giro, poi esci")
    p.add_argument("--dry-run", action="store_true", help="non inviare messaggi")
    p.add_argument("--test-telegram", action="store_true", help="manda un messaggio di prova")
    p.add_argument("--selftest", action="store_true", help="verifica il parser, offline")
    p.add_argument("--durata-min", type=int, default=55, help="minuti di esecuzione")
    p.add_argument(
        "--cede-al-pc",
        action="store_true",
        help="salta il giro se il runner sul PC sta gia lavorando (uso cloud)",
    )
    args = p.parse_args(argv)

    if args.selftest:
        return selftest()

    cfg = leggi_config()
    token, chat_id = leggi_credenziali(BASE)
    if not token or not chat_id:
        print("Mancano TG_BOT_TOKEN e TG_CHAT_ID (ambiente o .env).", file=sys.stderr)
        return 2
    tg = Telegram(token, chat_id)

    if args.test_telegram:
        ok = tg.invia("✅ Monitor Amazon: prova di collegamento riuscita.")
        print("messaggio inviato" if ok else "invio fallito")
        return 0 if ok else 1

    lucchetto = None
    if not args.once:
        lucchetto = istanza_unica(cfg.get("porta_lucchetto", 47653))
        if lucchetto is None:
            log("un altro monitor sta gia girando, esco")
            return 0

    dati = stato_mod.carica(STATO)
    sess = amazon.sessione()
    sorveglianza = Sorveglianza(cfg, tg, dry_run=args.dry_run)
    avvio = datetime.now()
    scadenza = avvio + timedelta(minutes=args.durata_min)
    numero_giro = 0
    ultimo_riepilogo = None

    log(f"avvio: {len(cfg['prodotti'])} prodotti, ciclo {cfg['intervallo_ciclo_s']}s"
        f"{' (dry-run)' if args.dry_run else ''}")

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token_runner = os.environ.get("PAT_RUNNERS", "")

    while True:
        numero_giro += 1
        inizio = time.monotonic()

        # Il runner cloud non tocca Amazon finche il PC copre: due
        # controllori insieme raddoppierebbero le richieste e quindi i blocchi.
        if args.cede_al_pc and leader.pc_attivo(repo, token_runner):
            log(f"giro {numero_giro}: il PC sta lavorando, cedo")
            if args.once or datetime.now() >= scadenza:
                break
            time.sleep(cfg.get("intervallo_ciclo_s", 60))
            continue

        log(f"giro {numero_giro}")
        ultimo_riepilogo = giro(cfg, sess, tg, dati, dry_run=args.dry_run)
        stato_mod.salva(STATO, dati)
        sorveglianza.dopo_giro(ultimo_riepilogo)

        ogni = cfg.get("ogni_quanti_giri_canarino", 0)
        if ogni and numero_giro % ogni == 0:
            sorveglianza.controlla_canarino(sess)

        if not args.dry_run:
            rispondi_comandi(tg, cfg, dati, avvio, ultimo_riepilogo)

        if args.once or datetime.now() >= scadenza:
            break

        resto = cfg.get("intervallo_ciclo_s", 60) - (time.monotonic() - inizio)
        if resto > 0:
            time.sleep(resto)

    log("fine")
    return 0


if __name__ == "__main__":
    # Lo schianto va nel registro: avvia.cmd non reindirizza nulla su file,
    # quindi senza questo una traccia di stack andrebbe persa.
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:
        import traceback

        log("SCHIANTO:\n" + traceback.format_exc())
        raise
