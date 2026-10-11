"""Cobertura dos idiomas da interface e dos textos dinâmicos distribuídos."""
import ast
from collections import Counter
import json
import os
from pathlib import Path
from string import Formatter
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QSettings, QTranslator
from PySide6.QtWidgets import QApplication

from core.i18n import initialize_i18n, tr
from core.resources import PROJECT_ROOT
from features.generator.image_output import export_choices
from features.help.help_dialog import HelpDialog
from features.editor.properties import CaixaDeTextoPanel, EditorDeTextoPanel


def interface_sources():
    sources = set()
    paths = [PROJECT_ROOT / 'main.py']
    for directory in ('core', 'features'):
        paths.extend((PROJECT_ROOT / directory).rglob('*.py'))
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in ('tr', '_fail', 'TableValidationError')
                    and node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                sources.add(node.args[0].value)
    # A galeria e a lista de papéis traduzem valores carregados dinamicamente.
    catalog = json.loads((PROJECT_ROOT / 'assets/templates/catalog.json').read_text())
    for template in catalog['templates']:
        sources.update((template['title'], template['description']))
    sources.update(('Carta', 'Personalizado', 'Definição do Modelo'))
    return sources


class InterfaceCatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_current_interface_and_starters_have_finished_compiled_translations(self):
        fields = lambda text: Counter(
            (name, spec, conversion) for _, name, spec, conversion in Formatter().parse(text)
            if name is not None)
        sources = interface_sources()
        for locale in ('en_US', 'es_ES'):
            path = PROJECT_ROOT / f'assets/translations/fornax_{locale}'
            contexts = ET.parse(path.with_suffix('.ts')).findall('context')
            entries = [message for context in contexts if not context.findtext('name')
                       for message in context.findall('message')]
            messages = {message.findtext('source'): message for message in entries}
            self.assertEqual(len(messages), len(entries), 'Entradas duplicadas no contexto global')
            translator = QTranslator()
            self.assertTrue(translator.load(str(path.with_suffix('.qm'))))
            for source in sources:
                with self.subTest(locale=locale, source=source):
                    self.assertIn(source, messages)
                    translation = messages[source].find('translation')
                    self.assertNotIn(translation.get('type'), ('unfinished', 'obsolete', 'vanished'))
                    value = translation.text
                    self.assertTrue(value)
                    self.assertEqual(fields(source), fields(value))
                    self.assertEqual(translator.translate('', source), value)

    def test_help_controls_and_export_labels_use_the_selected_language(self):
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        with TemporaryDirectory() as temporary:
            settings = QSettings(str(Path(temporary) / 'language.ini'), QSettings.Format.IniFormat)
            try:
                for locale, heading, grouped in (
                    ('en_US', 'Help Center', 'Combined PDF'),
                    ('es_ES', 'Centro de ayuda', 'PDF agrupado'),
                ):
                    settings.setValue('language/locale', locale)
                    initialize_i18n(app, settings)
                    dialog = HelpDialog()
                    text_panel = EditorDeTextoPanel()
                    properties = CaixaDeTextoPanel()
                    try:
                        self.assertEqual(dialog.windowTitle(), heading + ' — FORNAX Forge')
                        self.assertEqual(dialog.category_filter.itemText(0), tr('Todas as categorias'))
                        self.assertNotEqual(dialog.search.placeholderText(),
                                            'Buscar na ajuda… Ex.: máscara, guias, transparência')
                        self.assertEqual([entry[0] for entry in export_choices()],
                                         ['PNG', 'JPEG', 'PDF', grouped])
                        self.assertEqual([entry[1] for entry in export_choices()],
                                         ['png', 'jpeg', 'pdf_item', 'pdf_grouped'])
                        for control, source in (
                            (text_panel.cbo_font, 'Selecionar a família da fonte'),
                            (text_panel.spin_size, 'Alterar o tamanho da fonte'),
                            (text_panel.btn_color, 'Selecionar a cor do texto'),
                            (properties.chk_link, '<b>HABILITAR LINK (URL)</b><br><br>Cria uma área clicável no PDF exportado.'),
                        ):
                            self.assertEqual(control.toolTip(), tr(source))
                            self.assertNotEqual(control.toolTip(), source)
                        # Artigos continuam no fallback pt_BR; busca, links e
                        # rótulos traduzidos precisam funcionar nesse contexto.
                        dialog.search.setText('barra flutuante')
                        dialog.open_topic('UI-17')
                        self.assertIn('oito posições', dialog.content.toPlainText())
                        self.assertNotIn('Descrição ainda não disponível', dialog.content.toPlainText())
                    finally:
                        dialog.close()
                        dialog.deleteLater()
                        text_panel.deleteLater()
                        properties.deleteLater()
                        app.processEvents()
            finally:
                settings.setValue('language/locale', 'pt_BR')
                initialize_i18n(app, settings)


if __name__ == '__main__':
    unittest.main()
