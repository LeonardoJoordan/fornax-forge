"""Rótulos e marcadores acompanham os cartões, cópias, faces e folhas reais."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtGui import QImage, QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from pypdf import PdfReader

from features.generator.manager import RenderManager
from features.generator.renderer import NativeRenderer
from features.generator.workers import HybridAssemblerWorker
from features.generator.pdf_links import inject_pdf_links


class GroupedPdfNamingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch('core.paths._data_home', return_value=self.root / 'data'))

    def generate(self, *, protected=False, imposed=False, duplex=False, count=3, capacity=4):
        output = self.root / 'FORNAX - Forja nº 42'
        output.mkdir()
        renderers = [NativeRenderer({'canvas_size': {'w': 120, 'h': 160}, 'boxes': [
            {'x': 4, 'y': 8, 'w': 110, 'h': 80, 'font_size': 10, 'html': '<p>{nome}</p>',
             'has_link': True, 'link_key': 'url'},
        ]}) for _ in range(2 if duplex else 1)]
        # The workspace displays a preview before exporting. Initialize Qt's
        # text bindings on the GUI thread here too, before parallel workers.
        for renderer in renderers:
            renderer.render_to_qimage({'nome': 'Prévia'}, {'nome': 'Prévia'})
        rows = [{'nome': 'Ana' if i < 2 else f'Pessoa {i + 1}', 'url': 'https://example.org/'}
                for i in range(count)]
        settings = dict(enabled=imposed, target_w_mm=10, target_h_mm=14,
                        sheet_w_mm=20 if capacity == 4 else 40, sheet_h_mm=28,
                        auto_rotate=False, crop_marks=False, bleed_margin=False)
        manager = RenderManager(renderers, rows, rows, output, '{nome}', settings,
            export_format='PDF', single_pdf=True, protected_content=protected,
            target_w_mm=10, target_h_mm=14)
        errors, finished = [], []
        manager.error_occurred.connect(errors.append)
        manager.finished_process.connect(lambda: finished.append(True))
        manager.start()
        for _ in range(1000):
            if finished:
                break
            QTest.qWait(10)
        for worker in manager.workers:
            worker.wait()
        if getattr(manager, 'assembler_worker', None):
            manager.assembler_worker.wait()
        if manager._hybrid_temporary:
            manager._hybrid_temporary.cleanup()
        self.assertTrue(finished, 'A geração não terminou')
        self.assertEqual(errors, [])
        self.assertEqual(manager.generated_files, ['FORNAX - Forja nº 42.pdf'])
        self.assertEqual([path.name for path in output.iterdir()], manager.generated_files)
        reader = PdfReader(output / manager.generated_files[0])
        self.assertTrue(all(page.get('/Annots') for page in reader.pages))
        return reader

    def assert_navigation(self, reader, labels):
        self.assertEqual(reader.page_labels, labels)
        self.assertEqual([entry.title for entry in reader.outline], labels)
        self.assertEqual([reader.get_destination_page_number(entry) for entry in reader.outline],
                         list(range(len(labels))))
        self.assertTrue(all(page.get('/Annots') for page in reader.pages))

    def test_public_cards_use_individual_names_without_internal_sort_prefixes(self):
        self.assert_navigation(self.generate(), ['Ana', 'Ana_01', 'Pessoa 3'])

    def test_protected_cards_use_same_names_without_intermediate_cache(self):
        self.assert_navigation(self.generate(protected=True), ['Ana', 'Ana_01', 'Pessoa 3'])

    def test_public_sheets_number_only_existing_cards_on_last_page(self):
        self.assert_navigation(self.generate(imposed=True, count=6), ['Cartão de 1 a 4', 'Cartão de 5 a 6'])

    def test_protected_sheets_support_eight_cards_per_page(self):
        self.assert_navigation(self.generate(protected=True, imposed=True, count=17, capacity=8),
                               ['Cartão de 1 a 8', 'Cartão de 9 a 16', 'Cartão de 17 a 17'])

    def test_public_duplex_cards_keep_faces_together(self):
        labels = [f'{name} — {face}' for name in ('Ana', 'Ana_01', 'Pessoa 3') for face in ('Frente', 'Verso')]
        self.assert_navigation(self.generate(duplex=True), labels)

    def test_protected_duplex_sheets_do_not_count_verso_as_new_cards(self):
        labels = [f'{name} — {face}' for name in ('Cartão de 1 a 4', 'Cartão de 5 a 6')
                  for face in ('Frente', 'Verso')]
        self.assert_navigation(self.generate(protected=True, imposed=True, duplex=True, count=6), labels)

    def test_public_duplex_sheets_share_the_same_ranges_and_face_order(self):
        labels = [f'{name} — {face}' for name in ('Cartão de 1 a 4', 'Cartão de 5 a 6')
                  for face in ('Frente', 'Verso')]
        self.assert_navigation(self.generate(imposed=True, duplex=True, count=6), labels)

    def test_metadata_does_not_change_image_streams_links_or_page_sizes(self):
        reader = self.generate()
        path = self.root / 'FORNAX - Forja nº 42' / 'FORNAX - Forja nº 42.pdf'
        def image_streams(pdf):
            return [[(obj.get_object().get('/Filter'), obj.get_object().get_data())
                     for obj in page['/Resources']['/XObject'].values()] for page in pdf.pages]
        streams = image_streams(reader)
        boxes = [tuple(page.mediabox) for page in reader.pages]
        def links(pdf):
            return [[(tuple(a.get_object()['/Rect']), str(a.get_object()['/A']))
                     for a in page['/Annots']] for page in pdf.pages]
        annotations = links(reader)
        inject_pdf_links(path, {}, 120, 160, page_labels=['Novo A', 'Novo B', 'Novo C'])
        updated = PdfReader(path)
        self.assertEqual(streams, image_streams(updated))
        self.assertEqual(boxes, [tuple(page.mediabox) for page in updated.pages])
        self.assertEqual(annotations, links(updated))

    def test_hybrid_assembly_uses_production_order_instead_of_lexical_filename_order(self):
        work, output = self.root / 'work', self.root / 'FORNAX - Forja nº 7'
        work.mkdir(); output.mkdir()
        names = ['Folha_99.png', 'Folha_100.png', 'Folha_101.png']
        for name in names:
            image = QImage(10, 10, QImage.Format.Format_RGB32)
            image.fill(QColor('white'))
            image.save(str(work / name), 'PNG')
        labels = dict(zip(names, ['Cartão de 393 a 396', 'Cartão de 397 a 400', 'Cartão de 401 a 404']))
        worker = HybridAssemblerWorker(list(reversed(names)), work, output, False, {}, 10, 10, page_labels=labels)
        errors = []
        worker.error_occurred.connect(errors.append)
        worker.run()
        self.assertEqual(errors, [])
        reader = PdfReader(output / 'FORNAX - Forja nº 7.pdf')
        self.assertEqual(reader.page_labels, list(labels.values()))
        self.assertEqual([entry.title for entry in reader.outline], list(labels.values()))


if __name__ == '__main__':
    unittest.main()
