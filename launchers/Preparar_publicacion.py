from pathlib import Path
import json,sys,shutil,zipfile
from arranque import ROOT,MANAGED,SETTINGS,validate_zip

def build(destination):
    destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=True)
    version=(ROOT/'version.txt').read_text().strip()
    if version!=SETTINGS['version']:raise ValueError('Versión incompatible con settings.json')
    # Incluir el soporte dentro de cada APP para los actualizadores anteriores.
    folders=['APP'] if SETTINGS['kind']=='Bancos' else ['APP_MAC','APP_PC']
    support=['launchers','assets','requirements.txt','settings.json','version.txt','README.md','INSTALAR.command','INSTALAR.bat']
    support += [p.name for p in ROOT.glob('Abrir Conciliador *')]
    if (ROOT/'installed_version.txt').exists():support.append('installed_version.txt')
    for folder in folders:
        payload=ROOT/folder/'bootstrap_payload'
        if payload.exists():shutil.rmtree(payload)
        payload.mkdir()
        manifest=[]
        for name in support:
            src=ROOT/name
            for file in (src.rglob('*') if src.is_dir() else [src]):
                if not file.is_file() or '__pycache__' in file.parts or file.suffix=='.pyc':continue
                rel=file.relative_to(ROOT);dst=payload/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dst);manifest.append(rel.as_posix())
        (payload/'payload.json').write_text(json.dumps(manifest))
    for platform in ['mac','pc']:
        prefix='' if SETTINGS['kind']=='Bancos' else 'Instalador Conciliador IATA Maveric/Archivos APP/'
        archive=destination/f'latest_{platform}.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for name in MANAGED:
                src=ROOT/name
                for file in (src.rglob('*') if src.is_dir() else [src]):
                    if file.is_file() and '__pycache__' not in file.parts and file.suffix!='.pyc':z.write(file,prefix+file.relative_to(ROOT).as_posix())
            if prefix:
                install='INSTALAR.command' if platform=='mac' else 'INSTALAR.bat'
                wrapper = '#!/bin/zsh\nROOT="$(cd \"$(dirname \"$0\")\" && pwd)"\nexec /bin/zsh "$ROOT/Archivos APP/INSTALAR.command"\n' if platform=='mac' else '@echo off\r\ncall "%~dp0Archivos APP\\INSTALAR.bat"\r\n'
                info=zipfile.ZipInfo('Instalador Conciliador IATA Maveric/'+install);info.external_attr=0o100755<<16;z.writestr(info,wrapper)
        import tempfile
        with tempfile.TemporaryDirectory() as temp:validate_zip(archive,Path(temp))
    (destination/'version.txt').write_text(version+'\n')
    if SETTINGS['kind']=='Bancos':
        with zipfile.ZipFile(destination/'latest_app.zip','w',zipfile.ZIP_DEFLATED) as z:
            for file in (ROOT/'APP').rglob('*'):
                if file.is_file() and '__pycache__' not in file.parts and file.suffix!='.pyc':z.write(file,file.relative_to(ROOT))
    print('Paquetes validados:',destination)

if __name__=='__main__':build(sys.argv[1] if len(sys.argv)>1 else ROOT/'build')
