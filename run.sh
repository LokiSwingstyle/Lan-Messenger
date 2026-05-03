#!/usr/bin/env bash
set -e
python3 - <<'PY'
import importlib, subprocess, sys
pkgs = ["flask", "flask_socketio", "eventlet"]
for p in pkgs:
    try:
        importlib.import_module(p)
    except Exception:
        subprocess.check_call([sys.executable, "-m", "pip", "install", p])
PY
python3 app.py
