@echo off
rem Lancia un ciclo di monitoraggio da 55 minuti.
rem Il task di Windows lo riavvia ogni ora: se il ciclo muore per qualsiasi
rem motivo, al massimo si resta scoperti fino allo scatto successivo.
cd /d "%~dp0"
echo. >> monitor.log
echo ===== avvio %date% %time% budget 55 min ===== >> monitor.log
python monitor.py --durata-min 55 >> monitor.log 2>&1
