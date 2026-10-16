"""Carpetas de resultados independientes de la instalación y de las actualizaciones."""
from datetime import datetime
from pathlib import Path
import os


def documents_folder() -> Path:
    if os.name == "nt":
        # Respeta Documentos incluso si Windows lo redirige a OneDrive u otra unidad.
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0:
            return Path(buffer.value)
    return Path.home() / "Documents"


KIND='Bancos'
INSTALL_FOLDER='App Conciliador Bancos Maveric'
OLD_FOLDER='Conciliador Bancos'

def app_folder() -> Path:
    return documents_folder() / INSTALL_FOLDER

def output_root() -> Path:
    return app_folder() / 'archivos conciliados'

def migrate_previous_results():
    """Copia resultados de la carpeta anterior; nunca elimina ni sobrescribe."""
    import hashlib,shutil
    old=documents_folder() / OLD_FOLDER / 'Archivos conciliados'
    target=output_root()
    if not old.is_dir():return
    for source in old.rglob('*.xlsx'):
        if not source.is_file() or source.is_symlink():continue
        relative=source.relative_to(old)
        if KIND in {'Bancos','Tarjetas'} and len(relative.parts)>1:
            relative=Path(relative.parts[0])/source.name
        destination=target/relative
        if destination.exists():
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            if hashlib.sha256(destination.read_bytes()).hexdigest()==digest:continue
            destination=destination.with_name(destination.stem+'_recuperado_'+digest[:12]+destination.suffix)
            if destination.exists():continue
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)


def save_result(excel,filename,bank_folder):
    folder=output_root()/Path(bank_folder).name
    folder.mkdir(parents=True,exist_ok=True)
    destination=folder/Path(filename).name
    destination.write_bytes(excel.getvalue())
    return destination
