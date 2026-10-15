"""Arranque y actualización; no importa ni modifica el motor de conciliación."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import webbrowser
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT/'settings.json').read_text())
REPO = SETTINGS['repo']
PORT = SETTINGS['port']
MANAGED = ('APP', 'APP_MAC', 'APP_PC', 'assets', 'launchers', 'tests', 'requirements.txt', 'version.txt', 'installed_version.txt', 'settings.json', 'README.md', 'Abrir Conciliador Bancos Maveric.command', 'Abrir Conciliador Bancos Maveric.bat', 'Abrir Conciliador IATA Maveric.command', 'Abrir Conciliador IATA Maveric.bat', 'INSTALAR.command', 'INSTALAR.bat')
APP_FOLDER = ROOT / ('APP' if SETTINGS['kind']=='Bancos' else ('APP_PC' if os.name=='nt' else 'APP_MAC'))
PLATFORM = 'pc' if os.name == 'nt' else 'mac'
RUNTIME = ROOT / ('runtime_' + PLATFORM)
UV = RUNTIME / 'uv' / ('uv.exe' if os.name == 'nt' else 'uv')
VENV = RUNTIME / '.venv'
PYTHON = VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
PROBE = "import sys; assert sys.version_info[:2] == (3,12); import numpy,pandas,streamlit,openpyxl,xlrd,pyarrow,xlsxwriter,requests,packaging,pypdf,PyPDF2; assert numpy.array([1,2]).sum()==3; assert pandas.DataFrame({'a':[1]}).a.sum()==1"

def run(args, timeout=600, **kwargs):
    return subprocess.run([str(a) for a in args], timeout=timeout, check=True, **kwargs)

def fetch(url, target=None):
    req = urllib.request.Request(url, headers={'User-Agent':'Sevens-Tarjetas', 'Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=8) as response:
        if target is None:
            return json.load(response)
        deadline = time.monotonic() + 90
        with open(target, 'wb') as out:
            total = 0
            while True:
                block = response.read(65536)
                if not block:
                    break
                total += len(block)
                if time.monotonic() > deadline or total > 50_000_000:
                    raise TimeoutError('Descarga excedió el límite')
                out.write(block)

def version(value):
    return tuple(int(p) for p in value.strip().lstrip('v').split('.'))

def validate_zip(archive, destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            path=Path(item.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in item.filename:
                raise ValueError('Ruta insegura en el paquete')
            parts=path.parts
            if 'Archivos APP' in parts:
                parts=parts[parts.index('Archivos APP')+1:]
            if not parts or item.is_dir(): continue
            if parts[0] not in MANAGED: continue
            target=destination.joinpath(*parts)
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(item) as source, target.open('wb') as output:
                shutil.copyfileobj(source,output)
    for required in ('settings.json','version.txt','launchers/arranque.py'):
        if not (destination/required).is_file():raise ValueError('Paquete incompleto: '+required)
    settings=json.loads((destination/'settings.json').read_text())
    if settings['repo'] != REPO or settings['port'] != PORT:raise ValueError('El paquete corresponde a otro conciliador')
    return destination


def deploy(source, target):
    """Respalda y reemplaza solamente archivos del programa; revierte ante error."""
    if source.resolve() == target.resolve():
        return
    target.mkdir(parents=True, exist_ok=True)
    backup = target / 'backups' / (time.strftime('%Y%m%d_%H%M%S') + '_' + str(time.time_ns()))
    backup.mkdir(parents=True)
    names = [n for n in MANAGED if (source / n).exists()]
    existed = set()
    for name in names:
        old = target / name
        if old.exists():
            existed.add(name)
            if old.is_dir(): shutil.copytree(old, backup / name)
            else: shutil.copy2(old, backup / name)
    try:
        for name in names:
            dst, src = target / name, source / name
            if dst.is_dir(): shutil.rmtree(dst)
            elif dst.exists(): dst.unlink()
            if src.is_dir(): shutil.copytree(src, dst)
            else: shutil.copy2(src, dst)
    except BaseException:
        for name in names:
            dst = target / name
            if dst.is_dir(): shutil.rmtree(dst)
            elif dst.exists(): dst.unlink()
            if name in existed:
                src = backup / name
                if src.is_dir(): shutil.copytree(src, dst)
                else: shutil.copy2(src, dst)
        raise
    if os.name != 'nt':
        for file in target.rglob('*.command'):
            if 'backups' not in file.parts: file.chmod(0o755)
    print('Respaldo del programa:', backup, flush=True)

def update():
    try:
        release = fetch(f'https://api.github.com/repos/{REPO}/releases/latest')
        current = (ROOT / 'version.txt').read_text().strip()
        if version(release['tag_name']) <= version(current): return False
        asset = next(a for a in release['assets'] if a['name'] == f'latest_{PLATFORM}.zip')
        url = asset['browser_download_url']
        if not url.startswith(f'https://github.com/{REPO}/releases/download/'):
            raise ValueError('Origen de actualización inesperado')
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            archive, stage = temp / 'update.zip', temp / 'new'
            fetch(url, archive)
            if asset.get('digest', '').startswith('sha256:'):
                if hashlib.sha256(archive.read_bytes()).hexdigest() != asset['digest'][7:]:
                    raise ValueError('Checksum incorrecto')
            validate_zip(archive, stage)
            if version((stage / 'version.txt').read_text()) != version(release['tag_name']):
                raise ValueError('La versión del paquete no coincide con el Release')
            deploy(stage, ROOT)
        return True
    except Exception as exc:
        print('Se continúa con la versión instalada. GitHub:', exc, flush=True)
        return False

def healthy():
    try:
        run([PYTHON, '-I', '-c', PROBE], timeout=25, stdout=subprocess.DEVNULL)
        fingerprint = hashlib.sha256((ROOT / 'requirements.txt').read_bytes()).hexdigest()
        marker = RUNTIME / 'requirements.sha256'
        return marker.exists() and marker.read_text() == fingerprint
    except (OSError, subprocess.SubprocessError): return False

def prepare():
    if healthy():
        print('Dependencias comprobadas.', flush=True)
        return
    print('Reparando entorno Python; los históricos no se modifican.', flush=True)
    # Guardar el entorno anterior en lugar de eliminarlo.
    base_python = getattr(sys, '_base_executable', None) or sys.executable
    if VENV.exists(): VENV.rename(RUNTIME / ('.venv_anterior_' + str(time.time_ns())))
    run([UV, 'venv', '--python', base_python, VENV])
    run([UV, 'pip', 'install', '--python', PYTHON, '-r', ROOT / 'requirements.txt'])
    run([PYTHON, '-I', '-c', PROBE], timeout=25)
    (RUNTIME / 'requirements.sha256').write_text(hashlib.sha256((ROOT / 'requirements.txt').read_bytes()).hexdigest())

def serve():
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try: sock.bind(('127.0.0.1', PORT))
        except OSError: raise RuntimeError(f'El puerto {PORT} está ocupado. Cerrá la instancia anterior; no se abrirá otro servicio.')
    logs = ROOT / 'logs'
    logs.mkdir(exist_ok=True)
    url = f'http://127.0.0.1:{PORT}'
    env = dict(os.environ, PYTHONUNBUFFERED='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    with open(logs / f'streamlit_{PLATFORM}.log', 'a') as log:
        process = subprocess.Popen([str(PYTHON), '-m', 'streamlit', 'run', 'app.py', '--server.headless=true', '--server.address=127.0.0.1', f'--server.port={PORT}', '--server.fileWatcherType=none', '--browser.gatherUsageStats=false', '--theme.base=light', '--theme.primaryColor=#087eb7', '--theme.backgroundColor=#f6f9fc', '--theme.secondaryBackgroundColor=#ffffff', '--theme.textColor=#18374c'], cwd=APP_FOLDER, env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if process.poll() is not None: raise RuntimeError('Streamlit terminó antes de iniciar; revisá el registro.')
                try:
                    with urllib.request.urlopen(url + '/_stcore/health', timeout=1) as response:
                        if response.status == 200: break
                except OSError: time.sleep(.5)
            else: raise TimeoutError('Streamlit no inició en 60 segundos')
            print('Aplicación lista:', url, flush=True)
            webbrowser.open(url)
            if process.wait() != 0: raise RuntimeError('Streamlit terminó con error')
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait()

def reopen_running():
    print('El conciliador ya está abierto o iniciando. Abriendo su ventana…', flush=True)
    url = f'http://127.0.0.1:{PORT}'
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url + '/_stcore/health', timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            time.sleep(.5)
    raise RuntimeError('La instancia anterior sigue iniciando. Revisá el registro de arranque.')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--install', action='store_true')
    parser.add_argument('--no-update', action='store_true')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    if args.install:
        from instalar import install
        install()
        return
    RUNTIME.mkdir(parents=True, exist_ok=True)
    # Bloqueo liberado por el sistema incluso después de una interrupción.
    lock = open(RUNTIME / 'arranque.lock', 'a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        reopen_running()
        return
    if not args.no_update and update():
        # Ejecutar código nuevo tras liberar el bloqueo.
        lock.close()
        run([sys.executable, ROOT / 'launchers/arranque.py', '--no-update'], timeout=None)
        return
    prepare()
    if not args.check_only: serve()

if __name__ == '__main__':
    try: main()
    except KeyboardInterrupt: pass
    except Exception as exc:
        print('ERROR:', exc, flush=True)
        sys.exit(1)
