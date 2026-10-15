"""Puente compatible con el acceso de escritorio y el actualizador anterior."""
import hashlib,json,os,shutil,subprocess,sys,tempfile,time,urllib.request,zipfile
from pathlib import Path
UPDATER_VERSION='2.1.0'
ROOT=Path(__file__).resolve().parent
REPO='stournier77/conciliador-bancos-maveric-sevens'
MANAGED={'APP','assets','launchers','tests','requirements.txt','version.txt','settings.json','README.md','INSTALAR.command','INSTALAR.bat','Abrir Conciliador Bancos Maveric.command','Abrir Conciliador Bancos Maveric.bat'}
def fetch(url):
    request=urllib.request.Request(url,headers={'User-Agent':'Sevens-Bancos','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(request,timeout=30) as response:return response.read()
def current_version():
    p=ROOT/'version.txt'
    if not p.exists():p=ROOT/'APP/version.txt'
    return p.read_text().strip() if p.exists() else '0.0.0'
def main():
    try:
        release=json.loads(fetch(f'https://api.github.com/repos/{REPO}/releases/latest'))
        remote=release['tag_name'].lstrip('v')
        if tuple(map(int,remote.split('.')))>tuple(map(int,current_version().split('.'))):
            key='pc' if os.name=='nt' else 'mac'
            asset=next(a for a in release['assets'] if a['name']==f'latest_{key}.zip')
            url=asset['browser_download_url']
            if not url.startswith(f'https://github.com/{REPO}/releases/download/'):raise ValueError('Origen inesperado')
            content=fetch(url)
            if asset.get('digest','').startswith('sha256:') and hashlib.sha256(content).hexdigest()!=asset['digest'][7:]:raise ValueError('Checksum incorrecto')
            with tempfile.TemporaryDirectory() as temp:
                temp=Path(temp);archive=temp/'app.zip';archive.write_bytes(content);stage=temp/'stage';stage.mkdir()
                with zipfile.ZipFile(archive) as z:
                    for info in z.infolist():
                        p=Path(info.filename)
                        if p.is_absolute() or '..' in p.parts or '\\' in info.filename:raise ValueError('Ruta insegura')
                        if not p.parts or p.parts[0] not in MANAGED or info.is_dir():continue
                        target=stage/p;target.parent.mkdir(parents=True,exist_ok=True)
                        with z.open(info) as source,target.open('wb') as output:shutil.copyfileobj(source,output)
                if (stage/'version.txt').read_text().strip()!=remote:raise ValueError('Versión inválida')
                config=json.loads((stage/'settings.json').read_text())
                if config['repo']!=REPO:raise ValueError('Paquete de otra aplicación')
                backup=ROOT/'backups'/('puente_'+str(time.time_ns()));backup.mkdir(parents=True)
                copied=[]
                try:
                    for name in MANAGED:
                        source=stage/name;target=ROOT/name
                        if not source.exists():continue
                        if target.exists():
                            if target.is_dir():shutil.copytree(target,backup/name)
                            else:shutil.copy2(target,backup/name)
                        copied.append(name)
                        if source.is_dir():shutil.copytree(source,target,dirs_exist_ok=True)
                        else:shutil.copy2(source,target)
                except Exception:
                    for name in copied:
                        source=backup/name
                        if source.is_dir():shutil.copytree(source,ROOT/name,dirs_exist_ok=True)
                        elif source.exists():shutil.copy2(source,ROOT/name)
                    raise
    except Exception as exc:print('Actualización: se conserva la versión instalada.',exc,flush=True)
    support=ROOT/'launchers'
    if support.exists():
        if os.name=='nt':command=['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(support/'Abrir_Conciliador_Sevens_PC.ps1')]
        else:command=['/bin/zsh',str(support/'Abrir_Conciliador_Sevens_Mac.command')]
        raise SystemExit(subprocess.call(command))
    # Durante la transición, conservar la aplicación anterior si GitHub no responde.
    raise SystemExit(subprocess.call([sys.executable,'-m','streamlit','run',str(ROOT/'APP/app.py'),'--server.port=8772']))
if __name__=='__main__':main()
