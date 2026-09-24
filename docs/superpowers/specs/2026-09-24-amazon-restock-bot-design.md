# Bot Telegram: avviso restock Amazon.it (Pokémon GCC 30° Anniversario)

Data: 2026-09-24
Stato: approvato dall'utente, implementazione autorizzata in autonomia

## Obiettivo

Ricevere su Telegram un avviso immediato, con il link ufficiale Amazon, nel momento
in cui uno dei 7 prodotti monitorati diventa acquistabile direttamente da Amazon.

## Prodotti monitorati

Tutti su amazon.it. Al 2026-09-24 sono tutti nello stato "Disponibile su invito".

| ASIN | Prodotto |
|---|---|
| B0H9HFPRRD | Set Allenatore Fuoriclasse 30° Anniversario |
| B0H9HDZN97 | Scatola da collezione Greninja-ex |
| B0H9HGQSWR | Scatola da collezione Sylveon-ex |
| B0H9HPCL27 | Confezione da due buste |
| B0H9HBQKF3 | Collezione Greninja-ex |
| B0H9HJQ1Z9 | Collezione Sylveon-ex |
| B0H99Z9XPG | Collezione con raccoglitore |

Il link notificato è sempre la forma canonica `https://www.amazon.it/dp/<ASIN>`,
non lo short link `amzn.eu` (che contiene parametri di tracciamento della condivisione).

## Decisioni prese con l'utente

1. **Trigger**: avviso solo quando il prodotto è acquistabile e venduto da Amazon.
   Niente avvisi per venditori terzi o prezzi gonfiati.
2. **Frequenza**: un ciclo completo dei 7 prodotti ogni ~60 secondi.
3. **Copertura**: 24/7 obbligatoria, indipendente dal PC acceso. Da cui l'architettura ibrida.
4. **Bot Telegram**: previsto un bot dedicato; in attesa che l'utente lo crei si usa
   il bot già esistente e funzionante `@alertprezzoiphone17bot`, così il servizio è
   operativo senza alcuna azione richiesta. Lo scambio di token è una modifica di una riga.

## Vincolo scoperto durante l'esplorazione

Su questo PC non esiste né `gh` né alcuna credenziale GitHub salvata. Creare la repo,
caricare i secrets e registrare il runner self-hosted richiede un login GitHub via browser,
che solo l'utente può fare. Di conseguenza la consegna è divisa in due:

- **Fase 1 (nessuna azione utente)**: il monitor gira sul PC tramite Utilità di
  pianificazione di Windows. Operativo da subito.
- **Fase 2 (un login utente)**: gli stessi file attivano i due workflow GitHub Actions
  e aggiungono la copertura a PC spento.

Lo script è identico nelle due fasi. Cambia solo chi lo lancia.

## Architettura

Un solo script Python, due esecutori che non lavorano mai in contemporanea.

- **Esecutore PC** — fonte primaria. IP residenziale, quello che Amazon blocca di meno.
  In fase 1 è un task di Windows; in fase 2 è un runner self-hosted GitHub.
- **Esecutore cloud** — solo fase 2, `ubuntu-latest`. Non contatta mai Amazon finché il
  PC è vivo: interroga ogni 60s le API GitHub per sapere se il runner del PC è online e
  occupato. Se sì, dorme. Se il PC è spento o il job è morto, prende il controllo.

Usare le API GitHub per stabilire chi comanda elimina ogni protocollo di elezione e
ogni possibilità di avviso doppio: c'è sempre esattamente un controllore attivo, e il
PC vince sempre quando è presente.

Entrambi i job girano in ciclo da 55 minuti riavviato da un cron orario: il cron di
GitHub non scende sotto i 5 minuti, il loop interno sì.

La fase 2 richiede repo pubblica: in privata il piano free offre 2000 minuti/mese e il
solo job cloud ne consumerebbe circa 40.000. Token e chat id restano nei GitHub Secrets.

## Rilevamento della disponibilità

Verificato sulle pagine reali: sui prodotti "Disponibile su invito" il pulsante
*Aggiungi al carrello* **è già presente**. Usarlo come segnale produrrebbe falsi allarmi
immediati su tutti e 7 i prodotti.

Il prodotto è considerato `ACQUISTABILE` solo se sono vere tutte e quattro le condizioni:

1. il testo di `#availability` non contiene `su invito`, `Non disponibile`,
   `Attualmente non disponibile`;
