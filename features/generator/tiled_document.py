"""Ladrilhamento de páginas comuns usando a mesma pintura nativa do quadro."""
from copy import deepcopy
from io import BytesIO
import math
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QRectF, QThread, Signal, Qt
from pypdf import PdfWriter

from core.i18n import tr
from core.model_document import adapt_model_page, normalize_model_document
from core.naming_engine import build_output_filename, confined_output_path
from core.tiling import build_tile_plan, UNITS_PER_MM
from .organogram import OrganogramRenderer
from .renderer import NativeRenderer


def proportional_options(options, bounds):
    result = deepcopy(options)
    target = result.get('target_size_mm')
    if target and len(target) == 2 and all(isinstance(value, (int, float)) and not isinstance(value, bool)
                                         and math.isfinite(value) and value > 0 for value in target):
        result['target_size_mm'] = (target[0], target[0] * bounds.height() / bounds.width())
    return result


def tiling_options(settings, bounds=None):
    if not settings or not settings.get('tiling'):
        return None
    options = dict(paper=tuple(settings.get('paper', (210, 297))),
                margin_mm=settings.get('margin_value', 5) if settings.get('margin_enabled') else 0,
                overlap_mm=settings.get('overlap_mm', 0), crop_marks=settings.get('crop_marks', False),
                target_size_mm=settings.get('target_size_mm'), offset_mm=settings.get('offset_mm', (0, 0)),
                auto_orientation=settings.get('auto_orientation', True))
    return proportional_options(options, bounds) if bounds is not None else options


class PageTilingRenderer(OrganogramRenderer):
    def __init__(self, document, page_id=None, row_plain=None, row_rich=None, *, asset_provider=None,
                 dynamic_image_dir=None):
        self.document = normalize_model_document(document)
        page = adapt_model_page(self.document, page_id or self.document['pages'][0]['page_id'])
        self.card = NativeRenderer(page, asset_provider=asset_provider)
        self.card.set_dynamic_image_directory(dynamic_image_dir)
        canvas = page['canvas_size']
        width = page.get('target_w_mm') or canvas['w'] / UNITS_PER_MM
        height = page.get('target_h_mm') or canvas['h'] / UNITS_PER_MM
        self.bounds = QRectF(0, 0, width * UNITS_PER_MM, height * UNITS_PER_MM)
        self.row_plain = row_plain if row_plain is not None else {key: '{' + key + '}' for key in page.get('placeholders', [])}
        self.row_rich = row_rich if row_rich is not None else self.row_plain
        self.slots = []

    def paint(self, painter, *, region=None, stop=None, out_links=None):
        if stop and stop():
            raise InterruptedError(tr('Geração cancelada.'))
        painter.save()
        try:
            painter.setClipRect(region if region is not None else self.bounds, Qt.ClipOperation.IntersectClip)
            canvas = self.card.tpl['canvas_size']
            painter.scale(self.bounds.width() / canvas['w'], self.bounds.height() / canvas['h'])
            self.card.paint_card(painter, self.row_plain, self.row_rich, out_links)
        finally:
            painter.restore()


class TiledDocumentWorker(QThread):
    progress_updated = Signal(int)
    log_updated = Signal(str)
    error_occurred = Signal(str)
    finished_process = Signal()

    def __init__(self, document, rows_plain, rows_rich, output_dir, mode, *, options,
                 pattern='{modelo}', asset_provider=None, dynamic_image_dir=None,
                 authorized_snapshot=None, parent=None, dpi=150):
        super().__init__(parent)
        self.document = deepcopy(document)
        self.rows = list(zip(deepcopy(rows_plain), deepcopy(rows_rich)))
        self.output_dir, self.mode = Path(output_dir), mode
        self.options, self.pattern = deepcopy(options), pattern
        self.asset_provider, self.dynamic_image_dir = asset_provider, dynamic_image_dir
        self.authorized_snapshot = authorized_snapshot
        self.dpi = dpi
        self._is_running = True

    def stop(self):
        self.requestInterruption()
        self.wait()

    def run(self):
        published = []
        try:
            jobs, used = [], set()
            pages = self.document['pages']
            # O lote compartilha uma pintura/cache por página. Não conserva
            # cópias decodificadas das mesmas imagens para cada registro.
            templates = []
            for page in pages:
                renderer = PageTilingRenderer(self.document, page['page_id'],
                    asset_provider=self.asset_provider, dynamic_image_dir=self.dynamic_image_dir)
                plan = build_tile_plan(renderer.bounds, **proportional_options(self.options, renderer.bounds))
                templates.append((renderer, plan))
            for plain, rich in self.rows:
                name = build_output_filename(self.pattern, plain, used)
                for index, (renderer, plan) in enumerate(templates):
                    base = f'{name}_pag{index + 1}' if len(pages) > 1 else name
                    jobs.append((base, renderer, plan, plain, rich))
            if not jobs:
                raise ValueError(tr('Não há registros válidos para gerar.'))
            total = sum(len(job[2].tiles) for job in jobs)
            staged, done = [], 0
            with TemporaryDirectory(prefix='.ladrilhos-', dir=self.output_dir) as directory:
                merged = PdfWriter() if self.mode == 'pdf_grouped' else None
                for base, renderer, plan, plain, rich in jobs:
                    renderer.row_plain, renderer.row_rich = plain, rich
                    if merged is not None:
                        if self.isInterruptionRequested():
                            raise InterruptedError(tr('Geração cancelada.'))
                        path = confined_output_path(directory, f'{base}.pdf')
                        renderer.export_pdf(path, plan=plan, stop=self.isInterruptionRequested)
                        start = len(merged.pages)
                        merged.append(str(path))
                        for index, tile in enumerate(plan.tiles):
                            merged.set_page_label(start + index, start + index, prefix=f'{base} — {tile.name}')
                        path.unlink()
                        done += len(plan.tiles)
                        self.progress_updated.emit(round(95 * done / total))
                    else:
                        for tile in plan.tiles:
                            if self.isInterruptionRequested():
                                raise InterruptedError(tr('Geração cancelada.'))
                            extension = 'png' if self.mode == 'png' else 'pdf'
                            path = confined_output_path(directory, f'{base}_{tile.name}.{extension}')
                            if self.mode == 'png':
                                renderer.export_tile_png(path, plan, tile, dpi=self.dpi, stop=self.isInterruptionRequested)
                            else:
                                renderer.export_pdf(path, plan=plan, tiles=(tile,), stop=self.isInterruptionRequested)
                            staged.append(path)
                            done += 1
                            self.progress_updated.emit(round(95 * done / total))
                if merged is not None:
                    path = confined_output_path(directory, 'ladrilhos.pdf')
                    output = BytesIO()
                    merged.write(output)
                    merged.close()
                    path.write_bytes(output.getvalue())
                    staged.append(path)
                for path in staged:
                    if self.isInterruptionRequested():
                        raise InterruptedError(tr('Geração cancelada.'))
                    target = confined_output_path(self.output_dir, path.name)
                    if target.exists():
                        raise FileExistsError(tr('Já existe um arquivo com o mesmo nome na pasta de saída.'))
                    path.replace(target)
                    published.append(target)
            self.progress_updated.emit(100)
            self.log_updated.emit(tr('Ladrilhos gerados: {folhas} folhas.').format(folhas=total))
        except Exception as error:
            for path in published:
                path.unlink(missing_ok=True)
            self.error_occurred.emit(str(error))
        finally:
            if self.authorized_snapshot is not None:
                self.authorized_snapshot.close()
            self._is_running = False
            self.finished_process.emit()
