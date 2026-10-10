"""PNG intermediário deve preservar pixels, DPI e o PDF raster final."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from pypdf import PdfReader
from features.generator.png_output import save_png
from features.generator.renderer import NativeRenderer
from features.generator.workers import DirectRenderWorker, PageRenderWorker, HybridAssemblerWorker
from features.generator.manager import RenderManager


class IntermediatePngTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.renderer = NativeRenderer({"canvas_size": {"w": 200, "h": 140}, "boxes": [
            {"x": 8, "y": 8, "w": 180, "h": 80, "html": '<p><b>{nome}</b></p>', "font_size": 14},
        ]})

    def run_worker(self, worker):
        errors = []
        worker.error_occurred.connect(errors.append)
        worker.run()
        self.assertEqual(errors, [])

    def test_lossless_alpha_dpi_and_text_metadata(self):
        image = QImage(120, 80, QImage.Format.Format_ARGB32)
        for x in range(image.width()):
            for y in range(image.height()):
                image.setPixel(x, y, ((x * 2) << 24) | (x << 16) | (y << 8) | 123)
        image.setDotsPerMeterX(11811)
        image.setDotsPerMeterY(11812)
        image.setText("Description", "Teste sem perdas")
        decoded = []
        for flag in (False, True):
            path = self.root / f"{flag}.png"
            self.assertTrue(save_png(image, path, intermediate=flag))
            result = QImage(str(path))
            self.assertEqual(result.convertToFormat(image.format()), image)
            self.assertEqual((result.dotsPerMeterX(), result.dotsPerMeterY()), (11811, 11812))
            self.assertEqual(result.text("Description"), image.text("Description"))
            decoded.append(result)
        self.assertEqual(decoded[0], decoded[1])

    def test_direct_and_imposed_workers_produce_identical_pngs_and_grouped_pdf_images(self):
        task = (0, 0, 1, {"nome": "Nome de exemplo"}, {"nome": "Nome de exemplo"}, "card")
        settings = {"target_w_mm": 20, "target_h_mm": 14, "sheet_w_mm": 50,
                    "sheet_h_mm": 40, "crop_marks": True, "bleed_margin": False}
        for imposed in (False, True):
            images, pdfs = [], []
            for flag in (False, True):
                output = self.root / f"output-{imposed}-{flag}"
                work = self.root / f"work-{imposed}-{flag}"
                output.mkdir(); work.mkdir()
                if imposed:
                    worker = PageRenderWorker([{"page_num": 1, "front": [task], "back": None,
                        "output_base": "sheet"}], [self.renderer], work, settings, intermediate_png=flag)
                else:
                    worker = DirectRenderWorker([task], [self.renderer], work, target_w_mm=20,
                                                target_h_mm=14, intermediate_png=flag)
                self.run_worker(worker)
                paths = sorted(work.glob("*.png"))
                self.assertEqual(len(paths), 1)
                images.append(QImage(str(paths[0])))
                self.run_worker(HybridAssemblerWorker([p.name for p in paths], work, output,
                                                      imposed, settings, 20, 14))
                self.assertFalse(work.exists())
                pdfs.append(PdfReader(next(output.glob("*.pdf"))))
            self.assertEqual(images[0], images[1])
            self.assertEqual(images[0].dotsPerMeterX(), images[1].dotsPerMeterX())
            self.assertEqual(len(pdfs[0].pages), 1)
            self.assertEqual(pdfs[0].pages[0].mediabox, pdfs[1].pages[0].mediabox)
            def image_streams(pdf):
                objects = pdf.pages[0]["/Resources"]["/XObject"]
                images = [ref.get_object() for ref in objects.values()
                          if ref.get_object().get("/Subtype") == "/Image"]
                self.assertTrue(images)
                # Compara também o stream codificado: não depende de Pillow.
                return [(i["/Width"], i["/Height"], i.get("/Filter"), i.get_data()) for i in images]
            self.assertEqual(image_streams(pdfs[0]), image_streams(pdfs[1]))

    def test_only_public_grouped_pdf_enables_intermediate_compression(self):
        for imposed in (False, True):
            for fmt, single, protected in (("PNG", False, False), ("PDF", False, False),
                                           ("PDF", True, False), ("PNG", False, True), ("PDF", True, True)):
                with self.subTest(imposed=imposed, fmt=fmt, single=single, protected=protected):
                    manager = RenderManager([self.renderer], [{"nome": "Ana"}], [{"nome": "Ana"}],
                        self.root, "{nome}", {"enabled": imposed, "sheet_w_mm": 30, "sheet_h_mm": 30,
                        "target_w_mm": 20, "target_h_mm": 14}, fmt, single,
                        target_w_mm=20, target_h_mm=14, protected_content=protected)
                    with patch("features.generator.manager.get_temp_dir", return_value=self.root), patch(
                        "features.generator.manager.DirectRenderWorker.start"
                    ), patch("features.generator.manager.PageRenderWorker.start"), patch(
                        "features.generator.manager.SecureGroupedPdfWorker.start"
                    ):
                        manager._start()
                    for worker in manager.workers:
                        if isinstance(worker, (DirectRenderWorker, PageRenderWorker)):
                            self.assertEqual(worker.intermediate_png, fmt == "PDF" and single and not protected)
                    manager.stop()

    def test_intermediate_write_failure_and_cancellation_leave_no_partial_output(self):
        task = (0, 0, 1, {"nome": "Ana"}, {"nome": "Ana"}, "card")
        worker = DirectRenderWorker([task], [self.renderer], self.root, intermediate_png=True)
        errors = []
        worker.error_occurred.connect(errors.append)
        def failed_save(image, path, **kwargs):
            Path(path).write_bytes(b"incomplete")
            return False
        with patch("features.generator.renderer.save_png", side_effect=failed_save):
            worker.run()
        self.assertEqual(len(errors), 1)
        self.assertEqual(list(self.root.iterdir()), [])
        cancelled = DirectRenderWorker([task], [self.renderer], self.root, intermediate_png=True)
        cancelled.stop()
        self.run_worker(cancelled)
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
