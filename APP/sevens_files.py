"""Selección local desde la carpeta de la app; conserva también arrastrar archivos."""
from pathlib import Path
import io,json,mimetypes,os,platform,re,subprocess
import streamlit as st

MAX_BYTES=200*1024*1024

class SelectedFile(io.BytesIO):
    def __init__(self,name,data):
        super().__init__(data)
        self.name=name
        self.size=len(data)
        self.type=mimetypes.guess_type(name)[0] or 'application/octet-stream'

def choose_file(folder,extensions):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    extensions=[str(x).lstrip('.').lower() for x in extensions or []]
    if any(not re.fullmatch(r'[a-z0-9]+',x) for x in extensions):raise ValueError('Tipo de archivo inválido')
    if platform.system()=='Darwin':
        # Finder no siempre reconoce extensiones como tipos de AppleScript.
        # Mostrar archivos y validar su extensión después de seleccionarlos.
        script='on run argv\nset selectedFile to choose file with prompt "Seleccionar archivo para conciliar" default location (POSIX file (item 1 of argv))\nreturn POSIX path of selectedFile\nend run'
        result=subprocess.run(['osascript','-e',script,'--',str(folder)],capture_output=True,text=True,timeout=600)
        if result.returncode and '-128' in result.stderr:return None
        if result.returncode:raise RuntimeError('No se pudo abrir el selector de archivos de macOS.')
        chosen=result.stdout.strip()
    elif os.name=='nt':
        env=dict(os.environ,SEVENS_INPUT_FOLDER=str(folder),SEVENS_INPUT_FILTER='Archivos compatibles|'+(';'.join('*.'+x for x in extensions) or '*.*'))
        script="""$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Windows.Forms
$dialog=New-Object System.Windows.Forms.OpenFileDialog
$dialog.InitialDirectory=$env:SEVENS_INPUT_FOLDER
$dialog.Filter=$env:SEVENS_INPUT_FILTER
$dialog.Title='Seleccionar archivo para conciliar'
$dialog.RestoreDirectory=$true
$owner=New-Object System.Windows.Forms.Form
$owner.TopMost=$true
try { if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) { ConvertTo-Json -Compress -InputObject $dialog.FileName } } finally { $dialog.Dispose(); $owner.Dispose() }
"""
        result=subprocess.run(['powershell','-NoProfile','-STA','-NonInteractive','-Command',script],env=env,capture_output=True,encoding='utf-8-sig',timeout=600,check=True)
        chosen=json.loads(result.stdout) if result.stdout.strip() else None
    else:raise RuntimeError('Selector de escritorio disponible en Mac y Windows.')
    if not chosen:return None
    file=Path(chosen)
    if extensions and file.suffix.lower().lstrip('.') not in extensions:raise ValueError('Ese tipo de archivo no es compatible.')
    if file.stat().st_size>MAX_BYTES:raise ValueError('El archivo supera los 200 MB.')
    with file.open('rb') as source:data=source.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:raise ValueError('El archivo supera los 200 MB.')
    return file.name,data

def install_native_uploaders(folder_factory):
    """Adaptador de presentación: los motores reciben el mismo archivo en memoria."""
    if platform.system()!='Darwin' and os.name!='nt':return
    original=getattr(st.file_uploader,'__dict__',{}).get('_sevens_original',st.file_uploader)
    def upload(label,type=None,accept_multiple_files=False,key=None,**kwargs):
        if accept_multiple_files or key is None:
            return original(label,type=type,accept_multiple_files=accept_multiple_files,key=key,**kwargs)
        state='_sevens_selected_'+key;generation=state+'_generation';error=state+'_error'
        def changed():
            st.session_state.pop(state,None)
        def select():
            try:
                selected=choose_file(folder_factory(),type)
                if selected is not None:
                    st.session_state[state]=selected
                    st.session_state[generation]=st.session_state.get(generation,0)+1
                st.session_state.pop(error,None)
            except Exception as exc:st.session_state[error]=str(exc)
        def clear():
            st.session_state.pop(state,None)
            st.session_state[generation]=st.session_state.get(generation,0)+1
        with st.container(key='desktop_upload_'+key):
            options=dict(kwargs)
            callback=options.pop('on_change',None)
            def on_change():
                changed()
                if callback:callback()
            gen=st.session_state.get(generation,0)
            uploaded=original(label,type=type,accept_multiple_files=False,key=key if not gen else key+'_desktop_'+str(gen),on_change=on_change,**options)
            st.button('Seleccionar archivo',key='desktop_pick_'+key,on_click=select,disabled=kwargs.get('disabled',False))
            if state in st.session_state and uploaded is None:
                name,data=st.session_state[state]
                st.caption(name)
                st.button('Quitar archivo',key='desktop_clear_'+key,on_click=clear)
                uploaded=SelectedFile(name,data)
            if error in st.session_state:st.error(st.session_state[error])
        return uploaded
    upload._sevens_original=original
    st.file_uploader=upload
    st.markdown('''<style>
[class*="st-key-desktop_upload_"]{position:relative}
[class*="st-key-desktop_upload_"] [data-testid="stFileUploaderDropzone"]{justify-content:flex-start!important;padding-top:22px}
[class*="st-key-desktop_upload_"] [data-testid="stFileUploaderDropzone"]>span{display:none!important}
[class*="st-key-desktop_pick_"]{position:absolute!important;top:58px;left:0;width:100%;display:flex;justify-content:center;z-index:1}
[class*="st-key-desktop_pick_"] [data-testid="stButton"]{display:flex;justify-content:center;width:100%}
[class*="st-key-desktop_pick_"] [data-testid="stMarkdownContainer"] p{font-size:13px!important;white-space:nowrap}
[class*="st-key-desktop_pick_"] button{width:154px;max-width:calc(100% - 28px);min-height:34px;margin:0 auto;background:var(--sevens-soft);border:1px solid #a4c7dc;border-radius:8px;color:var(--sevens-ink);font-size:13px}
[class*="st-key-desktop_clear_"] button{font-size:12px;padding:2px 8px;min-height:28px}
</style>''',unsafe_allow_html=True)
