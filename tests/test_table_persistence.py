"""Documento v6, pacotes .fornax e abertura segura da tabela no editor."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch,Mock
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parent/'performance'))
from PySide6.QtCore import QBuffer,QByteArray,QIODevice,QCoreApplication,QEvent
from PySide6.QtGui import QImage,QColor,QTextCursor
from PySide6.QtWidgets import QApplication
from core.model_document import (
    normalize_model_document,persistent_model_document,save_model_document,load_model_document,
    adapt_model_page,replace_model_page,add_blank_back_page,clear_model_page,remove_model_page,
    add_model_table,ModelValidationError,UnsupportedSchemaError,
)
from core.table_model import new_table,duplicate_table,set_cell_html,merge_cells,cell_at,format_cells
from core.document_layers import layer_entries
from core.organogram import add_organogram,artwork_bounds
from core.fornax_container import (
    save_public_fornax,open_public_fornax,save_protected_fornax,unlock_fornax,
    FULL_MODE,SIGNATURES_MODE,PUBLIC_DOCUMENT_PATH,
)
from core.html_utils import TextOnlyDocument
from core.ui_font import install_ui_font
from features.editor.model_adapter import prepare_scene_page
from table_document_fixtures import documents


def base_document():
    return normalize_model_document(dict(canvas_size={'w':600,'h':400},target_w_mm=50,target_h_mm=34,
                                        boxes=[],images=[],shapes=[],signatures=[],placeholders=[]))


def example_document():
    table=set_cell_html(new_table(4,4,width=600,height=400),0,0,'<p><b>{nome}</b></p>')
    return add_model_table(base_document(),table)


class TablePersistenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        install_ui_font(cls.app)
        cls.callback_errors=[]
        cls.previous_hook=sys.excepthook
        sys.excepthook=lambda kind,value,trace:cls.callback_errors.append(str(value))

    @classmethod
    def tearDownClass(cls):
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        cls.app.processEvents()
        sys.excepthook=cls.previous_hook
        if cls.callback_errors:
            raise AssertionError('Exceções de callbacks Qt: '+repr(cls.callback_errors))

    def setUp(self):
        self.temporary=TemporaryDirectory(prefix='fornax-table-persist-')
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.enterContext(patch('core.paths._data_home',return_value=self.root/'data'))

    def test_v3_v4_v5_without_tables_keep_original_versions_and_are_not_mutated(self):
        legacy=dict(schema_version=3,canvas_size={'w':200,'h':100},boxes=[],images=[],shapes=[],signatures=[])
        before=deepcopy(legacy)
        v4=normalize_model_document(legacy)
        self.assertEqual(legacy,before)
        self.assertEqual(v4['schema_version'],4)
        v5=add_organogram(v4)
        self.assertEqual(normalize_model_document(v5)['schema_version'],5)
        source=self.root/'legacy.json';source.write_text(json.dumps(legacy))
        original=source.read_bytes();load_model_document(source)
        self.assertEqual(source.read_bytes(),original)

    def test_tables_require_v6_unknown_versions_and_root_collection_rejected(self):
        source=example_document()
        for version in (3,4,5,7,True,6.0):
            wrong=deepcopy(source);wrong['schema_version']=version
            with self.subTest(version=version),self.assertRaises((ModelValidationError,UnsupportedSchemaError)):
                normalize_model_document(wrong)
        wrong=deepcopy(source);wrong['tables']=wrong['pages'][0]['tables']
        with self.assertRaises(ModelValidationError):normalize_model_document(wrong)

    def test_malformed_tables_are_controlled_model_errors_before_copy(self):
        document=example_document()
        for value in (None,42,'invalid',{},[False]):
            source=deepcopy(document);source['pages'][0]['tables']=value
            with self.subTest(value=value),self.assertRaises(ModelValidationError):
                normalize_model_document(source)
        source=deepcopy(document)
        source['pages'][0]['tables'][0]['cells'][0]['row_span']=999
        with patch('core.model_document.deepcopy',side_effect=AssertionError('Não copiar entrada inválida')):
            with self.assertRaises(ModelValidationError):normalize_model_document(source)

    def test_persist_reopen_atomic_backup_and_no_table_selection_in_json(self):
        document=example_document();before=deepcopy(document)
        path=save_model_document(document,self.root/'model')
        first=path.read_bytes()
        saved=persistent_model_document(load_model_document(path))
        self.assertEqual(saved['pages'][0]['tables'],document['pages'][0]['tables'])
        changed=deepcopy(document);changed['name']='Outra versão'
        save_model_document(changed,self.root/'model')
        self.assertEqual(path.with_name(path.name+'.bak').read_bytes(),first)
        self.assertEqual(document,before)
        bad=deepcopy(changed);bad['pages'][0]['tables'][0]['selection']=[0,0]
        original=path.read_bytes()
        with self.assertRaises(ModelValidationError):save_model_document(bad,self.root/'model')
        self.assertEqual(path.read_bytes(),original)

    def test_public_and_fully_protected_container_roundtrip_is_equivalent(self):
        document=example_document();expected=persistent_model_document(document)
        public=self.root/'public.fornax';encrypted=self.root/'full.fornax'
        save_public_fornax(document,public)
        self.assertEqual(open_public_fornax(public).document(),expected)
        save_protected_fornax(document,encrypted,'senha-sintetica-etapa02',mode=FULL_MODE)
        self.assertEqual(unlock_fornax(encrypted,'senha-sintetica-etapa02').document(),expected)
        with zipfile.ZipFile(encrypted) as archive:
            self.assertNotIn(PUBLIC_DOCUMENT_PATH,archive.namelist())
            self.assertFalse(any(b'{nome}' in archive.read(name) for name in archive.namelist()))

    def test_signature_protection_preserves_public_table_and_authorized_signature(self):
        document=example_document()
        signature=dict(object_id='signature-test',signature_id='sig-table-test',path='sign.png',x=0,y=0,w=30,h=20)
        document['pages'][0]['signatures'].append(signature)
        document['pages'][0]['layer_order'].append(signature['object_id'])
        image=QImage(4,4,QImage.Format.Format_ARGB32);image.fill(QColor('#113344'))
        buffer=QBuffer();buffer.open(QIODevice.OpenModeFlag.WriteOnly);image.save(buffer,'PNG')
        asset=bytes(buffer.data());path=self.root/'signatures.fornax'
        save_protected_fornax(document,path,'senha-sintetica-etapa02',mode=SIGNATURES_MODE,
                             asset_provider=lambda reference:asset)
        public=open_public_fornax(path).document()
        self.assertEqual(public['pages'][0]['tables'],document['pages'][0]['tables'])
        opened=unlock_fornax(path,'senha-sintetica-etapa02')
        self.assertEqual(opened.document()['pages'][0]['tables'],document['pages'][0]['tables'])
        self.assertEqual(opened.asset(opened.document()['pages'][0]['signatures'][0]['path']),asset)

    def test_recovery_snapshot_keeps_tables_and_original_in_all_protection_modes(self):
        from core.fornax_session import FornaxSessionManager
        from core.fornax_container import PUBLIC_MODE
        document=example_document()
        signature_path=self.root/'recovery-signature.png'
        image=QImage(4,4,QImage.Format.Format_ARGB32);image.fill(QColor('#113344'))
        self.assertTrue(image.save(str(signature_path)))
        document['pages'][0]['signatures'].append(dict(object_id='recovery-signature',
            signature_id='sig-recovery',path=str(signature_path),x=0,y=0,w=30,h=20))
        document['pages'][0]['layer_order'].append('recovery-signature')
        document['protection_preferences']={'public_signatures_acknowledged':True}
        for mode in (PUBLIC_MODE,SIGNATURES_MODE,FULL_MODE):
            with self.subTest(mode=mode):
                path=self.root/(mode+'.fornax')
                if mode==PUBLIC_MODE:
                    save_public_fornax(document,path)
                else:
                    save_protected_fornax(document,path,'senha-sintetica',mode=mode)
                original=path.read_bytes()
                sessions=FornaxSessionManager()
                self.addCleanup(sessions.close)
                if mode==PUBLIC_MODE:sessions.select(path)
                else:sessions.unlock(path,'senha-sintetica')
                changed=deepcopy(sessions.document())
                changed['pages'][0]['tables'][0]['cells'][0]['html']='<p><b>Atualização {nome}</b></p>'
                recovery=self.root/(mode+'-recovery.fornax')
                sessions.write_recovery(changed,recovery)
                reopened=sessions.read_recovery(recovery).document()
                self.assertEqual(reopened['schema_version'],6)
                self.assertEqual(reopened['pages'][0]['tables'],changed['pages'][0]['tables'])
                self.assertEqual(path.read_bytes(),original)
                if mode==FULL_MODE:
                    with zipfile.ZipFile(recovery) as package:
                        self.assertNotIn(PUBLIC_DOCUMENT_PATH,package.namelist())
                sessions.close()

    def test_adapt_replace_collect_fields_and_layers_on_front_back_and_board(self):
        document=example_document()
        self.assertEqual(document['placeholders'],['nome'])
        document=add_blank_back_page(document)
        back=set_cell_html(new_table(1,1,name='Verso'),0,0,'<p>{no<b>ta</b>}</p>')
        document=add_model_table(document,back,'back')
        self.assertEqual(document['placeholders'],['nome','nota'])
        adapted=adapt_model_page(document,'back')
        self.assertEqual(adapted['__document_schema_version'],6)
        self.assertEqual(layer_entries(adapted)[-1][1],'table')
        prepared=prepare_scene_page(adapted)
        self.assertIsInstance(prepared['tables'][0]['layer_id'],int)
        table=prepared['tables'][0];table['x']=40
        replaced=replace_model_page(document,prepared,'back')
        self.assertEqual(replaced['pages'][1]['tables'][0]['x'],40)
        self.assertEqual(document['pages'][1]['tables'][0]['x'],0)
        self.assertEqual(replaced['schema_version'],6)

    def test_replacing_page_promotes_schema_and_no_downgrade_after_last_table(self):
        base=base_document();page=adapt_model_page(base)
        table=new_table(1,1);page['tables']=[table];page['layer_order']=[table['object_id']]
        result=replace_model_page(base,page)
        self.assertEqual(result['schema_version'],6)
        cleared=clear_model_page(result,'front')
        self.assertEqual(cleared['schema_version'],6)
        self.assertFalse(cleared['pages'][0]['tables'])

    def test_organogram_version_preserved_mutual_exclusion_and_table_bounds(self):
        front=example_document();board=add_organogram(front)
        self.assertEqual(board['schema_version'],6)
        with self.assertRaises(ModelValidationError):add_blank_back_page(board)
        self.assertEqual(remove_model_page(board,'organogram')['schema_version'],6)
        board_table=new_table(1,1,name='Quadro')
        board_table.update(x=100,y=200,rotation=90,board_behind=True)
        board=add_model_table(board,board_table,'organogram')
        page=adapt_model_page(board,'organogram')
        replaced=replace_model_page(board,page,'organogram')
        self.assertEqual(replaced['organogram']['tables'],board['organogram']['tables'])
        bounds=artwork_bounds(board['organogram'])
        self.assertGreaterEqual(bounds.width(),300)
        self.assertGreaterEqual(bounds.height(),600)
        angled=deepcopy(board['organogram']);angled['tables'][0]['rotation']=45
        angled_bounds=artwork_bounds(angled)
        expected=(600+300+4)/(2**.5)  # Contorno de 2 unidades nos dois eixos.
        self.assertAlmostEqual(angled_bounds.width(),expected)
        self.assertAlmostEqual(angled_bounds.height(),expected)
        after=clear_model_page(board,'organogram')
        self.assertEqual(after['pages'][0]['tables'],front['pages'][0]['tables'])
        self.assertEqual(after['schema_version'],6)
        removed=remove_model_page(board,'organogram')
        self.assertEqual(removed['pages'][0]['tables'],front['pages'][0]['tables'])

    def test_duplicate_object_and_cell_ids_rejected_atomically(self):
        document=example_document();original=deepcopy(document)
        with self.assertRaises(ModelValidationError):add_model_table(document,document['pages'][0]['tables'][0])
        self.assertEqual(document,original)
        table=deepcopy(document['pages'][0]['tables'][0]);table['object_id']='another-table'
        with self.assertRaises(ModelValidationError):add_model_table(document,table)

    def test_all_acceptance_specs_save_and_reopen_as_public_v6(self):
        for name,document in documents().items():
            with self.subTest(name=name):
                path=self.root/(name+'.fornax')
                save_public_fornax(document,path)
                self.assertEqual(open_public_fornax(path).document(),persistent_model_document(document))
                self.assertEqual(document['schema_version'],6)
                self.assertTrue(document['placeholders'])

    def test_rich_merge_full_qt_html_keeps_text_bold_italic_and_own_color(self):
        table=new_table(1,2)
        source=TextOnlyDocument();source.setHtml('<p><b>Primeiro</b></p>')
        table=set_cell_html(table,0,0,source.toHtml())
        table=set_cell_html(table,0,1,'<p><i>Segundo</i></p>')
        table=format_cells(table,0,1,0,1,{'font_color':'#bb2200'})
        merged=merge_cells(table,0,0,0,1)
        doc=TextOnlyDocument();doc.setHtml(cell_at(merged,0,0)['html'])
        self.assertEqual(doc.toPlainText().split(),['Primeiro','Segundo'])
        first=doc.find('Primeiro');second=doc.find('Segundo')
        self.assertGreater(first.charFormat().fontWeight(),400)
        self.assertTrue(second.charFormat().fontItalic())
        self.assertEqual(second.charFormat().foreground().color().name(),'#bb2200')

    def test_max_document_slots_survive_package_json_budget(self):
        first=new_table(100,10,width=2000,height=10000)
        document=add_model_table(base_document(),first)
        document=add_model_table(document,duplicate_table(first,name='Tabela 2'))
        path=self.root/'limit.fornax';save_public_fornax(document,path)
        self.assertEqual(len(open_public_fornax(path).document()['pages'][0]['tables']),2)
        before=deepcopy(document)
        with self.assertRaises(ModelValidationError):add_model_table(document,new_table(1,1))
        self.assertEqual(document,before)

    def test_old_reader_rejects_v6_in_isolated_process_without_writing_file(self):
        # Referência lida antes das alterações desta etapa; somente leitura.
        reference=Path(__file__).resolve().parents[1]/'docs/implementacao_tabelas/etapa-02/model_document-anterior.txt'
        if not reference.is_file():
            self.skipTest('Referência histórica é evidência local, não versionada.')
        path=self.root/'new.fornax';save_public_fornax(example_document(),path)
        digest=sha256(path.read_bytes()).hexdigest()
        command=[sys.executable,'-c',
            'import sys,types; from pathlib import Path; '
            'module=types.ModuleType("core.model_document"); sys.modules[module.__name__]=module; '
            'exec(compile(Path(sys.argv[1]).read_text(),sys.argv[1],"exec"),module.__dict__); '
            'from core.fornax_container import open_public_fornax\n'
            'try:\n open_public_fornax(sys.argv[2])\n'
            'except Exception as error:\n assert "Versão de modelo não suportada" in str(error), str(error); print(type(error).__name__)\n'
            'else:\n raise AssertionError("Leitor anterior aceitou v6")',str(reference),str(path)]
        result=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(sha256(path.read_bytes()).hexdigest(),digest)

    def test_editor_and_renderers_preserve_tables_and_reject_invalid_input_atomically(self):
        from features.editor.editor_window import EditorWindow
        from features.editor.table_item import TableItem
        from features.generator.renderer import NativeRenderer
        from features.generator.organogram import OrganogramRenderer
        document=example_document()
        self.assertFalse(NativeRenderer(adapt_model_page(document)).render_preview_image().isNull())
        self.assertIsInstance(OrganogramRenderer(add_organogram(document),[]),OrganogramRenderer)
        editor=EditorWindow()
        try:
            editor._load_document_into_scene(document)
            table=next(i for i in editor.scene.items() if isinstance(i,TableItem))
            self.assertEqual(table.to_data()['cells'],document['pages'][0]['tables'][0]['cells'])
            before=editor.get_current_scene_state()
            invalid=deepcopy(document)
            invalid['pages'][0]['tables'][0]['column_widths'][0]=-1
            with self.assertRaises(ModelValidationError):editor._load_document_into_scene(invalid)
            self.assertEqual(editor.get_current_scene_state(),before)
        finally:
            editor._last_saved_state=editor.get_current_scene_state()
            editor._last_saved_document_state=editor._capture_document_history_state()
            editor.close();editor.deleteLater();self.app.processEvents()

    def test_workspace_opens_table_editor_without_temporary_refusal(self):
        from features.workspace.main_window import MainWindow
        document=example_document()
        path=self.root/'test.fornax'
        fake=SimpleNamespace(
            preview_panel=SimpleNamespace(cbo_models=SimpleNamespace(currentText=lambda:'Teste')),
            _current_library_entry=lambda:SimpleNamespace(is_fornax=True,path=path,key='test'),
            _fornax_sessions=SimpleNamespace(document=lambda path:document,
                status=lambda path:SimpleNamespace(descriptor=SimpleNamespace(mode='none',model_id='test'),save_as_required=False)),
            _on_editor_saved=Mock(),_connect_editor_lifecycle=Mock())
        with patch('features.workspace.main_window.QMessageBox.warning') as warning, \
             patch('features.workspace.main_window.EditorWindow') as create:
            create.fornax_recovery_path.return_value=self.root/'absent-recovery.fornax'
            MainWindow._open_model_dialog(fake)
            warning.assert_not_called()
            create.return_value.load_from_fornax.assert_called_once()
            self.assertEqual(create.return_value.load_from_fornax.call_args.args[0],document)


if __name__=='__main__':
    unittest.main()