2. è presente `buy-now-button` — assente su tutti e 7 gli articoli su invito e presente
   sul prodotto di controllo acquistabile: è il discriminante più netto;
3. esiste un prezzo leggibile nel buybox;
4. il buybox indica Amazon come venditore.

**ASIN canarino**: un prodotto sempre disponibile, controllato periodicamente. Se il
canarino risulta non acquistabile, non è il mercato ad essere cambiato ma il parser a
essersi rotto perché Amazon ha modificato l'HTML. In quel caso il bot lo segnala invece
di restare silenzioso, che è il modo peggiore di fallire per un bot di questo tipo.

## Gestione dei blocchi

Tre stati, non due: `ACQUISTABILE`, `NON_ACQUISTABILE`, `SCONOSCIUTO`.

La pagina anti-bot reale di Amazon è stata catturata: circa 4 KB, senza `<title>`,
con il testo "Fai clic sul pulsante qui sotto per continuare a fare acquisti".
Riconoscimento del blocco: assenza di `<title>`, corpo sotto i 50 KB, HTTP 503,
oppure presenza di quel testo.

Uno stato `SCONOSCIUTO` non genera mai un avviso e non aggiorna mai lo stato salvato.
È il meccanismo che impedisce a un blocco di trasformarsi in un falso allarme o in un
falso "non più disponibile".

Risposta al blocco: nuovo tentativo dopo alcuni secondi con User-Agent ruotato. Misurato
sul campo: con questa strategia tutti e 7 i prodotti sono stati letti correttamente.
Se la cecità supera una soglia di minuti consecutivi, arriva un avviso Telegram
"non riesco a leggere Amazon da X minuti", con cooldown per non ripetersi all'infinito.

## Notifiche Telegram

- **Restock** (`NON_ACQUISTABILE` verso `ACQUISTABILE`): titolo, prezzo, link
  `https://www.amazon.it/dp/<ASIN>`, orario. Notifica sonora.
- **Finestra chiusa** (`ACQUISTABILE` verso `NON_ACQUISTABILE`): messaggio breve.
- Mai due avvisi consecutivi per lo stesso stato.
- Comandi in sola lettura via `getUpdates` dentro il ciclo: `/status` (chi controlla, da
  quanto, esito ultimo giro) e `/lista` (i 7 prodotti con stato corrente).
- L'aggiunta di prodotti si fa modificando `config.json`. Un comando `/add` non è
  previsto in questa versione.

## Stato persistente

`state.json` contiene l'ultimo stato noto per ogni ASIN. In fase 1 è un file locale.
In fase 2 vive sul branch `bot-state` e viene scritto tramite Contents API solo quando
uno stato cambia davvero, quindi poche scritture a settimana e nessun rumore nella
cronologia git.

## File del progetto

```
monitor.py           # fetch, parsing, stato, telegram, comandi
config.json          # ASIN, canarino, soglie, tempi
state.json           # ultimo stato noto per ASIN
.env                 # TG_BOT_TOKEN, TG_CHAT_ID (mai committato)
tests/               # test offline su pagine reali salvate
.github/workflows/   # watch-pc.yml + watch-cloud.yml (fase 2)
README.md            # setup task Windows, secrets, runner, BotFather
```

Stile allineato ai bot esistenti dell'utente (`iphone 17`, `Bet`): Python con `requests`,
`.env` accanto allo script, flag CLI `--once`, `--dry-run`, `--test-telegram`, `--selftest`.

## Test

`--selftest` gira interamente offline su pagine HTML reali salvate in `tests/fixtures/`:

| Fixture | Origine | Esito atteso |
|---|---|---|
| `invito_B0H9HFPRRD.html` | pagina reale del 2026-09-24 | `NON_ACQUISTABILE` |
| `acquistabile_B0F8VZ7QVX.html` | pagina reale di prodotto venduto da Amazon | `ACQUISTABILE` |
| `blocco_antibot.html` | pagina anti-bot reale catturata | `SCONOSCIUTO` |
| `nondisponibile_sintetica.html` | derivata da pagina reale, etichettata come sintetica | `NON_ACQUISTABILE` |

Il test che conta è il primo: garantisce che "Disponibile su invito" non venga mai
interpretato come acquistabile. È il modo in cui questo bot fallirebbe per primo.

## Fuori ambito

Comando `/add` da chat, supporto a domini Amazon diversi da amazon.it, acquisto
automatico, monitoraggio di venditori terzi, storico prezzi.
