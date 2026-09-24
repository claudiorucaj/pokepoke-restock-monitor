' Avvia il runner GitHub Actions senza mostrare finestre, ma solo se non ne
' gira gia uno.
'
' Serve perche l'utente non e amministratore e il runner non puo essere
' installato come servizio Windows: lo tiene acceso un task pianificato che
' scatta ogni 5 minuti e fa da guardiano, riavviandolo se e morto.
'
' Il controllo sul processo non e un dettaglio: il runner NON rifiuta di
' avviarsi due volte, e due listener sulla stessa registrazione si
' contendono la sessione con GitHub. Senza questo controllo se ne
' accumulerebbe uno ogni cinque minuti.
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
Set wmi = GetObject("winmgmts:\\.\root\cimv2")

Set trovati = wmi.ExecQuery("SELECT ProcessId FROM Win32_Process WHERE Name = 'Runner.Listener.exe'")
If trovati.Count > 0 Then
    WScript.Quit 0
End If

cartella = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = cartella
sh.Run "cmd /c """ & cartella & "\run.cmd""", 0, False
