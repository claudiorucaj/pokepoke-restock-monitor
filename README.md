# Monitor restock Amazon.it — Pokémon GCC 30° Anniversario

Avvisa su Telegram, con il link ufficiale Amazon, nel momento in cui uno dei
prodotti monitorati diventa acquistabile direttamente da Amazon.

**Stato: attivo sul PC.** Il monitoraggio gira in background, senza finestre,
e riparte da solo dopo un riavvio. Non serve fare nulla per usarlo.

## Cosa controlla

Sette prodotti su amazon.it, tutti attualmente "Disponibile su invito":

| ASIN | Prodotto |
|---|---|
| B0H9HFPRRD | Set Allenatore Fuoriclasse 30° Anniversario |
| B0H9HDZN97 | Scatola da collezione Greninja-ex |
| B0H9HGQSWR | Scatola da collezione Sylveon-ex |
| B0H9HPCL27 | Confezione da due buste |
| B0H9HBQKF3 | Collezione Greninja-ex |
| B0H9HJQ1Z9 | Collezione Sylveon-ex |
| B0H99Z9XPG | Collezione con raccoglitore |

Un giro completo dei sette ogni ~60 secondi.

## Quando arriva l'avviso

Solo quando il prodotto è davvero comprabile **da Amazon**. Servono quattro
condizioni insieme: pulsante *Acquista ora* presente, venditore Amazon,
testo di disponibilità senza termini negativi, prezzo leggibile.

Il dettaglio che rende il tutto non banale: sui prodotti "Disponibile su
invito" il pulsante *Aggiungi al carrello* **c'è già**. Usare quello come
segnale manderebbe sette falsi allarmi al primo giro. Il discriminante vero è
il pulsante *Acquista ora*, che sugli articoli su invito non compare.

Ricevi anche un messaggio breve quando la finestra si chiude, così sai che è
passata.

## Quando Amazon ci blocca

Gli stati sono tre, non due: `ACQUISTABILE`, `NON_ACQUISTABILE` e
`SCONOSCIUTO`. Il terzo significa "non sono riuscito a leggere la pagina", di
solito perché Amazon ha risposto con la sua pagina anti-bot.

Uno stato sconosciuto non genera mai un avviso e non sovrascrive mai l'ultimo
stato buono. Senza questa regola un blocco diventerebbe un falso "non più
disponibile" seguito, al giro dopo, da un falso restock.

Al blocco il monitor risponde riprovando con un altro User-Agent: sul campo
basta a far passare la richiesta successiva. Se la cecità dura più di 15
minuti ricevi un avviso: meglio saperlo che credere che "nessun messaggio"
significhi "nessuna disponibilità".

C'è anche un canarino: un prodotto sempre disponibile (batterie Amazon
Basics) controllato ogni 10 giri. Se risulta non acquistabile non è il mercato
ad essere cambiato, è il parser da aggiornare perché Amazon ha modificato
l'HTML. Anche di questo vieni avvisato.

## Comandi Telegram

- `/status` — da quanto è attivo, esito dell'ultimo giro
- `/lista` — i sette prodotti con lo stato corrente

## Uso a mano

```bash
python monitor.py --selftest        # verifica il parser su pagine salvate, offline
python monitor.py --test-telegram   # manda un messaggio di prova
python monitor.py --once --dry-run  # un giro solo, senza inviare nulla
python monitor.py --once            # un giro solo
```

## Aggiungere o togliere prodotti

Si modifica `config.json`, voce `prodotti`: serve l'ASIN (le dieci cifre dopo
`/dp/` nell'URL Amazon) e un nome a piacere. Dal giro successivo è attivo.

Nello stesso file si regolano i tempi: `intervallo_ciclo_s`,
`pausa_tra_prodotti_s`, `tentativi_per_prodotto`.

## Come è avviato

Un'attività pianificata di Windows, `PokePoke-Monitor`, parte ogni 5 minuti e
lancia `avvia_nascosto.vbs`, che a sua volta esegue `avvia.cmd` senza mostrare
finestre. Ogni esecuzione dura 55 minuti.

Le esecuzioni non si accavallano: `monitor.py` tiene un lucchetto (un socket
su `127.0.0.1:47653`) e ogni istanza in più esce subito. Partire ogni 5 minuti
invece che ogni ora serve a riprendere in fretta dopo un riavvio del PC o la
morte del processo.

