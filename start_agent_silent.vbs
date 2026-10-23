' ==============================================================================
' J.A.R.V.I.S. Local Agent - Root Silent Background Launcher Forwarder (VBScript)
' ==============================================================================
Option Explicit

Dim objFSO, objShell, rootDir, targetVbs

Set objFSO = CreateObject("Scripting.FileSystemObject")
Set objShell = CreateObject("WScript.Shell")

rootDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
targetVbs = rootDir & "\ops\windows\start_agent_silent.vbs"

If objFSO.FileExists(targetVbs) Then
    objShell.Run "wscript.exe " & Chr(34) & targetVbs & Chr(34), 0, False
End If

Set objShell = Nothing
Set objFSO = Nothing
