"""Comparação antes/depois, isolada da biblioteca e preferências do usuário.

QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tests .venv/bin/python \
    tests/performance/workspace_pipeline_evidence.py /tmp/workspace-before.json
Não execute em paralelo com outros testes/benchmarks.
"""
import inspect
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QSettings
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QLabel, QTableWidgetItem
from core.fornax_container import open_public_fornax, save_public_fornax
from core.fornax_session import FornaxSessionManager
from core.model_document import adapt_model_page
from core.ui_font import install_ui_font
from features.generator.renderer import NativeRenderer
from features.generator.workers import DirectRenderWorker, HybridAssemblerWorker
from test_organogram import card_document, board_document
from test_signature_preview import PreviewWorkspace


def main(destination):
    app = QApplication.instance() or QApplication([])
    install_ui_font(app)
    results = {"environment": platform.platform(), "measurements": {}}

    def measure(name, action, samples=5):
        action()
        values = []
        for _ in range(samples):
            start = time.perf_counter()
            action()
            values.append((time.perf_counter() - start) * 1000)
        result = {"median_ms": round(statistics.median(values), 3), "samples_ms": values}
        results["measurements"][name] = result
        Path(destination).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(name, result["median_ms"], flush=True)
        return result

    with TemporaryDirectory(prefix="fornax-pipeline-") as temp, patch(
        "core.paths._data_home", return_value=Path(temp) / "data"
    ):
        root = Path(temp)
        windows, sessions = [], []

        def workspace(doc, count=1000):
            doc["imposition_settings"] = {"enabled": False,
                "active_preset_name": PreviewWorkspace.SYSTEM_IMPOSITION_PRESET}
            path = root / f"model-{len(windows)}.fornax"
            save_public_fornax(doc, path)
            session = FornaxSessionManager()
            session.select(path)
            sessions.append(session)
            w = PreviewWorkspace(path, session, QSettings(str(root / "prefs.ini"), QSettings.Format.IniFormat))
            windows.append(w)
            w._preview_sheet_index = 0
            w._sheet_preview_workers, w._stale_sheet_preview_dirs = set(), set()
            w.table_panel.lbl_board_status = QLabel(w)
            table = w.table_panel.table
            table.blockSignals(True)
            table.setRowCount(count)
            groups = (doc.get("organogram") or {}).get("groups", [])
            for row in range(count):
                for col in range(table.columnCount()):
                    value = "1" if col == 0 else groups[0]["name"] if groups and col == 1 else f"Pessoa {row}-{col}"
                    table.setItem(row, col, QTableWidgetItem(value))
            table.blockSignals(False)
            table.setCurrentCell(0, table.columnCount() - 1)
            w._preview_refresh_timer.stop()
            return w

        doc = card_document()
        doc["pages"][0]["field_ids"] = ["Nome", "Funcao", "Campo0", "Campo1", "Campo2", "Campo3"]
        doc["placeholders"] = doc["pages"][0]["field_ids"][:]
        w = workspace(doc)
        table = w.table_panel.table
        assert table.columnCount() == 7
        measure("scrape_1000x7", w._scrape_table_data)
        measure("next_item_1000x7", lambda: w._on_preview_index_requested((w._preview_item_index + 1) % 1000))
        measure("same_row_selection", lambda: table.setCurrentCell(table.currentRow(), 1 if table.currentColumn() != 1 else 2))
        with patch.object(w, "_scrape_table_data", wraps=w._scrape_table_data) as scrape, patch.object(
            w.preview_renderer, "render_to_pixmap", wraps=w.preview_renderer.render_to_pixmap
        ) as render:
            w._on_preview_index_requested(50)
            results["next_counts"] = {"scrapes": scrape.call_count, "renders": render.call_count}

        clipboard = "\n".join("\t".join(f"Pessoa {r}-{c}" for c in range(6)) for r in range(1000))
        app.clipboard().setText(clipboard)
        revisions = []
        def paste():
            sample = workspace(doc, 1)
            sample.table_panel.table.setCurrentCell(0, 1)
            revision = sample._sheet_preview_revision
            start = time.perf_counter()
            sample.table_panel.table._paste_from_clipboard()
            elapsed = (time.perf_counter() - start) * 1000
            revisions.append(sample._sheet_preview_revision - revision)
            assert sample.table_panel.table.item(999, 6).text() == "Pessoa 999-5"
            sample._preview_refresh_timer.stop()
            return elapsed
        paste()
        times = [paste() for _ in range(5)]
        results["measurements"]["paste_1000x6"] = {"median_ms": statistics.median(times), "samples_ms": times, "invalidations": revisions}
        print("paste_1000x6", results["measurements"]["paste_1000x6"], flush=True)

        for count in (300, 1000):
            board = workspace(board_document(10, count // 10), count)
            board._on_preview_mode_changed("sheet")
            bt = board.table_panel.table
            measure(f"board_{count}_selection", lambda: bt.setCurrentCell(0, 2 if bt.currentColumn() != 2 else 3), samples=3)

        photos = workspace(card_document())
        image = QImage(4, 4, QImage.Format.Format_ARGB32)
        image.fill(0xffffffff)
        image.save(str(root / "person.png"))
        photos.cached_model_document["pages"][0]["shapes"][0]["dynamic_image_field"] = "Nome"
        photos.table_panel.txt_dynamic_image_dir.setText(str(root))
        pt = photos.table_panel.table
        pt.blockSignals(True)
        for row in range(1000):
            pt.item(row, 1).setText("person")
        pt.blockSignals(False)
        photos._refresh_dynamic_image_status()
        # Isola a validação de imagens acionada por uma edição textual.
        with patch.object(photos, "_on_table_selection"), patch.object(photos, "_start_sheet_preview_preload"):
            def edit():
                pt.item(0, 2).setText(pt.item(0, 2).text() + "a")
                photos._refresh_preview_after_data_change()
                photos._preview_refresh_timer.stop()
            measure("photo_status_after_unrelated_edit_1000", edit)

        opened = open_public_fornax(Path("assets/templates/models/internship-certificate.fornax"))
        renderer = NativeRenderer(adapt_model_page(opened.document()), asset_provider=opened.asset)
        renderer.pre_render_static_base()
        options = {"intermediate_png": True} if "intermediate_png" in inspect.signature(DirectRenderWorker).parameters else {}
        errors = []
        def grouped_pdf():
            work_dir = root / "intermediate"
            work_dir.mkdir(exist_ok=True)
            tasks = [(n, n, 0, {"nome": f"Pessoa {n}"}, {"nome": f"Pessoa {n}"}, f"cert-{n}") for n in range(3)]
            worker = DirectRenderWorker(tasks, [renderer], work_dir, target_w_mm=297, target_h_mm=210, **options)
            worker.error_occurred.connect(errors.append)
            worker.run()
            paths = [work_dir / f"cert-{n}.png" for n in range(3)]
            assert all(p.exists() for p in paths), errors
            assembler = HybridAssemblerWorker([p.name for p in paths], work_dir, root, False, {}, 297, 210)
            assembler.error_occurred.connect(errors.append)
            assembler.run()
            assert not errors, errors
            assert (root / f"{root.name}_Completo.pdf").exists()
        measure("grouped_pdf_3_certificates_serial", grouped_pdf, samples=3)
        for window in windows:
            window._preview_refresh_timer.stop()
            window.table_panel.table._row_height_timer.stop()
            window.deleteLater()
        for session in sessions:
            session.close()
    Path(destination).write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
