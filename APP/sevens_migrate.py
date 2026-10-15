from pathlib import Path
import shutil,json

def migrate():
    app=Path(__file__).resolve().parent;source=app/'bootstrap_payload';root=app.parent
    if not source.exists():return
    version=(source/'version.txt').read_text().strip()
    marker=root/'logs'/'migracion_sevens.txt'
    if marker.exists() and marker.read_text().strip()==version:return
    manifest=json.loads((source/'payload.json').read_text())
    backup=root/'backups'/('migracion_'+version)
    written=[]
    try:
        for relative in manifest:
            src=source/relative;dst=root/relative
            if dst.exists():
                saved=backup/relative;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dst,saved)
            dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst);written.append(relative)
            if dst.suffix=='.command':dst.chmod(0o755)
        marker.parent.mkdir(parents=True,exist_ok=True);marker.write_text(version)
    except Exception:
        for relative in reversed(written):
            saved=backup/relative
            if saved.exists():shutil.copy2(saved,root/relative)
        raise
