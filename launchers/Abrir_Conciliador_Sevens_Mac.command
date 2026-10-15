#!/bin/zsh
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$ROOT/runtime_mac"
UV="$RUNTIME/uv/uv"
mkdir -p "$RUNTIME/uv" "$ROOT/logs"
exec > >(tee -a "$ROOT/logs/ultimo_arranque_mac.log") 2>&1
export UV_CACHE_DIR="$RUNTIME/cache"
export UV_PYTHON_INSTALL_DIR="$RUNTIME/python"
export UV_NO_MODIFY_PATH=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
if [[ ! -x "$UV" ]]; then
  TEMP_INSTALL="$(mktemp)"
  curl -fsSL --connect-timeout 8 --max-time 45 https://astral.sh/uv/install.sh -o "$TEMP_INSTALL"
  env UV_INSTALL_DIR="$RUNTIME/uv" UV_NO_MODIFY_PATH=1 sh "$TEMP_INSTALL"
  rm -f "$TEMP_INSTALL"
fi
# Usar Python administrado fuera del entorno que vamos a comprobar/reparar.
if ! PYTHON="$("$UV" python find --managed-python 3.12 2>/dev/null)"; then
  "$UV" python install --no-bin --no-registry 3.12
  PYTHON="$("$UV" python find --managed-python 3.12)"
fi
"$PYTHON" "$ROOT/launchers/arranque.py" "$@" || { echo 'Revisá los registros en Archivos APP/logs.'; read '?Enter para cerrar...'; exit 1; }
