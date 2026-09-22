import traceback
import shutil
from PySide6.QtCore import QThread, Signal, QSizeF, QMarginsF
from PySide6.QtGui import QImage, QPainter, QPdfWriter, QPageLayout, QPageSize

from .imposition import SheetAssembler
from .production_plan import build_imposition_plan
from .pdf_links import inject_pdf_links
from core.i18n import tr
from core.model_document import resolve_model_file
from core.naming_engine import confined_output_path
from core.render_cache import publish_thumbnail_cache, source_revision


def physical_page(width_mm, height_mm):
    # Evita que medidas personalizadas próximas de A4 sejam arredondadas para A4.
    return QPageSize(QSizeF(width_mm, height_mm), QPageSize.Unit.Millimeter,
                     "", QPageSize.SizeMatchPolicy.ExactMatch)


def pdf_painter(writer):
    painter = QPainter(writer)
    if not painter.isActive():
        raise OSError(tr("Não foi possível abrir o PDF para gravação."))
    return painter


class DirectRenderWorker(QThread):
    card_finished = Signal(object, int, object)
    error_occurred = Signal(str)

    def __init__(self, chunk_data, renderers, output_dir, export_format="PNG", single_pdf=False, target_w_mm=100.0, target_h_mm=150.0, secure_output=False):
        super().__init__()
        self.chunk_data = chunk_data
        if not isinstance(renderers, (list, tuple)):
            renderers = [renderers]
        self.renderers = [renderer.fork() for renderer in renderers]
        self.renderer = self.renderers[0]
        self.output_dir = output_dir
        self.export_format = export_format
        self.single_pdf = single_pdf
        self.target_w_mm = target_w_mm
        self.target_h_mm = target_h_mm
        self.secure_output = bool(secure_output)
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        try:
            for original_idx, source_row, copy_index, row_plain, row_rich, filename in self.chunk_data:
                if not self._is_running: break
                links_by_page = {}
                temporary_paths = []
                published_paths = []
                active_secure_paths = []
                if self.export_format == "PDF":
                    out_path = confined_output_path(self.output_dir, f"{filename}.pdf")
                    temporary = (
                        out_path if self.secure_output else
                        confined_output_path(self.output_dir, f".{filename}.{original_idx}.partial.pdf")
                    )
                    if not self.secure_output:
                        temporary_paths.append(temporary)
                    else:
                        active_secure_paths.append(out_path)
                    writer = QPdfWriter(str(temporary))
                    writer.setPageSize(QPageSize(QPageSize.PageSizeId.Custom))
                    layout = writer.pageLayout()
                    layout.setPageSize(physical_page(self.target_w_mm, self.target_h_mm))
                    layout.setMargins(QMarginsF(0, 0, 0, 0))
                    writer.setPageLayout(layout)
                    painter = pdf_painter(writer)
                    for page_index, renderer in enumerate(self.renderers):
                        if not self._is_running:
                            break
                        if page_index:
                            writer.newPage()
                        local_links = []
                        image = renderer.render_to_qimage(row_plain, row_rich, out_links=local_links)
                        painter.drawImage(layout.paintRectPixels(writer.resolution()), image)
                        links_by_page[page_index] = local_links
                    painter.end()
                    del painter
                    del layout
                    del writer
                    if not self._is_running:
                        temporary.unlink(missing_ok=True)
                        break
                    if any(links_by_page.values()):
                        canvas = self.renderers[0].tpl.get("canvas_size", {})
                        inject_pdf_links(
                            temporary, links_by_page,
                            canvas.get("w", 1000), canvas.get("h", 1000),
                            memory_only=self.secure_output,
                        )
                    if not self.secure_output:
                        temporary.replace(out_path)
                    published_paths.append(out_path)
                    temporary_paths.clear()
                    output_names = [out_path.name]
                else:
                    output_names = []
                    staged = []
                    multiple_pages = len(self.renderers) > 1
                    for page_index, renderer in enumerate(self.renderers):
                        if not self._is_running:
                            break
                        suffix = f"_pag{page_index + 1}" if multiple_pages else ""
                        out_path = confined_output_path(self.output_dir, f"{filename}{suffix}.png")
                        temporary = (
                            out_path if self.secure_output else
                            confined_output_path(self.output_dir, f".{filename}{suffix}.{original_idx}.partial.png")
                        )
                        if not self.secure_output:
                            temporary_paths.append(temporary)
                        else:
                            active_secure_paths.append(out_path)
                        local_links = []
                        renderer.render_row(
                            row_plain, row_rich, temporary, out_links=local_links,
                            target_w_mm=self.target_w_mm, target_h_mm=self.target_h_mm,
                        )
                        links_by_page[page_index] = local_links
                        staged.append((temporary, out_path))
                    if not self._is_running:
                        for temporary in temporary_paths:
                            temporary.unlink(missing_ok=True)
                        break
                    for temporary, out_path in staged:
                        if not self.secure_output:
                            temporary.replace(out_path)
                        published_paths.append(out_path)
                        output_names.append(out_path.name)
                    temporary_paths.clear()

                self.card_finished.emit(output_names, original_idx, links_by_page)
                active_secure_paths = []

        except Exception as e:
            active_painter = locals().get("painter")
            if active_painter is not None and active_painter.isActive():
                active_painter.end()
            painter = None
            layout = None
            writer = None
            for path in locals().get("temporary_paths", []):
                path.unlink(missing_ok=True)
            for path in locals().get("published_paths", []):
                path.unlink(missing_ok=True)
            for path in locals().get("active_secure_paths", []):
                path.unlink(missing_ok=True)
            self.error_occurred.emit(str(e))

