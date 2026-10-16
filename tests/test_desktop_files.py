import importlib,io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess
ROOT=Path(__file__).resolve().parents[1]
KIND=json.loads((ROOT/'settings.json').read_text(encoding='utf-8'))['kind'] if (ROOT/'settings.json').exists() else 'Tarjetas'
APP=ROOT/('app' if KIND=='Tarjetas' else 'APP' if KIND=='Bancos' else 'APP_MAC')
sys.path.insert(0,str(APP))
import sevens_files
paths=importlib.import_module('paths' if KIND=='Tarjetas' else 'sevens_paths')

class DesktopFilesTests(unittest.TestCase):
    def test_mac_picker_starts_in_app_folder_and_returns_unchanged_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary)/'Maveric con espacios.xlsx';source.write_bytes(b'original')
            initial=Path(temporary)/paths.INSTALL_FOLDER
            def native(command,**kwargs):
                self.assertEqual(command[-1],str(initial.resolve()))
                self.assertIn('default location',command[2]);self.assertIn('of type {"xlsx", "xls"}',command[2])
                return CompletedProcess(command,0,str(source)+'\n','')
            with patch.object(sevens_files.platform,'system',return_value='Darwin'),patch.object(sevens_files.subprocess,'run',side_effect=native):
                name,data=sevens_files.choose_file(initial,['xlsx','xls'])
            self.assertEqual((name,data),(source.name,b'original'))
            selected=sevens_files.SelectedFile(name,data);self.assertEqual(selected.read(),b'original');self.assertEqual(selected.getvalue(),b'original')
    def test_cancel_does_not_select_or_change_a_file(self):
        with tempfile.TemporaryDirectory() as t,patch.object(sevens_files.platform,'system',return_value='Darwin'),patch.object(sevens_files.subprocess,'run',return_value=CompletedProcess([],1,'','User canceled. (-128)')):
            self.assertIsNone(sevens_files.choose_file(Path(t),['xlsx']))
    @unittest.skipUnless(os.name=='nt','Windows native dialog')
    def test_windows_picker_uses_initial_directory_and_utf8(self):
        with tempfile.TemporaryDirectory() as t:
            f=Path(t)/'Banco español.xlsx';f.write_bytes(b'bytes')
            def native(command,**kwargs):
                self.assertIn('-STA',command);self.assertEqual(kwargs['env']['SEVENS_INPUT_FOLDER'],str(Path(t).resolve()))
                self.assertIn('InitialDirectory',command[-1]);self.assertIn('*.xlsx',kwargs['env']['SEVENS_INPUT_FILTER'])
                return CompletedProcess(command,0,json.dumps(str(f)), '')
            with patch.object(sevens_files.subprocess,'run',side_effect=native):
                self.assertEqual(sevens_files.choose_file(t,['xlsx']),(f.name,b'bytes'))
    def test_history_migration_preserves_originals_and_conflicting_results(self):
        with tempfile.TemporaryDirectory() as t,patch.object(paths,'documents_folder',return_value=Path(t)):
            old=Path(t)/paths.OLD_FOLDER/'Archivos conciliados'
            group='Brex' if paths.KIND=='Tarjetas' else 'Banco Santander' if paths.KIND=='Bancos' else '1-7 oct 26'
            src=old/group/('20261001_a_20261007' if paths.KIND in {'Bancos','Tarjetas'} else '')/'resultado.xlsx'
            src.parent.mkdir(parents=True);src.write_bytes(b'original')
            out=paths.output_root()/group/'resultado.xlsx';out.parent.mkdir(parents=True);out.write_bytes(b'different')
            paths.migrate_previous_results();paths.migrate_previous_results()
            self.assertEqual(src.read_bytes(),b'original');self.assertEqual(out.read_bytes(),b'different')
            recovered=list(out.parent.glob('*recuperado*.xlsx'));self.assertEqual(len(recovered),1);self.assertEqual(recovered[0].read_bytes(),b'original')
            self.assertEqual(paths.app_folder(),Path(t)/paths.INSTALL_FOLDER)
    def test_native_picker_feeds_the_existing_uploader_contract(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as t:
            script=Path(t)/'preview.py'
            script.write_text('import sys\nsys.path.insert(0,'+repr(str(APP))+')\nimport streamlit as st\nfrom sevens_files import install_native_uploaders\nfrom pathlib import Path\ninstall_native_uploaders(lambda:Path('+repr(t)+'))\nf=st.file_uploader("Excel",type=["xlsx"],key="test_file")\nif f:st.success(f.name+":"+f.getvalue().decode())\n',encoding='utf-8')
            with patch.object(sevens_files.platform,'system',return_value='Darwin'),patch.object(sevens_files,'choose_file',return_value=('ejemplo.xlsx',b'content')) as chooser:
                app=AppTest.from_file(str(script)).run()
                next(b for b in app.button if b.label=='Seleccionar archivo').click().run()
                self.assertFalse(app.exception);self.assertEqual(app.success[0].value,'ejemplo.xlsx:content');self.assertEqual(chooser.call_args.args[0],Path(t))
                next(b for b in app.button if b.label=='Quitar archivo').click().run()
                self.assertFalse(app.success)

    def test_platform_dialog_scripts_are_valid(self):
        import ast
        source=(APP/'sevens_files.py').read_text(encoding='utf-8')
        constants=[n.value for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
        if os.name=='nt':
            import subprocess
            code=next(c for c in constants if c.startswith("$ErrorActionPreference"))
            env=dict(os.environ,SEVENS_TEST_SCRIPT=code)
            subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',"$tokens=$null; $errors=$null; [void][System.Management.Automation.Language.Parser]::ParseInput($env:SEVENS_TEST_SCRIPT,[ref]$tokens,[ref]$errors); if($errors.Count){throw ($errors | Out-String)}"],env=env,check=True,capture_output=True)
        elif sys.platform=='darwin':
            import subprocess
            with tempfile.TemporaryDirectory() as t:
                commands=[]
                def capture(command,**kwargs):
                    commands.append(command)
                    return CompletedProcess(command,1,'','User canceled. (-128)')
                with patch.object(sevens_files.subprocess,'run',side_effect=capture):sevens_files.choose_file(t,['xlsx','xls'])
                file=Path(t)/'dialog.applescript';file.write_text(commands[0][2],encoding='utf-8')
                subprocess.run(['osacompile','-o',str(Path(t)/'dialog.scpt'),str(file)],check=True,capture_output=True)

    def test_bank_storage_goes_directly_into_bank_folder(self):
        import ast,importlib.util
        with tempfile.TemporaryDirectory() as t,patch.object(paths,'documents_folder',return_value=Path(t)):
            spec=importlib.util.spec_from_file_location('storage_adapter',ROOT/'launchers/actualizar_guardado.py');adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
            copy=Path(t)/'app.py';copy.write_text((APP/'app.py').read_text(encoding='utf-8'),encoding='utf-8');adapter.adapt(copy)
            tree=ast.parse(copy.read_text(encoding='utf-8'));node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='save_copy')
            namespace={'prettify_bank_folder_name':lambda x:'Banco Santander'};exec(compile(ast.Module(body=[node],type_ignores=[]),'storage','exec'),namespace)
            result=namespace['save_copy'](io.BytesIO(b'excel'),'resultado.xlsx','20261001_a_20261007','SANTANDER')
            self.assertEqual(result,paths.output_root()/'Banco Santander/resultado.xlsx');self.assertEqual(result.read_bytes(),b'excel')

if __name__=='__main__':unittest.main()
