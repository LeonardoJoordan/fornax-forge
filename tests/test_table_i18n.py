"""Catálogos TS/QM e controles reais de tabelas nos três idiomas."""
import ast
from collections import Counter
from pathlib import Path
from string import Formatter
import unittest
import xml.etree.ElementTree as ET
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QLabel
import test_table_canvas as canvas
from core.i18n import initialize_i18n,tr
from core.table_warnings import table_warning_messages
from core.resources import PROJECT_ROOT


class TableI18nTest(unittest.TestCase):
    setUpClass=classmethod(canvas.TableCanvasTest.setUpClass.__func__)
    tearDownClass=classmethod(canvas.TableCanvasTest.tearDownClass.__func__)
    setUp=canvas.TableCanvasTest.setUp
    tearDown=canvas.TableCanvasTest.tearDown
    editor=canvas.TableCanvasTest.editor

    def locale(self,locale):
        settings=QSettings(str(self.root/'locale.ini'),QSettings.Format.IniFormat)
        settings.setValue('language/locale',locale);initialize_i18n(self.app,settings)
        return settings

    def setUp(self):
        canvas.TableCanvasTest.setUp(self)
        self.addCleanup(self.locale,'pt_BR')

    def test_literals_and_validation_messages_have_finished_translations(self):
        sources=set()
        for name in ('features/editor/table_panel.py','features/editor/table_controller.py','features/editor/table_floating.py',
                     'features/editor/floating_bar.py', 'features/editor/object_floating.py',
                     'features/editor/text_floating.py', 'features/editor/table_selectors.py',
                     'features/editor/table_edit.py','core/table_warnings.py','core/table_model.py','core/table_clipboard.py'):
            for node in ast.walk(ast.parse((PROJECT_ROOT/name).read_text())):
                if (isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
                    and node.func.id in ('tr','_fail','TableValidationError') and node.args
                    and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str)):
                    sources.add(node.args[0].value)
        sources.update(['Elementos','Elementos (formas e tabela)','Formas e tabela','Adicionar tabela'])
        fields=lambda text:Counter(name for _,name,_,_ in Formatter().parse(text) if name is not None)
        for locale in ('en_US','es_ES'):
            messages={m.findtext('source'):m for context in ET.parse(PROJECT_ROOT/f'assets/translations/fornax_{locale}.ts').findall('context')
                      if context.findtext('name')=='' for m in context.findall('message')}
            for source in sources:
                with self.subTest(locale=locale,source=source):
                    self.assertTrue(source in messages,source)
                    translation=messages[source].find('translation')
                    self.assertNotEqual(translation.get('type'),'unfinished');self.assertTrue(translation.text)
                    self.assertEqual(fields(source),fields(translation.text))

    def test_compiled_catalog_updates_controls_without_changing_operation_keys(self):
        for locale,table,merge,rows,elements,collapse in [('pt_BR','Tabela','Mesclar células','Linhas','Elementos','Recolher barra de ferramentas'),
                                                ('en_US','Table','Merge cells','Rows','Elements','Collapse toolbar'),
                                                ('es_ES','Tabla','Combinar celdas','Filas','Elementos','Contraer barra de herramientas')]:
            with self.subTest(locale=locale):
                self.locale(locale);w,item=self.editor()
                self.assertEqual(w.action_add_table.text(),table)
                self.assertTrue(any(label.text()==tr('BORDAS') for label in w.table_panel.findChildren(QLabel)))
                self.assertEqual(w.table_controller.floating_bar.buttons['rows'].text(), rows)
                self.assertEqual(w.table_controller.floating_bar.buttons['merge'].accessibleName(), merge)
                self.assertEqual(w.table_controller.floating_bar.buttons['vertical_align'].toolTip(),
                                 tr('Alinhamento vertical'))
                item.setSelected(True)
                w.table_controller.selectors.reposition()
                self.assertEqual(w.table_controller.selectors.buttons['row', 0].accessibleName(),
                                 tr('Selecionar linha {number}').format(number=1))
                self.assertEqual(w.object_floating_bar.collapse_button.toolTip(), collapse)
                self.assertEqual(tr('Linhas'),rows)
                self.assertTrue(any(elements in label.text() for label in w.btn_elements.findChildren(QLabel)))
                self.assertEqual(w.table_panel.edge_opacity.accessibleName(),tr('Opacidade das bordas'))
                self.assertEqual(w.btn_elements.objectName(),'addFormas')
                before=w._capture_document_history_state()['document']
                w.table_controller.error(ValueError('A tabela precisa conservar ao menos uma linha e uma coluna.'))
                self.assertEqual(w.table_panel.message.text(),tr('A tabela precisa conservar ao menos uma linha e uma coluna.'))
                self.assertEqual(w._capture_document_history_state()['document'],before)

    def test_warning_formats_all_fields_from_compiled_catalog(self):
        warning={'row':2,'column':3,'table_name':'SINTÉTICO','page_id':'front','block':'Grupo','slot':4}
        for locale in ('pt_BR','en_US','es_ES'):
            self.locale(locale)
            text=table_warning_messages([warning])[0]
            self.assertIn('2,3',text);self.assertIn('SINTÉTICO',text);self.assertIn('4',text)
            self.assertNotIn('{',text)
            if locale=='en_US':self.assertIn('Text exceeds cell',text)
            elif locale=='es_ES':self.assertIn('El texto supera la celda',text)
        self.assertEqual(table_warning_messages([],source_row=0),[])


if __name__=='__main__':unittest.main()
