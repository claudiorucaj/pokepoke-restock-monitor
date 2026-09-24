# Registra il monitor come attivita pianificata di Windows.
#
# Schema: il task parte ogni 5 minuti; ogni esecuzione dura 55 minuti. Non si
# accavallano perche monitor.py tiene un lucchetto (un socket su 127.0.0.1) e
# ogni istanza in piu esce subito. Il vantaggio rispetto a un riavvio orario e
# la ripartenza rapida: dopo un riavvio del PC o la morte del processo il
# monitoraggio riprende entro 5 minuti invece che all'ora successiva.
#
# Uso:       powershell -ExecutionPolicy Bypass -File installa_task_windows.ps1
# Rimozione: schtasks /delete /tn PokePoke-Monitor /f

$nome = "PokePoke-Monitor"
$cartella = $PSScriptRoot
if (-not $cartella) { $cartella = (Get-Location).Path }

# Il percorso contiene uno spazio ("Bot telegram") e schtasks non gestisce le
# virgolette annidate dentro /tr. Il nome breve 8.3 elimina il problema.
$fso = New-Object -ComObject Scripting.FileSystemObject
$corto = $fso.GetFolder($cartella).ShortPath

$comando = "wscript.exe $corto\avvia_nascosto.vbs"
schtasks /create /tn $nome /tr $comando /sc minute /mo 5 /f | Out-Null

if ($LASTEXITCODE -eq 0) {
    Write-Output "Task '$nome' registrato: parte ogni 5 minuti, cartella $corto"
} else {
    Write-Output "Registrazione fallita (codice $LASTEXITCODE)."
}
