"""Start the local Windows app without installing packages or making AI calls."""
from pathlib import Path
import argparse
import gzip
import http.client
import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".local" / "launcher"
BACKEND_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:8081"


def can_start_mongo(uri):
    parsed = urlsplit(uri)
    return (
        parsed.scheme == "mongodb"
        and parsed.hostname in ("localhost", "127.0.0.1")
        and parsed.port in (None, 27017)
        and not parsed.username
        and parse_qs(parsed.query).get("replicaSet") == ["rs0"]
    )


def service_environment(env_file):
    from dotenv import dotenv_values
    # Match server.py: inherited environment wins over .env.
    env = dict(os.environ)
    for key, value in dotenv_values(env_file).items():
        if value is not None:
            env.setdefault(key, value)
    # The launcher runs one backend process, so leases left by a previous run
    # belong to a process that has exited; free them at startup.
    env.setdefault("CLEAR_LEASES_ON_STARTUP", "1")
    env["EXPO_PUBLIC_BACKEND_URL"] = BACKEND_URL
    env["CI"] = "1"
    env["EXPO_NO_TELEMETRY"] = "1"
    env["EXPO_OFFLINE"] = "1"
    # Expo's better-opn helper honors this; only our app window should open.
    env["BROWSER"] = "none"
    return env


def port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def fetch(url, timeout=3):
    # Metro's large uncompressed response can stall on Windows; browsers request
    # compressed bundles. Read and validate the whole gzip stream the same way.
    request = Request(url, headers={"Accept-Encoding": "gzip"})
    with urlopen(request, timeout=timeout) as response:
        content = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            content = gzip.decompress(content)
        return content.decode("utf-8")


def backend_ready():
    try:
        health = json.loads(fetch(BACKEND_URL + "/api/health"))
        paths = json.loads(fetch(BACKEND_URL + "/openapi.json"))["paths"]
        return health.get("status") == "ok" and "/api/story/new" in paths and "/api/admin/runtime" in paths
    except (OSError, ValueError, KeyError, http.client.HTTPException):
        return False


def frontend_ready():
    try:
        if "packager-status:running" not in fetch(FRONTEND_URL + "/status"):
            return False
        bundle = fetch(FRONTEND_URL + "/node_modules/expo-router/entry.bundle?platform=web&dev=true&hot=false&lazy=true&transform.routerRoot=app", timeout=45)
        # Expo embeds its root and public URL; reject an unrelated Metro server.
        encoded_root = json.dumps(str(ROOT / "frontend"))[1:-1]
        return encoded_root in bundle and BACKEND_URL in bundle and "EXPO_PUBLIC_BACKEND_URL" in bundle
    except (OSError, ValueError, http.client.HTTPException):
        return False


