from PySide6.QtCore import Signal, QObject
import os
import math
import re
import shutil
import tempfile
from pathlib import Path

# Imports corrigidos para a nova arquitetura
from core.naming_engine import build_output_filename, sanitize_filename, unique_filename
from .production_plan import build_imposition_plan
from .workers import (
    PageRenderWorker, DirectRenderWorker, HybridAssemblerWorker,
    SecureGroupedPdfWorker,
)
from core.i18n import tr
from core.paths import get_temp_dir

RENDER_MEMORY_BUDGET = 768 * 1024 * 1024


def _bounded_worker_count(requested, renderers, *, sheet=None, capacity=1, duplex=False):
    """Limita buffers simultâneos sem reduzir a velocidade de modelos comuns."""
    canvas = renderers[0].tpl.get("canvas_size", {})
    canvas_pixels = int(canvas.get("w", 0)) * int(canvas.get("h", 0))
    page_count = len(renderers)
    shared_bases = canvas_pixels * 4 * page_count
    if sheet is None:
        per_worker = canvas_pixels * 4
    else:
        sheet_pixels = sheet.sheet_w * sheet.sheet_h
        face_count = 2 if duplex else 1
        per_worker = 4 * (canvas_pixels * max(1, capacity) + sheet_pixels * face_count)
    available = max(per_worker, RENDER_MEMORY_BUDGET - shared_bases)
    return max(1, min(requested, available // max(1, per_worker)))

class RenderManager(QObject):
    progress_updated = Signal(int)
    log_updated = Signal(str)
    finished_process = Signal()
    error_occurred = Signal(str)

    def __init__(self, renderers, rows_plain, rows_rich, output_dir, filename_pattern, imposition_settings=None, export_format="PNG", single_pdf=False, target_w_mm=100.0, target_h_mm=150.0, source_rows=None, authorized_snapshot=None, protected_content=False):
        super().__init__()
        if not isinstance(renderers, (list, tuple)):
            renderers = [renderers]
        if not renderers:
            raise ValueError("Ao menos uma página deve ser fornecida para renderização.")
        self.page_renderers = list(renderers)
        self.renderer = self.page_renderers[0]
        self.rows_plain = rows_plain
        self.rows_rich = rows_rich
        self.source_rows = list(source_rows) if source_rows is not None else list(range(len(rows_plain)))
        self.output_dir = output_dir
        self.pattern = filename_pattern
        self.export_format = export_format.upper()
        self.single_pdf = single_pdf
        self.target_w_mm = target_w_mm
        self.target_h_mm = target_h_mm
        self.authorized_snapshot = authorized_snapshot
        self.protected_content = bool(protected_content)
        
        self.imposition_settings = imposition_settings or {"enabled": False}
        self.is_imposition = self.imposition_settings.get("enabled", False)
        
        self.workers = []
        self._hybrid_temporary = None
        self.total_cards = len(rows_plain)
        self.cards_done = 0
        self.generated_files = []
        self.all_cards_links = {} # Mapeia o índice do cartão para os seus links
        self._is_running = False

    def start(self):
        try:
            self._start()
        except Exception as error:
            if not self._is_running:
                self._is_running = True
            self._on_worker_error(str(error))

    def _start(self):
        self._is_running = True
        self._finish_emitted = False # Trava de segurança da Etapa Anterior
        self.cards_done = 0
        self.generated_files = []
        self.workers = []
        self.all_cards_links = {}

        if not self.total_cards or len(self.rows_rich) != self.total_cards:
            self._on_worker_error(tr("Não há registros válidos para gerar."))
            return
        
        self.log_updated.emit(tr("📋 Planejando produção…"))
        
        cpu_count = os.cpu_count() or 4
        num_threads = max(1, cpu_count - 2)
        num_threads = _bounded_worker_count(num_threads, self.page_renderers)
        
        # --- LÓGICA HÍBRIDA (Fim do castramento de threads) ---
        self.is_hybrid = (
            self.single_pdf and self.export_format == "PDF"
            and not self.protected_content
        )
        if self.is_hybrid:
            self._hybrid_temporary = tempfile.TemporaryDirectory(
                prefix="generation-", dir=get_temp_dir(),
            )
            self.work_dir = Path(self._hybrid_temporary.name)
        else:
            self.work_dir = self.output_dir
        self.worker_format = "PNG" if self.is_hybrid else self.export_format

        if self.is_hybrid:
            self.log_updated.emit(tr("⚡ Modo híbrido: gerando em cache ({threads} threads)…").format(threads=num_threads))

        all_tasks_data = []
        used_names = set()
        if self.work_dir.exists():
            for path in self.work_dir.iterdir():
                if not path.is_file():
                    continue
                stem = path.stem
                stem = re.sub(r"_(?:pag\d+|frente|verso)$", "", stem, flags=re.IGNORECASE)
                used_names.add(stem)
        
        copy_counts = {}
        for i in range(len(self.rows_plain)):
            row = self.rows_plain[i]
            fname = build_output_filename(self.pattern, row, used_names)
            source_row = self.source_rows[i] if i < len(self.source_rows) else i
            copy_counts[source_row] = copy_counts.get(source_row, 0) + 1
            copy_index = copy_counts[source_row]
            
            # Indexação oculta: Garante que mesmo processados fora de ordem,
            # os arquivos sejam montados na sequência exata da planilha.
            if self.is_hybrid and not self.is_imposition:
                fname = f"{i:05d}_{fname}"
                
            all_tasks_data.append(
                (i, source_row, copy_index, self.rows_plain[i], self.rows_rich[i], fname)
            )

        # Gera a base estática de forma síncrona na Thread Principal antes de acionar os Workers
        for page_renderer in self.page_renderers:
            page_renderer.pre_render_static_base()

        if self.protected_content and self.single_pdf and self.export_format == "PDF":
            self._start_secure_grouped_pdf(all_tasks_data)
        elif self.is_imposition:
            self._start_imposition_mode(all_tasks_data, num_threads)
        else:
            self._start_direct_mode(all_tasks_data, num_threads)

    def stop(self):
        self._is_running = False
        self.log_updated.emit(tr("🛑 Interrompendo processamento…"))
        for w in self.workers:
            w.stop()
            w.quit()
            w.wait()
        assembler = getattr(self, "assembler_worker", None)
        if assembler is not None and assembler.isRunning():
            assembler.stop()
            assembler.wait()
        if getattr(self, "is_hybrid", False):
            shutil.rmtree(self.work_dir, ignore_errors=True)
            temporary = self._hybrid_temporary
            self._hybrid_temporary = None
            if temporary is not None:
                temporary.cleanup()
        self._release_authorized_snapshot()

    def _release_authorized_snapshot(self):
        # Os sinais de último item podem chegar antes de QThread.finished.
        # Aguarde a saída de run() antes de descartar dados usados pelo worker.
        if self.protected_content:
            for worker in self.workers:
                worker.wait()
                worker.renderers = []
                worker.renderer = None
                if hasattr(worker, "chunk_data"):
                    worker.chunk_data = []
                if hasattr(worker, "tasks"):
                    worker.tasks = []
            self.page_renderers = []
            self.renderer = None
            self.rows_plain = []
            self.rows_rich = []
            self.all_cards_links.clear()
        snapshot = self.authorized_snapshot
        self.authorized_snapshot = None
        if snapshot is not None:
            snapshot.close()

    def _start_secure_grouped_pdf(self, all_tasks_data):
        self.log_updated.emit(tr("🔒 Gerando PDF protegido sem cache intermediário…"))
        worker = SecureGroupedPdfWorker(
            all_tasks_data, self.page_renderers, self.output_dir,
            self.imposition_settings, self.target_w_mm, self.target_h_mm,
        )
        worker.progress.connect(self._on_secure_grouped_progress)
        worker.finished_assembly.connect(self._on_secure_grouped_finished)
        worker.error_occurred.connect(self._on_worker_error)
        self.workers.append(worker)
        worker.start()

    def _on_secure_grouped_progress(self, count, message):
        if not self._is_running:
            return
        self.cards_done += count
        self.log_updated.emit(message)
        done = min(self.cards_done, self.total_cards)
        self.progress_updated.emit(int((done / self.total_cards) * 95))

    def _on_secure_grouped_finished(self, filename):
        if not self._is_running:
            return
        self.generated_files = [filename]
        self.cards_done = self.total_cards
        self._finish_emitted = True
        self._is_running = False
        self.progress_updated.emit(100)
        self._release_authorized_snapshot()
        self.finished_process.emit()
        self.log_updated.emit(tr("✅ Processo finalizado com sucesso!"))

    def _start_imposition_mode(self, all_data, num_threads):
        settings = dict(self.imposition_settings)
        settings["duplex"] = len(self.page_renderers) > 1
        self.imposition_settings = settings
        plan = build_imposition_plan(all_data, settings)
        capacity = plan.capacity
        
        if capacity <= 0:
            self._on_worker_error(tr("O modelo é grande demais para as margens da folha."))
            return
        num_threads = _bounded_worker_count(
            num_threads, self.page_renderers, sheet=plan.assembler,
            capacity=capacity, duplex=plan.duplex,
        )
            
        total_pages = len(plan.sheets)
        self.log_updated.emit(tr("📚 Imposição: {itens} itens em {folhas} folhas físicas (capacidade: {capacidade} por folha).").format(itens=len(all_data), folhas=total_pages, capacidade=capacity))
        if plan.duplex:
            self.log_updated.emit(tr("↔️ Frente e verso alinhados com rotação automática e virada lateral."))
            if self.export_format == "PDF" and not self.single_pdf:
                self.log_updated.emit(tr("📄 PDF por folha: cada arquivo terá frente e verso."))
        self.log_updated.emit(tr("🚀 Distribuindo o trabalho entre {threads} threads…").format(threads=num_threads))

        pages_jobs = []
        safe_pattern = sanitize_filename(self.pattern.replace("{", "").replace("}", ""))
        used_sheet_names = set()
        if self.work_dir.exists():
            used_sheet_names.update(
                re.sub(r"_(?:frente|verso)$", "", path.stem, flags=re.IGNORECASE)
                for path in self.work_dir.iterdir() if path.is_file()
            )

        for sheet in plan.sheets:
            page_num = sheet.number
            output_base = unique_filename(
                sanitize_filename(f"{safe_pattern}_Folha_{page_num:02d}"),
                used_sheet_names,
            )
            job = {
                "page_num": page_num,
                "output_base": output_base,
                "front": sheet.front,
                "back": sheet.back,
            }
            pages_jobs.append(job)

        chunk_size = math.ceil(total_pages / num_threads)
        
        for i in range(num_threads):
            start = i * chunk_size
            end = start + chunk_size
            worker_tasks = pages_jobs[start:end]
            
            if not worker_tasks: continue
            
            w = PageRenderWorker(
                worker_tasks, self.page_renderers, self.work_dir, settings,
                self.worker_format, False, secure_output=self.protected_content,
            )
            w.page_finished.connect(self._on_page_finished)
            w.error_occurred.connect(self._on_worker_error)
            
            self.workers.append(w)
            w.start()

    def _start_direct_mode(self, all_data, num_threads):
        self.log_updated.emit(tr("🚀 Processando {itens} itens em {threads} threads…").format(itens=len(all_data), threads=num_threads))
        
        chunk_size = math.ceil(len(all_data) / num_threads)
        
        for i in range(num_threads):
            start = i * chunk_size
            end = start + chunk_size
            chunk = all_data[start:end]
            
            if not chunk: continue
            
            w = DirectRenderWorker(
                chunk, self.page_renderers, self.work_dir, self.worker_format,
                False, self.target_w_mm, self.target_h_mm,
                secure_output=self.protected_content,
            )
            w.card_finished.connect(self._on_direct_card_finished)
            w.error_occurred.connect(self._on_worker_error)
            
            self.workers.append(w)
            w.start()

    def _start_hybrid_assembly(self):
        self.log_updated.emit(tr("📦 Montando o PDF agrupado em segundo plano…"))
        canvas_w = self.renderer.tpl.get("canvas_size", {}).get("w", 1000)
        canvas_h = self.renderer.tpl.get("canvas_size", {}).get("h", 1000)
        if self.is_imposition:
            from .imposition import SheetAssembler
            assembler = SheetAssembler(
                self.imposition_settings.get("target_w_mm", 100),
                self.imposition_settings.get("target_h_mm", 150),
                self.imposition_settings.get("sheet_w_mm", 210),
                self.imposition_settings.get("sheet_h_mm", 297),
                self.imposition_settings.get("crop_marks", True),
                self.imposition_settings.get("bleed_margin", False),
                auto_rotate=True,
            )
            canvas_w, canvas_h = assembler.sheet_w, assembler.sheet_h
        self.assembler_worker = HybridAssemblerWorker(
            self.generated_files, self.work_dir, self.output_dir, 
            self.is_imposition, self.imposition_settings, 
            self.target_w_mm, self.target_h_mm,
            all_links=self.all_cards_links,
            canvas_w=canvas_w,
            canvas_h=canvas_h
        )
        self.assembler_worker.finished_assembly.connect(self._on_hybrid_assembly_finished)
        self.assembler_worker.error_occurred.connect(self._on_hybrid_assembly_error)
        self.assembler_worker.start()    

    def _on_page_finished(self, num_cards, filenames, sheet_index, links_by_face, msg):
        if not self._is_running: return
        self.cards_done += num_cards
        self.log_updated.emit(msg)
        face_count = len(self.page_renderers)
        for face_index, links in links_by_face.items():
            if links:
                self.all_cards_links[sheet_index * face_count + int(face_index)] = links
        self.generated_files.extend(filenames)
        self._update_progress()

    def _on_direct_card_finished(self, filenames, original_idx, links_by_page):
        if not self._is_running: return

        page_count = len(self.page_renderers)
        for page_index, local_links in links_by_page.items():
            if local_links:
                self.all_cards_links[original_idx * page_count + int(page_index)] = local_links
            
        self.cards_done += 1
        self.log_updated.emit(tr("[{concluidos}/{total}] Salvo: {arquivo}").format(
            concluidos=self.cards_done, total=self.total_cards,
            arquivo=", ".join(filenames),
        ))
        self.generated_files.extend(filenames)
        self._update_progress()

    def _on_hybrid_assembly_finished(self):
        out_name = f"{self.output_dir.name}_Imposicao.pdf" if self.is_imposition else f"{self.output_dir.name}_Completo.pdf"
        self.generated_files = [out_name]
        self.progress_updated.emit(100)
        self._is_running = False
        self._release_authorized_snapshot()
        self.finished_process.emit()
        self.log_updated.emit(tr("✅ Processo finalizado com sucesso!"))

    def _on_hybrid_assembly_error(self, error_msg):
        self._on_worker_error(tr("Erro na montagem do PDF: {erro}").format(erro=error_msg))

    def _on_worker_error(self, error_msg):
        if not self._is_running:
            return
        self._finish_emitted = True
        self.stop()
        self.error_occurred.emit(error_msg)
        self.finished_process.emit()

    def _check_completion(self):
        # A nova trava absoluta: Só finaliza se a matemática bater 100%
        if self.cards_done >= self.total_cards:
            if self._is_running and not getattr(self, '_finish_emitted', False):
                self._finish_emitted = True
                if getattr(self, 'is_hybrid', False):
                    self._start_hybrid_assembly()
                else:
                    self.progress_updated.emit(100)
                    self._is_running = False
                    self._release_authorized_snapshot()
                    self.finished_process.emit()
                    self.log_updated.emit(tr("✅ Processo finalizado com sucesso!"))
    
    def _update_progress(self):
        done = min(self.cards_done, self.total_cards)
        percent = int((done / self.total_cards) * 100)
        if getattr(self, "is_hybrid", False):
            percent = min(percent, 95)
        self.progress_updated.emit(percent)
        
        # Como o _update_progress é chamado SEMPRE no final do log_updated.emit,
        # isso garante que o log foi impresso antes de validarmos o fim do processo.
        self._check_completion()
