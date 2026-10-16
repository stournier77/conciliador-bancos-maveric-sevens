import ast,hashlib,json,os,sys,tempfile,unittest,io
from pathlib import Path
from unittest.mock import patch,MagicMock
from datetime import datetime
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
SETTINGS=json.loads((ROOT/'settings.json').read_text(encoding='utf-8'))
KIND=SETTINGS['kind']
APP=ROOT/('APP' if KIND=='Bancos' else 'APP_MAC')
sys.path.insert(0,str(APP));sys.path.insert(0,str(ROOT/'launchers'))
import arranque
import sevens_paths

class AppTests(unittest.TestCase):
    def test_https_uses_verified_native_fallback(self):
        import urllib.error,subprocess
        commands=[]
        def native(command,**kwargs):
            commands.append(command)
            target=kwargs['env']['SEVENS_DOWNLOAD_TARGET'] if os.name=='nt' else command[-1]
            Path(target).write_bytes(b'{"ok":true}')
            return subprocess.CompletedProcess(command,0)
        with patch('urllib.request.urlopen',side_effect=urllib.error.URLError('CERTIFICATE_VERIFY_FAILED')),patch('subprocess.run',side_effect=native):
            self.assertEqual(arranque.fetch('https://github.com/example'),{'ok':True})
        self.assertEqual(len(commands),1)
        self.assertNotIn('--insecure',commands[0]);self.assertNotIn('-k',commands[0])
        self.assertNotIn('ServerCertificateValidationCallback',' '.join(commands[0]))
        self.assertEqual(commands[0][0],'powershell' if os.name=='nt' else 'curl')

    def test_engine_unchanged(self):
        excluded={'out_base','save_copy'} if KIND=='Bancos' else {'get_reports_base_dir','output_name'}
        actual=[[n.name,hashlib.sha256(ast.dump(n,include_attributes=False).encode()).hexdigest()] for n in ast.parse((APP/'app.py').read_text(encoding='utf-8')).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name not in excluded]
        self.assertEqual(actual,json.loads((ROOT/'tests/engine_fingerprints.json').read_text(encoding='utf-8')))
        if KIND=='IATA':self.assertEqual((ROOT/'APP_MAC/app.py').read_bytes(),(ROOT/'APP_PC/app.py').read_bytes())

    def test_interface_and_output_paths(self):
        from streamlit.testing.v1 import AppTest
        import re
        source=(APP/'app.py').read_text(encoding='utf-8')
        device=next(iter(re.findall(r'[A-F0-9]{8}(?:-[A-F0-9]{4}){3}-[A-F0-9]{12}',source)))
        with tempfile.TemporaryDirectory() as temporary, patch('sevens_paths.documents_folder',return_value=Path(temporary)), patch('sevens_migrate.migrate'), patch('subprocess.check_output',return_value='"IOPlatformUUID" = "'+device+'"' ), patch('platform.system',return_value='Darwin'):
            # Bancos conserva su archivo local de equipos, aislado en la prueba.
            if KIND=='Bancos':
                original=Path.exists
                # Evita crear configuración de autorización dentro del proyecto al probar.
                auth=ROOT/'authorized_machines.json'
                existed=auth.exists()
            app=AppTest.from_file(str(APP/'app.py'),default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertEqual([b.label for b in app.sidebar.button],['Abrir carpeta de conciliaciones','Cerrar aplicación'])
            self.assertTrue(next(b for b in app.button if b.label=='GENERAR CONCILIACIÓN').disabled)
            expected=2 if KIND=='Bancos' else 3
            self.assertEqual(len(app.get('file_uploader')),expected)
            self.assertEqual(sevens_paths.output_root(),Path(temporary)/('App Conciliador '+KIND+' Maveric')/'archivos conciliados')
            if KIND=='Bancos' and not existed and auth.exists():auth.unlink()

    def test_reopen_running(self):
        response=MagicMock();response.__enter__.return_value.status=200
        with patch.object(arranque.urllib.request,'urlopen',return_value=response),patch.object(arranque.webbrowser,'open') as browser:
            arranque.reopen_running();browser.assert_called_once_with('http://127.0.0.1:'+str(SETTINGS['port']))

    def test_update_preserves_results_and_configuration(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=root/'source';target=root/'target'
            source.mkdir();target.mkdir();(source/'version.txt').write_text('new');(target/'version.txt').write_text('old')
            (target/'authorized_machines.json').write_text('local-config');(target/'runtime_pc').mkdir();(target/'runtime_pc/keep').write_text('runtime')
            history=root/'Archivos conciliados';history.mkdir();(history/'keep.xlsx').write_bytes(b'history')
            arranque.deploy(source,target)
            self.assertEqual((target/'authorized_machines.json').read_text(encoding='utf-8'),'local-config')
            self.assertEqual((target/'runtime_pc/keep').read_text(encoding='utf-8'),'runtime')
            self.assertEqual((history/'keep.xlsx').read_bytes(),b'history')

    def test_migration_preserves_configuration_and_shortcut(self):
        import shutil,importlib.util
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);app=root/'APP';app.mkdir();payload=app/'bootstrap_payload';payload.mkdir();(payload/'version.txt').write_text('test');(payload/'settings.json').write_text('{}');(payload/'payload.json').write_text(json.dumps(['version.txt','settings.json']))
            (root/'authorized_machines.json').write_text('private');(root/'desktop.lnk').write_bytes(b'icon')
            file=app/'sevens_migrate.py';shutil.copy2(APP/'sevens_migrate.py',file)
            spec=importlib.util.spec_from_file_location('migration_test',file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.migrate();module.migrate()
            self.assertEqual((root/'authorized_machines.json').read_text(encoding='utf-8'),'private');self.assertEqual((root/'desktop.lnk').read_bytes(),b'icon');self.assertEqual((root/'version.txt').read_text(encoding='utf-8'),'test')

if __name__=='__main__':unittest.main()
