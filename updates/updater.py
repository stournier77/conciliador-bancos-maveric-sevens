import os
import sys
import time
import shutil
import zipfile
import subprocess
import tempfile
import json
from pathlib import Path
from urllib.request import Request, urlopen

UPDATER_VERSION = "2.0.0"
ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "APP"
CONFIG = ROOT / "github_config.txt"
LOG_FILE = ROOT / "actualizador.log"


def log(message):
    text = str(message)
    print(text, flush=True)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "  " + text + "\n")
    except Exception:
        pass


def read_config():
    cfg = {
        "GITHUB_USER": "stournier77",
        "GITHUB_REPO": "conciliador-bancos-maveric-sevens",
        "GITHUB_BRANCH": "main",
        "APP_PORT": "8772",
    }
    if CONFIG.exists():
        for line in CONFIG.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg


def current_version():
    vf = APP_DIR / "version.txt"
    return vf.read_text(encoding="utf-8-sig").strip() if vf.exists() else "0.0.0"


def native_message(title, message, kind="info"):
    try:
        if sys.platform == "darwin":
            icon = "caution" if kind == "error" else "note"
            script = f'display dialog {json.dumps(message)} with title {json.dumps(title)} buttons {{"Aceptar"}} default button "Aceptar" with icon {icon}'
            subprocess.run(["osascript", "-e", script], check=False)
        elif sys.platform.startswith("win"):
            icon = "Error" if kind == "error" else "Information"
            ps = (
                "Add-Type -AssemblyName PresentationFramework; "
                f"[System.Windows.MessageBox]::Show({message!r},{title!r},'OK','{icon}') | Out-Null"
            )
            subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], check=False)
    except Exception:
        pass


def ask_update(local, remote):
    message = (
        "Hay una nueva versión del Conciliador Bancos - Maveric.\n\n"
        f"Versión instalada: {local}\n"
        f"Nueva versión: {remote}\n\n"
        "¿Desea actualizar ahora?"
    )
    try:
        if sys.platform == "darwin":
            script = (
                f'display dialog {json.dumps(message)} with title "Actualización disponible" '
                'buttons {"Ahora no", "Actualizar"} default button "Actualizar" cancel button "Ahora no" with icon note'
            )
            r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            return r.returncode == 0 and "Actualizar" in r.stdout
        if sys.platform.startswith("win"):
            ps = (
                "Add-Type -AssemblyName PresentationFramework; "
                f"$r=[System.Windows.MessageBox]::Show({message!r},'Actualización disponible','YesNo','Information'); "
                "if($r -eq 'Yes'){exit 0}else{exit 1}"
            )
            return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps]).returncode == 0
    except Exception as e:
        log(f"No se pudo mostrar la confirmación: {e}")
    try:
        return input("¿Actualizar ahora? [S/n]: ").strip().lower() not in {"n", "no"}
    except Exception:
        return True


def curl_download(url, out_path):
    subprocess.check_call(["curl", "-L", "--fail", "--silent", "--show-error", url, "-o", str(out_path)])


def download(url, out_path):
    out_path = Path(out_path)
    try:
        with urlopen(Request(url, headers={"User-Agent": "Conciliador-Bancos-Maveric-Sevens"}), timeout=120) as r:
            out_path.write_bytes(r.read())
    except Exception as first_error:
        log(f"Descarga Python no disponible; intento alternativo: {first_error}")
        if sys.platform == "darwin":
            curl_download(url, out_path)
        elif sys.platform.startswith("win"):
            ps = f"Invoke-WebRequest -Uri {url!r} -OutFile {str(out_path)!r} -UseBasicParsing"
            subprocess.check_call(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps])
        else:
            raise


def fetch_text(url):
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        p = Path(tmp.name)
    try:
        download(url, p)
        return p.read_text(encoding="utf-8-sig").strip()
    finally:
        p.unlink(missing_ok=True)


def github_base():
    cfg = read_config()
    return f"https://raw.githubusercontent.com/{cfg['GITHUB_USER']}/{cfg['GITHUB_REPO']}/{cfg.get('GITHUB_BRANCH','main')}/updates"


def self_update_if_needed(base, stamp):
    try:
        remote = fetch_text(base + "/updater_version.txt?nocache=" + stamp)
        if remote and remote != UPDATER_VERSION:
            log(f"Actualizando el sistema de actualizaciones: {UPDATER_VERSION} → {remote}")
            new_file = ROOT / "updater.py.nuevo"
            download(base + "/updater.py?nocache=" + stamp, new_file)
            source = new_file.read_text(encoding="utf-8-sig")
            compile(source, str(new_file), "exec")
            backup = ROOT / "updater.py.anterior"
            shutil.copy2(Path(__file__).resolve(), backup)
            os.replace(new_file, Path(__file__).resolve())
            log("Actualizador renovado. Reiniciando...")
            os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve())])
    except Exception as e:
        log(f"Aviso: no se pudo verificar el propio actualizador: {e}")


