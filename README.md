# Monitor restock Amazon.it — Pokémon GCC 30° Anniversario

Avvisa su Telegram, con il link ufficiale Amazon, nel momento in cui uno dei
prodotti monitorati diventa acquistabile direttamente da Amazon.

**Stato: attivo 24/7.** Il monitoraggio gira tramite GitHub Actions su due
esecutori che non lavorano mai insieme: il runner sul PC come fonte primaria,
un runner cloud come riserva quando il PC e spento. Non serve fare nulla.

Repo: https://github.com/claudiorucaj/pokepoke-restock-monitor

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

Tutto passa da GitHub Actions. Due workflow, entrambi con un ciclo interno da
55 minuti riavviato da un cron orario, perché il cron di GitHub non scende
sotto i 5 minuti mentre a noi serve un giro ogni 60 secondi.

- **`watch-pc.yml`** (cron `:00`) gira sul runner self-hosted del PC. È la
  fonte primaria: IP residenziale, quello che Amazon blocca di meno.
- **`watch-cloud.yml`** (cron `:04`) gira su runner GitHub. Prima di ogni
  giro chiede a GitHub se il workflow del PC ha un'esecuzione *in corso*: se
  sì salta il giro senza nemmeno contattare Amazon. Un PC spento lascia il suo
  job in coda anziché in esecuzione, ed è esattamente quella differenza a far
  subentrare il cloud.

I due cron sono sfasati di proposito: partendo insieme, il runner cloud — che
si avvia in pochi secondi — vedrebbe il job del PC ancora in coda e si
crederebbe scoperto, monitorando in doppio per qualche minuto.

### Il runner sul PC

L'utente non è amministratore, quindi il runner **non** è installato come
servizio Windows. Lo tiene acceso l'attività pianificata `PokePoke-Runner`,
che scatta ogni 5 minuti e lancia `avvia_runner_nascosto.vbs`.

Quel lanciatore controlla prima se un `Runner.Listener.exe` è già vivo e in
quel caso esce. Non è un dettaglio: il runner GitHub **non** rifiuta di
avviarsi due volte, e senza quel controllo se ne accumulava uno ogni cinque
minuti, tutti a contendersi la stessa sessione. Con il controllo, il task
diventa un guardiano che lo riavvia solo se è morto.

```powershell
schtasks /query /tn PokePoke-Runner       # stato
schtasks /run   /tn PokePoke-Runner       # avvio immediato
Get-Process Runner.Listener               # deve essercene esattamente uno
```

### Il monitor locale, come riserva manuale

L'attività `PokePoke-Monitor` esiste ancora ma è **disattivata**: faceva girare
il monitor direttamente sul PC, prima che ci fosse GitHub. Se Actions dovesse
dare problemi, si riaccende in un comando e il monitoraggio riparte senza
dipendere da nulla di remoto:

```powershell
schtasks /change /tn PokePoke-Monitor /enable
schtasks /change /tn PokePoke-Runner  /disable   # per non averli entrambi
```

In quel caso il registro torna in `monitor.log`, accanto allo script.

## Cosa è configurato su GitHub

Già fatto e funzionante. Documentato qui per poterlo rifare, spostare su un
altro PC o capire cosa toccare se qualcosa smette di andare.

**Repo pubblica.** Serve la visibilità pubblica: su repo privata il piano
gratuito dà 2000 minuti di Actions al mese e il solo job cloud ne consumerebbe
circa 40.000. Il codice è pubblico, le credenziali no.

**Due Secrets** (Settings → Secrets and variables → Actions): `TG_BOT_TOKEN` e
`TG_CHAT_ID`, gli stessi del `.env` locale. Non serve altro: per sapere se il
PC è vivo basta il token automatico di Actions, perché il segnale sono le
esecuzioni del workflow e non lo stato dei runner (leggere i runner
richiederebbe un token con permesso *Administration*, cioè un terzo secret da
creare e da far scadere).

**Runner self-hosted** registrato come `pokepoke-pc` con etichette
`self-hosted, windows, pokepoke`, installato in `C:ctions-runner`. Per
rigenerarlo da zero:

```bash
gh api -X POST repos/<utente>/<repo>/actions/runners/registration-token --jq .token
cd C:/actions-runner
./config.cmd --unattended --replace --url https://github.com/<utente>/<repo>   --token <token> --name pokepoke-pc --labels self-hosted,windows,pokepoke
```

Poi il task che lo tiene acceso, descritto sopra.

**Una trappola da ricordare:** il workflow del PC non usa `actions/setup-python`.
Quella action installa Python con `InstallAllUsers=1`, che vuole privilegi di
amministratore: sul runner self-hosted il job resta appeso lì per sempre. Sul
PC Python c'è già. Nel workflow cloud invece `setup-python` serve e resta.

Lo stato fra un'esecuzione e l'altra viaggia nella cache di Actions, così un
prodotto già visto disponibile non rigenera un avviso ogni ora.

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
leader.py       chi controlla fra PC e cloud
config.json     prodotti, canarino, tempi e soglie
tests/          test offline su pagine Amazon reali salvate
docs/           spec di progettazione e piano di implementazione
```

## Test

```bash
python -m pytest tests/ -q
```

36 test, tutti offline. Le fixture sono pagine Amazon reali salvate il
2026-09-24: un prodotto su invito, uno acquistabile venduto da Amazon, uno
acquistabile ma venduto da terzi, e la pagina anti-bot vera. La quinta è
sintetica e dichiarata tale in testa al file.

Il test che conta più di tutti è `test_su_invito_non_e_acquistabile`: è il
modo in cui questo bot fallirebbe per primo.
