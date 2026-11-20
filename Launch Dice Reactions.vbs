Option Explicit
Dim shell, files, root, python, script
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
root = files.GetParentFolderName(WScript.ScriptFullName)
python = root & "\backend\.venv\Scripts\pythonw.exe"
script = root & "\scripts\windows_launcher.py"
If Not files.FileExists(python) Then
    MsgBox "Python dependencies are missing. See docs\development.md in " & root, 16, "Dice Reactions"
    WScript.Quit 1
End If
shell.CurrentDirectory = root
shell.Run """" & python & """ """ & script & """", 0, False
