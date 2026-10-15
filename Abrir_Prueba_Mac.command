#!/bin/zsh
ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$HOME/Documents/App Conciliador Tarjetas Maveric/Archivos APP/runtime_mac/.venv/bin/python"
cd "$ROOT/APP"
exec "$PYTHON" -m streamlit run app.py --server.port=18772 --server.address=127.0.0.1 --server.headless=false --server.fileWatcherType=poll --server.runOnSave=true --theme.base=light