def start_process(name, command, cwd, env):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with (RUNTIME / (name.lower() + ".log")).open("ab") as log:
        return subprocess.Popen(
            [str(value) for value in command], cwd=str(cwd), env=env,
            stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


def ensure_service(name, port, ready, command, cwd, env, status):
    status("Checking " + name.lower() + "...")
    if ready():
        status(name + " is already running.")
        return False
    if port_open(port):
        raise RuntimeError(f"Port {port} is occupied, but {name.lower()} is not ready or belongs to another app. Close that service's terminal and try again. The launcher will not stop unknown processes.")
    process = start_process(name, command, cwd, env)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if ready():
            status(name + " is ready.")
            return True
        if process.poll() is not None:
            raise RuntimeError(f"{name} exited during startup. See {RUNTIME / (name.lower() + '.log')}.")
        time.sleep(0.5)
    raise RuntimeError(f"{name} did not become ready within two minutes. See {RUNTIME / (name.lower() + '.log')}.")


def find_mongod(config):
    candidates = [config.get("mongod"), shutil.which("mongod")]
    candidates += list((ROOT / ".local" / "tools").glob("**/mongod.exe"))
    candidates += sorted(Path(os.environ.get("ProgramFiles", r"C:\Program Files")).glob("MongoDB/Server/*/bin/mongod.exe"), reverse=True)
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise RuntimeError(f"MongoDB is not installed or located. Set the mongod executable path in {RUNTIME / 'config.json'}; see docs/windows-launcher.md.")


def ensure_database(env, config, status):
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
    uri = env.get("MONGO_URL", "")
    if not uri:
        raise RuntimeError("MONGO_URL is missing from backend/.env.")
    status("Checking database...")
    client = MongoClient(uri, serverSelectionTimeoutMS=2000, connectTimeoutMS=2000)
    try:
        try:
            hello = client.admin.command("hello")
        except PyMongoError:
            hello = None
        if hello is None:
            if not can_start_mongo(uri) or port_open(27017):
                raise RuntimeError("The configured database cannot be reached. Automatic database startup only supports a local rs0 replica set on port 27017; existing remote or custom databases must be started separately.")
            data = ROOT / ".local" / "mongo-gameplay"
            data.mkdir(parents=True, exist_ok=True)
            process = start_process("database", [find_mongod(config), "--replSet", "rs0", "--bind_ip", "127.0.0.1", "--port", "27017", "--dbpath", data], ROOT, env)
            direct = MongoClient("mongodb://127.0.0.1:27017/?directConnection=true", serverSelectionTimeoutMS=1000)
            try:
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError(f"MongoDB exited. See {RUNTIME / 'database.log'}.")
                    try:
                        direct.admin.command("ping")
                        break
                    except PyMongoError:
                        time.sleep(0.5)
                else:
                    raise RuntimeError("MongoDB did not start within 45 seconds.")
                try:
                    direct.admin.command("replSetGetStatus")
                except PyMongoError as exc:
                    if getattr(exc, "code", None) != 94:
                        raise RuntimeError("Cannot inspect local replica set configuration.") from None
                    direct.admin.command("replSetInitiate", {"_id": "rs0", "members": [{"_id": 0, "host": "127.0.0.1:27017"}]})
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    if direct.admin.command("hello").get("isWritablePrimary"):
                        break
                    time.sleep(0.5)
                else:
                    raise RuntimeError("MongoDB started but has no writable primary yet.")
            finally:
                direct.close()
            hello = client.admin.command("hello")
        if not hello.get("setName") and hello.get("msg") != "isdbgrid":
            raise RuntimeError("MongoDB is standalone. Dice Reactions needs a replica set for story saves.")
        status("Database is ready.")
    except PyMongoError:
        raise RuntimeError("Database connection failed. Check MONGO_URL and the database service; credentials are not shown here.") from None
    finally:
        client.close()


def find_browser():
    # Prefer the user's default browser when it supports app windows.
    preferred = "edge"
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice") as key:
            if "chrome" in winreg.QueryValueEx(key, "ProgId")[0].lower():
                preferred = "chrome"
    except OSError:
        pass
    choices = {
        "edge": [Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe", Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe"],
        "chrome": [Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe", Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe"],
    }
    for name in (preferred, "chrome" if preferred == "edge" else "edge"):
        for path in choices[name]:
            if path.is_file():
                return str(path)
    raise RuntimeError("Microsoft Edge or Google Chrome is required for the app window.")


def launch(status, open_app=True):
    from dotenv import dotenv_values  # dependency check before starting anything
    config_path = RUNTIME / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8-sig")) if config_path.exists() else {}
    env = service_environment(ROOT / "backend" / ".env")
    python = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
    node_candidates = list((ROOT / ".nw_tmp" / "node20").glob("*/node.exe"))
    node = str(node_candidates[0]) if node_candidates else shutil.which("node")
    expo = ROOT / "frontend" / "node_modules" / "expo" / "bin" / "cli"
    if not python.is_file() or not node or not expo.is_file():
        raise RuntimeError("Local Python/Node dependencies are missing. Follow docs/development.md first; the launcher does not install packages.")
    browser = find_browser() if open_app else None
    ensure_database(env, config, status)
    ensure_service("Engine", 8000, backend_ready, [python, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8000"], ROOT / "backend", env, status)
    ensure_service("Frontend", 8081, frontend_ready, [node, expo, "start", "--web", "--localhost", "--port", "8081"], ROOT / "frontend", env, status)
    if not json.loads(fetch(BACKEND_URL + "/api/health")).get("llm_configured"):
        status("App ready. Add your provider key to backend/.env before generating stories.")
    if browser:
        status("Opening Dice Reactions...")
        subprocess.Popen([browser, "--app=" + FRONTEND_URL], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    status("Ready. Local services stay running when the app window closes.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Start/reuse services and check readiness without an app window")
    args = parser.parse_args()
    # Prevent two double-clicks from racing to start the same services.
    RUNTIME.mkdir(parents=True, exist_ok=True)
    import msvcrt
    lock = (RUNTIME / "startup.lock").open("a+b")
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return 0
    if args.check:
        try:
            launch(print, open_app=False)
            return 0
        except Exception as exc:
            print("Launcher failed:", str(exc))
            return 1
    import tkinter as tk
    from tkinter import ttk
    window = tk.Tk()
    window.title("Dice Reactions")
    window.geometry("600x250")
    window.resizable(False, False)
    label = tk.StringVar(value="Starting Dice Reactions...")
    ttk.Label(window, text="Dice Reactions", font=("Segoe UI", 20, "bold")).pack(pady=(22, 12))
    ttk.Label(window, textvariable=label, wraplength=550, justify="center").pack(padx=20)
    progress = ttk.Progressbar(window, mode="indeterminate", length=500)
    progress.pack(pady=20)
    progress.start()
    events = queue.Queue()

    def worker():
        try:
            launch(lambda text: events.put(("status", text)))
            events.put(("done", ""))
        except Exception as exc:
            events.put(("error", str(exc)))

    def poll():
        while not events.empty():
            kind, text = events.get()
            if kind == "status":
                label.set(text)
            elif kind == "done":
                window.after(1500, window.destroy)
                return
            else:
                progress.stop()
                progress.pack_forget()
                label.set(text)
                ttk.Button(window, text="Close", command=window.destroy).pack(pady=10)
                return
        window.after(100, poll)

    threading.Thread(target=worker, daemon=True).start()
    window.after(100, poll)
    window.mainloop()
    lock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