class PageRenderWorker(QThread):
    page_finished = Signal(int, object, int, object, str)
    error_occurred = Signal(str)

    def __init__(self, tasks, renderers, output_dir, imposition_settings, export_format="PNG", single_pdf=False, secure_output=False):
        super().__init__()
        self.tasks = tasks
        if not isinstance(renderers, (list, tuple)):
            renderers = [renderers]
        self.renderers = [renderer.fork() for renderer in renderers]
        self.renderer = self.renderers[0]
        self.output_dir = output_dir
        self.export_format = export_format
        self.single_pdf = single_pdf
        self.duplex = bool(imposition_settings.get("duplex", False))
        self.secure_output = bool(secure_output)
        
        w_mm = imposition_settings.get("target_w_mm", 100)
        h_mm = imposition_settings.get("target_h_mm", 150)
        sheet_w = imposition_settings.get("sheet_w_mm", 210.0)
        sheet_h = imposition_settings.get("sheet_h_mm", 297.0)
        crop_marks = imposition_settings.get("crop_marks", True)
        bleed_margin = imposition_settings.get("bleed_margin", False)
        
        self.assembler = SheetAssembler(
            w_mm, h_mm, sheet_w, sheet_h, crop_marks, bleed_margin,
            auto_rotate=True,
        )
        
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        temporary_paths = []
        active_secure_paths = []
        try:
            for page_task in self.tasks:
                if not self._is_running: break
                active_secure_paths = []

                page_num = page_task["page_num"]
                face_tasks = [(0, page_task["front"])]
                if page_task.get("back") is not None:
                    face_tasks.append((1, page_task["back"]))

                face_images = []
                links_by_face = {}
                for face_index, slots in face_tasks:
                    renderer = self.renderers[face_index]
                    card_images = []
                    card_links = []
                    for task in slots:
                        if task is None:
                            card_images.append(None)
                            card_links.append([])
                            continue
                        _, _, _, row_plain, row_rich, _ = task
                        links = []
                        card_images.append(renderer.render_to_qimage(row_plain, row_rich, out_links=links))
                        card_links.append(links)
                    sheet_links = []
                    canvas = renderer.tpl.get("canvas_size", {})
                    face_images.append(self.assembler.render_sheet(
                        card_images,
                        preserve_slots=self.duplex,
                        card_links=card_links,
                        canvas_size=(canvas.get("w", 1000), canvas.get("h", 1000)),
                        out_links=sheet_links,
                        rotate_cards_180=(
                            self.duplex
                            and face_index == 1
                            and self.assembler.orientation == QPageLayout.Orientation.Landscape
                        ),
                    ))
                    links_by_face[face_index] = sheet_links

                output_base = page_task["output_base"]
                final_names = []
                if self.export_format == "PDF":
                    out_path = confined_output_path(self.output_dir, f"{output_base}.pdf")
                    temporary = (
                        out_path if self.secure_output else
                        confined_output_path(self.output_dir, f".{output_base}.{page_num}.partial.pdf")
                    )
                    if not self.secure_output:
                        temporary_paths.append(temporary)
                    else:
                        active_secure_paths.append(out_path)
                    writer = QPdfWriter(str(temporary))
                    layout = writer.pageLayout()
                    layout.setPageSize(physical_page(self.assembler.sheet_w_mm, self.assembler.sheet_h_mm))
                    layout.setMargins(QMarginsF(0, 0, 0, 0))
                    writer.setPageLayout(layout)
                    painter = pdf_painter(writer)
                    for face_index, image in enumerate(face_images):
                        if face_index:
                            writer.newPage()
                        painter.drawImage(layout.paintRectPixels(writer.resolution()), image)
                    painter.end()
                    del painter, layout, writer
                    if not self._is_running:
                        temporary.unlink(missing_ok=True)
                        break
                    if any(links_by_face.values()):
                        inject_pdf_links(
                            temporary, links_by_face,
                            self.assembler.sheet_w, self.assembler.sheet_h,
                            memory_only=self.secure_output,
                        )
                    if not self.secure_output:
                        temporary.replace(out_path)
                    temporary_paths.clear()
                    final_names.append(out_path.name)
                else:
                    staged = []
                    suffixes = ("_frente", "_verso") if self.duplex else ("",)
                    for face_index, image in enumerate(face_images):
                        suffix = suffixes[face_index]
                        out_path = confined_output_path(self.output_dir, f"{output_base}{suffix}.png")
                        temporary = (
                            out_path if self.secure_output else
                            confined_output_path(self.output_dir, f".{output_base}{suffix}.{page_num}.partial.png")
                        )
                        if not self.secure_output:
                            temporary_paths.append(temporary)
                        else:
                            active_secure_paths.append(out_path)
                        if not image.save(str(temporary), "PNG"):
                            raise OSError(tr("Não foi possível gravar {arquivo}.").format(arquivo=out_path))
                        staged.append((temporary, out_path))
                    if not self._is_running:
                        for temporary in temporary_paths:
                            temporary.unlink(missing_ok=True)
                        break
                    for temporary, out_path in staged:
                        if not self.secure_output:
                            temporary.replace(out_path)
                        final_names.append(out_path.name)
                    temporary_paths.clear()
                active_secure_paths = []

                num_cards = sum(task is not None for task in page_task["front"])
                msg = tr("🖨️ FOLHA {folha:02d} OK ({itens} itens)").format(folha=page_num, itens=num_cards)
                self.page_finished.emit(num_cards, final_names, page_num - 1, links_by_face, msg)

        except Exception as e:
            active_painter = locals().get("painter")
            if active_painter is not None and active_painter.isActive():
                active_painter.end()
            painter = None
            layout = None
            writer = None
            for path in temporary_paths:
                path.unlink(missing_ok=True)
            for path in active_secure_paths:
                path.unlink(missing_ok=True)
            self.error_occurred.emit(tr("Erro no processamento: {erro}\n{detalhes}").format(erro=e, detalhes=traceback.format_exc()))


