"""Geração sequencial das folhas de prévia fora da thread da interface."""

from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QPageLayout

from features.generator.production_plan import build_imposition_plan
from features.generator.renderer import NativeRenderer, renderers_for_document


class SheetPreviewWorker(QThread):
    # O terceiro argumento pode ser um caminho público ou uma QImage mantida
    # somente em memória quando o modelo contém conteúdo protegido.
    pageReady = Signal(int, int, object, int)
    pageFailed = Signal(int, int, str, int)

    def __init__(self, template, rows, settings, output_dir, generation,
                 first_page=0, first_face=0, cache_limit=12, parent=None,
                 asset_provider=None, memory_only=False, authorized_snapshot=None):
        super().__init__(parent)
        self.template = template
        self.rows = rows
        self.settings = settings
        self.output_dir = Path(output_dir) if output_dir else None
        self.generation = generation
        self.first_page = first_page
        self.first_face = first_face
        self.cache_limit = max(1, cache_limit)
        self.asset_provider = asset_provider
        self.memory_only = bool(memory_only)
        self.authorized_snapshot = authorized_snapshot
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        try:
            plan = build_imposition_plan(self.rows, self.settings)
            if not plan.sheets:
                return
            if "pages" in self.template:
                renderers = renderers_for_document(
                    self.template, asset_provider=self.asset_provider,
                )
            else:
                renderers = [NativeRenderer(
                    self.template, asset_provider=self.asset_provider,
                )]
            for renderer in renderers:
                renderer.pre_render_static_base()
            first = min(max(0, self.first_page), len(plan.sheets) - 1)
            first_face = min(max(0, self.first_face), len(renderers) - 1)
            tasks = [(first, first_face)]
            tasks.extend(
                (sheet_index, face_index)
                for sheet_index in range(len(plan.sheets))
                for face_index in range(len(renderers))
                if (sheet_index, face_index) != (first, first_face)
            )
            tasks = tasks[:self.cache_limit]

            if not self.memory_only:
                self.output_dir.mkdir(parents=True, exist_ok=True)
            for page_index, face_index in tasks:
                if not self._running or self.isInterruptionRequested():
                    return
                sheet = plan.sheets[page_index]
                slots = sheet.front if face_index == 0 else sheet.back
                if slots is None:
                    continue
                renderer = renderers[face_index]
                cards = []
                for entry in slots:
                    if entry is None:
                        cards.append(None)
                    else:
                        row_plain, row_rich = entry
                        cards.append(renderer.render_to_qimage(row_plain, row_rich))
                if not self._running or self.isInterruptionRequested():
                    return
                image = plan.assembler.render_sheet(
                    cards,
                    preserve_slots=plan.duplex,
                    rotate_cards_180=(
                        plan.duplex
                        and face_index == 1
                        and plan.assembler.orientation == QPageLayout.Orientation.Landscape
                    ),
                )
                if max(image.width(), image.height()) > 1800:
                    image = image.scaled(
                        1800, 1800,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                if self.memory_only:
                    self.pageReady.emit(page_index, face_index, image, self.generation)
                else:
                    path = self.output_dir / f"sheet_{page_index:05d}_face_{face_index}.png"
                    if not image.save(str(path), "PNG"):
                        raise OSError(f"Não foi possível gravar {path.name}")
                    self.pageReady.emit(page_index, face_index, str(path), self.generation)
        except Exception as exc:
            self.pageFailed.emit(self.first_page, self.first_face, str(exc), self.generation)
        finally:
            if self.authorized_snapshot is not None:
                self.authorized_snapshot.close()
                self.authorized_snapshot = None
            self.asset_provider = None
            self.template = None
            self.rows = []