Il registro sta in `monitor.log`.

```powershell
schtasks /query /tn PokePoke-Monitor     # stato
schtasks /run   /tn PokePoke-Monitor     # avvio immediato
schtasks /end   /tn PokePoke-Monitor     # ferma l'esecuzione in corso
schtasks /delete /tn PokePoke-Monitor /f # disinstalla
```

Per reinstallarlo: `powershell -ExecutionPolicy Bypass -File installa_task_windows.ps1`

## Fase 2: copertura anche a PC spento

Il codice per la copertura 24/7 è già pronto, ma è inerte finché la repo non
viene collegata a GitHub. Richiede un login che solo tu puoi fare.

L'architettura è ibrida e **non produce avvisi doppi**: il runner cloud, prima
di ogni giro, chiede a GitHub se il runner del PC sta lavorando. Se sì, salta
il giro senza nemmeno contattare Amazon. C'è sempre al massimo un controllore
attivo, e il PC — che ha IP residenziale e viene bloccato molto meno — vince
sempre quando è acceso.

Passi:

1. **Crea la repo e caricala.** Deve essere **pubblica**: su repo privata il
   piano gratuito dà 2000 minuti al mese e il solo job cloud ne consumerebbe
   circa 40.000. Il codice è pubblico, le credenziali restano nei Secrets.

   ```bash
   git remote add origin https://github.com/<tuo-utente>/<repo>.git
   git push -u origin implementazione:main
   ```

2. **Aggiungi tre Secrets** (Settings → Secrets and variables → Actions):
   - `TG_BOT_TOKEN`, `TG_CHAT_ID` — li trovi nel file `.env` locale
   - `PAT_RUNNERS` — token fine-grained sulla repo con permesso
     *Administration: read*. Serve al runner cloud per sapere se il PC è vivo.

3. **Installa il runner self-hosted sul PC** (Settings → Actions → Runners →
   New self-hosted runner → Windows) e registralo come servizio, così parte da
   solo:

   ```powershell
   ./run.cmd --once   # prova
   ./svc.sh install   # oppure, su Windows: .\svc.cmd install && .\svc.cmd start
   ```

4. **Disattiva il task di Windows**, altrimenti monitor locale e runner
   GitHub lavorerebbero in parallelo:

   ```powershell
   schtasks /delete /tn PokePoke-Monitor /f
   ```

I due workflow (`.github/workflows/`) partono ogni ora e girano 55 minuti,
perché il cron di GitHub non scende sotto i 5 minuti: la cadenza di 60 secondi
la fa il ciclo interno. Lo stato fra un'esecuzione e l'altra viaggia nella
cache di Actions, così un prodotto già visto disponibile non rigenera un
avviso ogni ora.

## Bot Telegram

Per non farti fare nulla, il monitor usa il bot che avevi già
(`@alertprezzoiphone17bot`) e la stessa chat. Se preferisci un bot dedicato:
creane uno con [@BotFather](https://t.me/BotFather), scrivigli un messaggio, e
sostituisci le due righe di `.env` con il nuovo token e il nuovo chat id.
Il chat id si legge da
`https://api.telegram.org/bot<TOKEN>/getUpdates` dopo avergli scritto.

## Struttura

```
monitor.py      ciclo di controllo, CLI, sorveglianza tecnica
amazon.py       scaricamento pagine e interpretazione della disponibilità
notifiche.py    messaggi Telegram e lettura credenziali
stato.py        stato persistente e regole di transizione
leader.py       chi controlla fra PC e cloud (fase 2)
config.json     prodotti, canarino, tempi e soglie
tests/          test offline su pagine Amazon reali salvate
docs/           spec di progettazione e piano di implementazione
```

## Test

```bash
python -m pytest tests/ -q
```

37 test, tutti offline. Le fixture sono pagine Amazon reali salvate il
2026-09-24: un prodotto su invito, uno acquistabile venduto da Amazon, uno
acquistabile ma venduto da terzi, e la pagina anti-bot vera. La quinta è
sintetica e dichiarata tale in testa al file.

Il test che conta più di tutti è `test_su_invito_non_e_acquistabile`: è il
modo in cui questo bot fallirebbe per primo.