class SecureGroupedPdfWorker(QThread):
    """Monta o PDF final protegido sem materializar cartões ou folhas em cache."""

    progress = Signal(int, str)
    finished_assembly = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, tasks, renderers, output_dir, imposition_settings,
                 target_w_mm, target_h_mm):
        super().__init__()
        self.tasks = list(tasks)
        self.renderers = [renderer.fork() for renderer in renderers]
        self.output_dir = output_dir
        self.settings = dict(imposition_settings or {})
        self.target_w_mm = target_w_mm
        self.target_h_mm = target_h_mm
        self.is_imposition = bool(self.settings.get("enabled", False))
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        output_path = self.output_dir / (
            f"{self.output_dir.name}_Imposicao.pdf" if self.is_imposition
            else f"{self.output_dir.name}_Completo.pdf"
        )
        painter = writer = layout = None
        try:
            writer = QPdfWriter(str(output_path))
            layout = writer.pageLayout()
            layout.setMargins(QMarginsF(0, 0, 0, 0))
            links_by_page = {}
            page_number = 0
            first_page = True

            if self.is_imposition:
                settings = dict(self.settings)
                settings["duplex"] = len(self.renderers) > 1
                plan = build_imposition_plan(self.tasks, settings)
                layout.setPageSize(physical_page(
                    plan.assembler.sheet_w_mm, plan.assembler.sheet_h_mm,
                ))
                writer.setPageLayout(layout)
                painter = pdf_painter(writer)
                for sheet in plan.sheets:
                    faces = [(0, sheet.front)]
                    if sheet.back is not None:
                        faces.append((1, sheet.back))
                    for face_index, slots in faces:
                        if not self._is_running:
                            raise InterruptedError
                        if not first_page:
                            writer.newPage()
                        first_page = False
                        renderer = self.renderers[face_index]
                        card_images, card_links = [], []
                        for task in slots:
                            if task is None:
                                card_images.append(None)
                                card_links.append([])
                                continue
                            _, _, _, row_plain, row_rich, _ = task
                            local_links = []
                            card_images.append(renderer.render_to_qimage(
                                row_plain, row_rich, out_links=local_links,
                            ))
                            card_links.append(local_links)
                        sheet_links = []
                        canvas = renderer.tpl.get("canvas_size", {})
                        image = plan.assembler.render_sheet(
                            card_images, preserve_slots=plan.duplex,
                            card_links=card_links,
                            canvas_size=(canvas.get("w", 1000), canvas.get("h", 1000)),
                            out_links=sheet_links,
                            rotate_cards_180=(
                                plan.duplex and face_index == 1
                                and plan.assembler.orientation == QPageLayout.Orientation.Landscape
                            ),
                        )
                        painter.drawImage(layout.paintRectPixels(writer.resolution()), image)
                        links_by_page[page_number] = sheet_links
                        page_number += 1
                    completed = sum(task is not None for task in sheet.front)
                    self.progress.emit(completed, tr("🖨️ FOLHA {folha:02d} OK ({itens} itens)").format(
                        folha=sheet.number, itens=completed,
                    ))
                link_canvas = (plan.assembler.sheet_w, plan.assembler.sheet_h)
            else:
                layout.setPageSize(physical_page(self.target_w_mm, self.target_h_mm))
                writer.setPageLayout(layout)
                painter = pdf_painter(writer)
                for original_idx, _source_row, _copy_index, row_plain, row_rich, filename in self.tasks:
                    if not self._is_running:
                        raise InterruptedError
                    for renderer in self.renderers:
                        if not first_page:
                            writer.newPage()
                        first_page = False
                        local_links = []
                        image = renderer.render_to_qimage(
                            row_plain, row_rich, out_links=local_links,
                        )
                        painter.drawImage(layout.paintRectPixels(writer.resolution()), image)
                        links_by_page[page_number] = local_links
                        page_number += 1
                    self.progress.emit(1, tr("Salvo no PDF agrupado: {arquivo}").format(arquivo=filename))
                canvas = self.renderers[0].tpl.get("canvas_size", {})
                link_canvas = (canvas.get("w", 1000), canvas.get("h", 1000))

            painter.end()
            painter = None
            writer = layout = None
            if links_by_page:
                inject_pdf_links(
                    output_path, links_by_page, *link_canvas, memory_only=True,
                )
            self.finished_assembly.emit(output_path.name)
        except InterruptedError:
            if painter is not None and painter.isActive():
                painter.end()
            painter = writer = layout = None
            output_path.unlink(missing_ok=True)
        except Exception as exc:
            if painter is not None and painter.isActive():
                painter.end()
            painter = writer = layout = None
            output_path.unlink(missing_ok=True)
            self.error_occurred.emit(str(exc))
            
            
