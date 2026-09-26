#!/usr/bin/env python3
"""Guardiano della catena del monitor cloud.

Il workflow cloud si tiene in vita da solo: ogni run prenota il successivo.
Se la catena si spezza (un selftest fallito, un guasto di GitHub) nessun run
la riprende, e il silenzio che ne segue sembrerebbe "nessun restock" invece
di "nessuno sta guardando". Questo script, lanciato da un workflow separato,
controlla che ci sia un run del cloud in corso o in attesa; se non c'e,
avvisa su Telegram e ne lancia uno.

Uso (in GitHub Actions, con GITHUB_REPOSITORY, GITHUB_TOKEN, TG_BOT_TOKEN e
TG_CHAT_ID nell'ambiente):
    python guardiano.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

from notifiche import Telegram, leggi_credenziali

API = "https://api.github.com/repos/{repo}/actions/workflows/{workflow}"
WORKFLOW = "watch-cloud.yml"
VIVI = {"in_progress", "queued", "pending", "waiting", "requested"}


def _intestazioni(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def catena_viva(repo, token, workflow=WORKFLOW, sess=None) -> bool | None:
    """Vero se il workflow cloud ha un run in corso o in attesa, falso se
    sono tutti conclusi, None se GitHub non risponde.

    Nel dubbio non si decide: un falso allarme ogni dieci minuti insegnerebbe
    a ignorare quello vero, e un run lanciato in piu non serve a nulla se
    GitHub non risponde nemmeno a una lettura.
    """
    sess = sess or requests
    try:
        r = sess.get(
            API.format(repo=repo, workflow=workflow) + "/runs",
            params={"per_page": 10},
            headers=_intestazioni(token),
            timeout=15,
        )
        if r.status_code != 200:
            return None
        return any(run.get("status") in VIVI for run in r.json().get("workflow_runs", []))
    except Exception:
        return None


def rilancia(repo, token, ramo="master", workflow=WORKFLOW, sess=None) -> bool:
    sess = sess or requests
    try:
        r = sess.post(
            API.format(repo=repo, workflow=workflow) + "/dispatches",
            json={"ref": ramo},
            headers=_intestazioni(token),
            timeout=15,
        )
        return r.status_code == 204
    except Exception:
        return False


def sorveglia(repo, token, tg, ramo="master", sess=None) -> str:
    """Controlla la catena e la ripara se serve. Ritorna cosa ha trovato."""
    viva = catena_viva(repo, token, sess=sess)
    if viva is None:
        return "sconosciuto"
    if viva:
        return "viva"
    riuscito = rilancia(repo, token, ramo, sess=sess)
    tg.invia(
        "⚠️ Il monitor cloud si era fermato: per un po' nessuno ha controllato Amazon. "
        + ("L'ho fatto ripartire." if riuscito else "Non sono riuscito a farlo ripartire, serve un intervento.")
    )
    return "riavviata" if riuscito else "ferma"


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    ramo = os.environ.get("GITHUB_REF_NAME", "master")
    tg_token, chat_id = leggi_credenziali(Path(__file__).resolve().parent)
    if not repo or not token or not tg_token or not chat_id:
        print("Mancano GITHUB_REPOSITORY, GITHUB_TOKEN, TG_BOT_TOKEN o TG_CHAT_ID.", file=sys.stderr)
        return 2
    esito = sorveglia(repo, token, Telegram(tg_token, chat_id), ramo)
    print(f"catena: {esito}")
    return 1 if esito == "ferma" else 0


if __name__ == "__main__":
    raise SystemExit(main())
