# Windows launcher

Double-click **Launch Dice Reactions.vbs**, or the **Dice Reactions** desktop shortcut.
The launcher shows startup progress, starts MongoDB, the Python backend and Expo
web frontend as hidden processes, waits for readiness, then opens the game in
an Edge/Chrome app window without browser tabs or an address bar. It prefers your
default browser if that browser is Edge or Chrome. This is a local web app window,
not a packaged native executable; the existing dependencies are still required.

The game uses http://localhost:8081 and the engine uses http://localhost:8000.
The browser's existing profile is used. Stories tied to browser storage remain
accessible in the same browser/profile; changing browsers can change the device
identity used by the game.

## Requirements and configuration

- Run the dependency setup in [development.md](development.md) first.
- Keep provider credentials in `backend/.env` or the launching user's environment.
  Inherited environment values take precedence, matching the backend.
- The launcher does not select models, edit keys, install packages, or make paid AI calls.
- Node is found in the existing `.nw_tmp/node20` installation, then on PATH.
- Expo starts with `EXPO_OFFLINE=1` using installed dependencies, so launching
  the frontend does not depend on Expo's online version-check service. This
  does not disable the backend's connection to your AI provider.
- MongoDB is found through `.local/launcher/config.json`, PATH,
  `.local/tools`, or the normal Program Files MongoDB installation.
- Example machine-local configuration (use the real installed executable path):

  ```json
  { "mongod": "C:\\Program Files\\MongoDB\\Server\\7.0\\bin\\mongod.exe" }
  ```

Automatic database startup only supports `mongodb://127.0.0.1:27017/?replicaSet=rs0`
(or localhost). Its persistent data lives in `.local/mongo-gameplay`, the same
directory used by the local gameplay setup. A new replica set is initialized
only when MongoDB reports it is uninitialized. Custom/remote databases are checked
but are never created or reconfigured by the launcher.

## Lifecycle and troubleshooting

Healthy services are reused. An occupied port with an unrecognized or unready
service produces an error rather than terminating another process. Repeated
double-clicks are serialized during startup. Closing the game window leaves
the local services running so reopening is quick; restarting Windows stops them.
The launcher is not installed as a Windows startup service.

Logs for services started by the launcher are in `.local/launcher/`:
`engine.log`, `frontend.log`, and `database.log`. Existing services retain their
existing terminal/log destination. These logs and database files are ignored by Git.
Treat backend logs as private; the engine may include story data in diagnostic output.

After changing backend configuration, stop its existing process/terminal before
relaunching. The launcher deliberately does not restart healthy existing services
or claim that a saved key/model change has been applied to them.

For a console readiness check without opening the app:

```powershell
cd C:\dev\dice-reactions
.\backend\.venv\Scripts\python.exe .\scripts\windows_launcher.py --check
```

This check may start missing services, but does not generate a story.
To run isolated launcher contract tests:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s tests -p test_windows_launcher.py -v
```
