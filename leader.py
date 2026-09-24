"""Chi dei due esecutori deve lavorare.

Il runner sul PC ha un IP residenziale e viene bloccato da Amazon molto meno
di un runner cloud. Quindi e lui la fonte primaria, e il runner cloud si fa
da parte finche il PC sta lavorando.

Non serve nessun protocollo di elezione: basta chiedere a GitHub se il runner
self-hosted risulta online e occupato. Cosi c'e sempre al massimo un
controllore attivo e nessun avviso doppio.
"""

from __future__ import annotations

import requests

API = "https://api.github.com/repos/{repo}/actions/runners"


def pc_attivo(repo: str, token: str, sess=None) -> bool:
    """Vero se un runner self-hosted sta eseguendo un job in questo momento.

    In caso di dubbio ritorna False, cioe "il PC non copre, lavora tu". Una
    risposta mancante puo dipendere da un token scaduto o da GitHub lento:
    in quel caso due controllori attivi producono al massimo un avviso
    doppio, mentre zero controllori attivi fanno perdere il restock. Fra i
    due errori possibili si sceglie sempre il meno costoso.
    """
    if not repo or not token:
        return False
    sess = sess or requests
    try:
        r = sess.get(
            API.format(repo=repo),
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=15,
        )
        if r.status_code != 200:
            return False
        for runner in r.json().get("runners", []):
            if runner.get("status") == "online" and runner.get("busy"):
                return True
        return False
    except Exception:
        return False