def install_app(base, remote, stamp):
    tmp_zip = ROOT / "_latest_app.zip"
    temp_extract = ROOT / "_APP_NUEVA"
    backup = ROOT / "APP_RESPALDO"
    tmp_zip.unlink(missing_ok=True)
    if temp_extract.exists(): shutil.rmtree(temp_extract)
    log("Descargando nueva versión...")
    download(base + "/latest_app.zip?nocache=" + stamp, tmp_zip)
    log("Verificando archivo descargado...")
    with zipfile.ZipFile(tmp_zip, "r") as z:
        bad = z.testzip()
        if bad: raise RuntimeError(f"Archivo ZIP dañado: {bad}")
        z.extractall(temp_extract)
    candidate = temp_extract / "APP"
    if not (candidate / "app.py").exists():
        raise RuntimeError("La actualización no contiene APP/app.py")
    installed_version = (candidate / "version.txt").read_text(encoding="utf-8-sig").strip()
    if installed_version != remote:
        raise RuntimeError(f"El ZIP informa versión {installed_version}, pero GitHub anuncia {remote}")
    compile((candidate / "app.py").read_text(encoding="utf-8"), str(candidate / "app.py"), "exec")
    log("Instalando actualización...")
    if backup.exists(): shutil.rmtree(backup)
    if APP_DIR.exists(): os.replace(APP_DIR, backup)
    try:
        os.replace(candidate, APP_DIR)
    except Exception:
        if APP_DIR.exists(): shutil.rmtree(APP_DIR)
        if backup.exists(): os.replace(backup, APP_DIR)
        raise
    shutil.rmtree(backup, ignore_errors=True)
    shutil.rmtree(temp_extract, ignore_errors=True)
    tmp_zip.unlink(missing_ok=True)
    log(f"Actualización {remote} instalada correctamente.")


def check_updates():
    base = github_base()
    stamp = str(int(time.time()))
    self_update_if_needed(base, stamp)
    local = current_version()
    log("Buscando actualizaciones...")
    remote = fetch_text(base + "/version.txt?nocache=" + stamp)
    log(f"Versión instalada: {local}")
    log(f"Última versión disponible: {remote}")
    if remote != local:
        if ask_update(local, remote):
            try:
                install_app(base, remote, stamp)
                native_message("Actualización completada", f"La versión {remote} se instaló correctamente.\n\nAhora se abrirá la aplicación.")
            except Exception as e:
                log(f"ERROR AL ACTUALIZAR: {e}")
                native_message("No se pudo actualizar", f"No se pudo instalar la versión {remote}.\n\nSe abrirá la versión anterior.\n\nDetalle: {e}", "error")
        else:
            log("Actualización pospuesta por el usuario.")
    else:
        log("La aplicación está actualizada.")


def kill_port(port):
    try:
        if sys.platform == "darwin":
            pids = subprocess.check_output(["bash", "-lc", f"lsof -ti tcp:{port} || true"], text=True).strip()
            if pids:
                subprocess.call(["bash", "-lc", f"echo '{pids}' | xargs kill -9 || true"])
        elif sys.platform.startswith("win"):
            ps = f"$p=(Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue).OwningProcess|Select-Object -Unique; foreach($i in $p){{try{{Stop-Process -Id $i -Force}}catch{{}}}}"
            subprocess.call(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps])
    except Exception as e:
        log(f"No se pudo cerrar una ejecución anterior: {e}")


def run_app():
    if not (APP_DIR / "app.py").exists():
        native_message("Aplicación no encontrada", f"No se encontró:\n{APP_DIR / 'app.py'}", "error")
        raise FileNotFoundError(APP_DIR / "app.py")
    cfg = read_config()
    port = cfg.get("APP_PORT", "8772")
    kill_port(port)
    req = APP_DIR / "requirements.txt"
    if req.exists():
        subprocess.call([sys.executable, "-m", "pip", "install", "-r", str(req)])
    if sys.platform == "darwin":
        subprocess.Popen(["open", f"http://localhost:{port}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif sys.platform.startswith("win"):
        subprocess.Popen(["cmd", "/c", "start", "", f"http://localhost:{port}"], shell=False)
    subprocess.call([sys.executable, "-m", "streamlit", "run", str(APP_DIR / "app.py"), "--server.port", port])


if __name__ == "__main__":
    try:
        check_updates()
    except Exception as e:
        log(f"No se pudo comprobar la actualización: {e}")
        native_message("Sin conexión con actualizaciones", f"No se pudo consultar GitHub.\n\nSe abrirá la versión instalada.\n\nDetalle: {e}", "error")
    run_app()
