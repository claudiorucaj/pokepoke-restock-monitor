@echo off
rem Lancia un ciclo di monitoraggio da 55 minuti.
rem
rem Nessun redirect su file: qualunque file aperto qui resterebbe bloccato per
rem tutta la durata del processo, e la seconda istanza morirebbe nel tentativo
rem di aprirlo invece di annunciarsi nel registro. Il registro e gli eventuali
rem schianti li scrive monitor.py, che apre e chiude monitor.log riga per riga.
cd /d "%~dp0"
python monitor.py --durata-min 55 >nul 2>&1
