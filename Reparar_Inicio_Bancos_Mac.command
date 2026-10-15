#!/bin/zsh
set -eu
ROOT="$HOME/Documents/App Conciliador Bancos Maveric/Archivos APP"
if [[ ! -d "$ROOT/APP" ]]; then
  echo "No se encontró la instalación de Bancos en Documentos."
  read "?Presioná Enter para cerrar."
  exit 1
fi
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT
echo "Reparando el inicio de Bancos…"
/usr/bin/curl --fail --location --show-error --proto '=https' --proto-redir '=https' --connect-timeout 8 --max-time 90 'https://raw.githubusercontent.com/stournier77/conciliador-bancos-maveric-sevens/main/updates/updater.py' --output "$TEMP_DIR/updater.py"
ACTUAL="$(/usr/bin/shasum -a 256 "$TEMP_DIR/updater.py" | /usr/bin/awk '{print $1}')"
if [[ "$ACTUAL" != '96368f66cd9650712edaf4f70171e2947aa1bc8fd66e4608ba8fd2e1d042a99f' ]]; then
  echo "No se pudo verificar el archivo. La instalación se conserva."
  read "?Presioná Enter para cerrar."
  exit 1
fi
BACKUP="$ROOT/backups/reparacion_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP"
if [[ -f "$ROOT/updater.py" ]]; then cp "$ROOT/updater.py" "$BACKUP/updater.py"; fi
cp "$TEMP_DIR/updater.py" "$ROOT/updater.py"
cd "$ROOT"
python3 "$ROOT/updater.py"
