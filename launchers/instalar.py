from pathlib import Path
import json,os,shutil,subprocess,plistlib
from arranque import ROOT,SETTINGS,deploy
from documentos import documents_folder

def install():
    target=documents_folder()/SETTINGS['install_folder']/'Archivos APP'
    deploy(ROOT,target)
    kind=SETTINGS['kind']
    legacy='Abrir Conciliador '+kind+' Maveric'
    name='Conciliador Bancos Maveric Sevens' if kind=='Bancos' else 'Conciliador IATA Maveric'
    if os.name=='nt':
        script='''param($Target,$Icon,$Name,$WorkDir)
$shell=New-Object -ComObject WScript.Shell
$link=$shell.CreateShortcut((Join-Path $shell.SpecialFolders.Item('Desktop') ($Name+'.lnk')))
$link.TargetPath=$Target;$link.WorkingDirectory=$WorkDir;$link.IconLocation=$Icon;$link.Save()
'''
        temporary=target/'logs';temporary.mkdir(exist_ok=True)
        file=temporary/'crear_acceso.ps1';file.write_text(script,encoding='utf-8-sig')
        icon='icon_sevens_bancos.ico' if kind=='Bancos' else 'Conciliador_IATA_Maveric.ico'
        subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(file),str(target/(legacy+'.bat')),str(target/'assets'/icon),name,str(target)],check=True)
    else:
        app=Path.home()/'Desktop'/(name+'.app')
        (app/'Contents/MacOS').mkdir(parents=True,exist_ok=True)
        (app/'Contents/Resources').mkdir(exist_ok=True)
        launcher=app/'Contents/MacOS/InicioSevens'
        import shlex
        launcher.write_text('#!/bin/zsh\nexec '+shlex.quote(str(target/(legacy+'.command')))+'\n');launcher.chmod(0o755)
        icon='AppIcon.icns' if kind=='Bancos' else 'Conciliador_IATA_Maveric.icns'
        shutil.copy2(target/'assets'/icon,app/'Contents/Resources/AppIcon.icns')
        info=dict(CFBundleExecutable='InicioSevens',CFBundleName=name,CFBundleIdentifier='uy.sevens.conciliador.'+kind.lower(),CFBundleIconFile='AppIcon',CFBundlePackageType='APPL',CFBundleVersion=SETTINGS['version'])
        (app/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
        subprocess.run(['codesign','--force','--deep','--sign','-',str(app)],check=True)
    print('Instalación lista:',target)
