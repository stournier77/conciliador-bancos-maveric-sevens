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