class HybridAssemblerWorker(QThread):
    finished_assembly = Signal()
    error_occurred = Signal(str)

    def __init__(self, generated_files, work_dir, output_dir, is_imposition, imposition_settings, target_w_mm, target_h_mm, all_links=None, canvas_w=1000, canvas_h=1000):
        super().__init__()
        self.generated_files = generated_files
        self.work_dir = work_dir
        self.output_dir = output_dir
        self.is_imposition = is_imposition
        self.imposition_settings = imposition_settings
        self.target_w_mm = target_w_mm
        self.target_h_mm = target_h_mm
        self.all_links = all_links or {}
        self.canvas_w = canvas_w
        self.canvas_h = canvas_h
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        temporary_pdf = None
        try:
            out_path_single = self.output_dir / f"{self.output_dir.name}_Completo.pdf"
            if self.is_imposition:
                out_path_single = self.output_dir / f"{self.output_dir.name}_Imposicao.pdf"
            temporary_pdf = self.output_dir / f".{out_path_single.name}.partial.pdf"

            writer = QPdfWriter(str(temporary_pdf))
            writer.setPageSize(QPageSize(QPageSize.PageSizeId.Custom))
            
            layout = writer.pageLayout()
            layout.setMargins(QMarginsF(0, 0, 0, 0))

            if self.is_imposition:
                sheet_w = self.imposition_settings.get("sheet_w_mm", 210.0)
                sheet_h = self.imposition_settings.get("sheet_h_mm", 297.0)
                tw = self.imposition_settings.get("target_w_mm", 100.0)
                th = self.imposition_settings.get("target_h_mm", 150.0)
                marks = self.imposition_settings.get("crop_marks", True)
                bleed = self.imposition_settings.get("bleed_margin", False)

                # Recalcula a orientação vencedora para o PDF final
                temp_asm = SheetAssembler(
                    tw, th, sheet_w, sheet_h, marks, bleed,
                    auto_rotate=True,
                )
                layout.setPageSize(physical_page(temp_asm.sheet_w_mm, temp_asm.sheet_h_mm))
            else:
                layout.setPageSize(physical_page(self.target_w_mm, self.target_h_mm))
                
            writer.setPageLayout(layout)
            painter = pdf_painter(writer)

            # Os arquivos já virão ordenados perfeitamente pelo índice
            sorted_files = sorted(self.generated_files)

            cancelled = False
            for i, filename in enumerate(sorted_files):
                if not self._is_running:
                    cancelled = True
                    break
                if i > 0:
                    writer.newPage()
                img_path = self.work_dir / filename
                img = QImage(str(img_path))
                if img.isNull():
                    painter.end()
                    raise OSError(f"Imagem ausente ou inválida na montagem: {img_path.name}")
                painter.drawImage(layout.paintRectPixels(writer.resolution()), img)
                del img 
            
            painter.end()
            
            # Força a liberação do arquivo final antes de injetar os links
            del painter
            del layout
            del writer

            if cancelled or not self._is_running:
                temporary_pdf.unlink(missing_ok=True)
                return

            # --- PÓS-PROCESSAMENTO: Injeção de Hiperlinks no PDF Único ---
            if self.all_links:
                try:
                    inject_pdf_links(
                        temporary_pdf,
                        self.all_links,
                        self.canvas_w,
                        self.canvas_h,
                    )
                except Exception as e:
                    raise OSError(f"Erro ao injetar links no PDF Híbrido: {e}") from e

            temporary_pdf.replace(out_path_single)
            shutil.rmtree(self.work_dir, ignore_errors=True)
            self.finished_assembly.emit()
            
        except Exception as e:
            active_painter = locals().get("painter")
            if active_painter is not None and active_painter.isActive():
                active_painter.end()
            painter = None
            layout = None
            writer = None
            if temporary_pdf is not None:
                temporary_pdf.unlink(missing_ok=True)
            self.error_occurred.emit(str(e))

