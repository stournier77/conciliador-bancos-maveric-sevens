"""Adaptación exclusiva de la carpeta de salida del programa Bancos al empaquetar."""
import ast
from pathlib import Path

def adapt(path):
    path=Path(path);source=path.read_text(encoding='utf-8');tree=ast.parse(source)
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='save_copy')
    replacement='''def save_copy(excel, filename, periodo, banco=None):
    from sevens_paths import save_result
    return save_result(excel, filename, prettify_bank_folder_name(banco or "Banco"))
'''
    lines=source.splitlines(keepends=True)
    path.write_text(''.join(lines[:node.lineno-1])+replacement+''.join(lines[node.end_lineno:]),encoding='utf-8')
