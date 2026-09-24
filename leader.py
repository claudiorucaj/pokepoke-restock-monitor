"""Chi dei due esecutori deve lavorare.

Il runner sul PC ha un IP residenziale e viene bloccato da Amazon molto meno
di un runner cloud. Quindi e lui la fonte primaria, e il runner cloud si fa
da parte finche il PC sta lavorando.

Non serve nessun protocollo di elezione: basta chiedere a GitHub se il
workflow del PC ha un'esecuzione *in corso*. Se il PC e spento il suo job
resta in coda, non in esecuzione, e la differenza fra "queued" e
"in_progress" e esattamente il segnale che serve.

Si interroga l'elenco delle esecuzioni e non quello dei runner di proposito:
leggere i runner richiede un token con permesso Administration, mentre le
esecuzioni bastano i permessi che il token automatico di Actions puo gia
avere (actions: read). Un secret in meno da creare e da far scadere.
"""

from __future__ import annotations

import requests

API = "https://api.github.com/repos/{repo}/actions/workflows/{workflow}/runs"


def pc_attivo(repo: str, token: str, workflow: str = "watch-pc.yml", sess=None) -> bool:
    """Vero se il workflow del PC sta girando in questo momento.

    In caso di dubbio ritorna False, cioe "il PC non copre, lavora tu". Una
    risposta mancante puo dipendere da un token scaduto o da GitHub lento: in
    quel caso due controllori attivi producono al massimo un avviso doppio,
    mentre zero controllori attivi fanno perdere il restock. Fra i due errori
    possibili si sceglie sempre il meno costoso.
    """
    if not repo or not token:
        return False
    sess = sess or requests
    try:
        r = sess.get(
            API.format(repo=repo, workflow=workflow),
            params={"status": "in_progress", "per_page": 1},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=15,
        )
        if r.status_code != 200:
            return False
        return r.json().get("total_count", 0) > 0
    except Exception:
        return False
