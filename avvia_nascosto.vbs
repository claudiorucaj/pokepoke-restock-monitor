' Lancia avvia.cmd senza mostrare alcuna finestra.
' Serve perche il task di Windows gira come utente interattivo: senza
' questo involucro comparirebbe una console ogni ora.
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
cartella = fso.GetParentFolderName(WScript.ScriptFullName)
sh.Run "cmd /c """ & cartella & "\avvia.cmd""", 0, False
