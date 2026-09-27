' ==============================================================================
' J.A.R.V.I.S. Local Agent - Silent Background Launcher (VBScript)
' Stark Industries PC Companion
'
' Lance jarvis_local_agent.py en tâche de fond 100% invisible (sans console)
' avec accès complet à la session graphique interactive (Chrome CDP, apps, etc.)
' ==============================================================================
Option Explicit

Dim objFSO, objShell, scriptDir, venvPythonw, dotVenvPythonw, pythonwExe, agentScript, runCmd

Set objFSO = CreateObject("Scripting.FileSystemObject")
Set objShell = CreateObject("WScript.Shell")

' Résolution dynamique du dossier d'exécution (dossier du script)
scriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
objShell.CurrentDirectory = scriptDir

venvPythonw = scriptDir & "\venv\Scripts\pythonw.exe"
dotVenvPythonw = scriptDir & "\.venv\Scripts\pythonw.exe"
agentScript = scriptDir & "\jarvis_local_agent.py"

' Vérification de l'existence du script agent
If Not objFSO.FileExists(agentScript) Then
    MsgBox "Le script agent est introuvable :" & vbCrLf & agentScript, vbCritical, "J.A.R.V.I.S. Local Agent - Erreur"
    WScript.Quit 1
End If

' Détection automatique de l'interpréteur pythonw (priorité à l'environnement virtuel)
If objFSO.FileExists(venvPythonw) Then
    pythonwExe = venvPythonw
ElseIf objFSO.FileExists(dotVenvPythonw) Then
    pythonwExe = dotVenvPythonw
Else
    pythonwExe = "pythonw.exe"
End If

' Lancement silencieux : fenêtre masquée (0 = SW_HIDE) et mode asynchrone (False)
runCmd = Chr(34) & pythonwExe & Chr(34) & " " & Chr(34) & agentScript & Chr(34)
objShell.Run runCmd, 0, False

WScript.Sleep 300

Set objShell = Nothing
Set objFSO = Nothing