class PreviewRenderWorker(QThread):
    preview_ready = Signal(str, str) # model_name, thumb_path
    error_occurred = Signal(str)

    def __init__(self, model_name, template_data, model_dir):
        super().__init__()
        self.model_name = model_name
        self.template_data = template_data
        self.model_dir = model_dir
        try:
            source = resolve_model_file(model_dir)
        except FileNotFoundError:
            source = model_dir / "template_v4.json"
        self._source_path = source
        self._source_revision = source_revision(source)
        self.page_id = template_data.get("__page_id", "front")

    def run(self):
        try:
            from features.generator.renderer import NativeRenderer
            from PySide6.QtCore import Qt
            
            renderer = NativeRenderer(self.template_data)
            
            # Prepara os placeholders para a thumbnail crua
            placeholders = self.template_data.get("placeholders", [])
            row_rich = {p: f"{{{p}}}" for p in placeholders}
            
            img = renderer.render_preview_image(row_rich, max_side=1600)
            try:
                source = resolve_model_file(self.model_dir)
            except FileNotFoundError:
                return
            if (
                source != self._source_path
                or self._source_revision is not None
                and source_revision(source) != self._source_revision
            ):
                return
            thumb_path = publish_thumbnail_cache(
                self.model_dir, source, img, self.page_id, self._source_revision,
            )
            if thumb_path is None:
                raise OSError("Não foi possível gravar a miniatura.")

            # Avisa a Janela Principal que terminou
            self.preview_ready.emit(self.model_name, str(thumb_path))
            
        except Exception as e:
            self.error_occurred.emit(tr("Erro na prévia em segundo plano: {erro}").format(erro=e))
