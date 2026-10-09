#!/usr/bin/env python3
"""Benchmark isolado do editor. Tempos sem profiler; contagens em rodada separada.

Uso: .venv/bin/python tests/performance/benchmark_editor.py --output <pasta>
Cada cenário roda num processo próprio, com dados e preferências temporários.
Não compara plataformas distintas nem estabelece limites de tempo para aprovação.
"""
import argparse
from contextlib import ExitStack
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.pending')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def distribution(samples):
    values = sorted(samples)
    position = (len(values) - 1) * .95
    lo, fraction = int(position), position - int(position)
    p95 = values[lo] + fraction * (values[min(lo+1, len(values)-1)] - values[lo])
    return {'median_ms': statistics.median(values), 'p95_ms': p95,
            'min_ms': values[0], 'max_ms': values[-1],
            'stdev_ms': statistics.pstdev(values), 'sample_count': len(values)}


def product_hashes():
    files = list((ROOT / 'core').glob('*.py')) + list((ROOT / 'features/editor').glob('*.py'))
    files += list((ROOT / 'features/generator').glob('*.py'))
    files += [p for subdir in ('assets/fonts/ui', 'assets/templates')
              for p in (ROOT/subdir).rglob('*') if p.is_file()]
    return {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def environment():
    import PySide6
    from PySide6.QtCore import qVersion
    def git(*args):
        result = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None
    return {'protocol': 1, 'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'platform': platform.platform(), 'python': sys.version,
            'machine': platform.machine(), 'logical_cpus': os.cpu_count(),
            'cpu_model': next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                               if line.startswith('model name')), None) if Path('/proc/cpuinfo').exists() else platform.processor(),
            'memory_total_kib': next((int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()
                                     if line.startswith('MemTotal:')), None) if Path('/proc/meminfo').exists() else None,
            'pyside6': PySide6.__version__, 'qt': qVersion(),
            'qt_platform': 'offscreen', 'theme': 'dark', 'locale': 'pt_BR',
            'window_requested': [1280, 800], 'workers_concurrent': 1,
            'warmups': 2, 'warm_samples': 20, 'cold_samples': 5,
            'git_branch': git('branch', '--show-current'), 'git_commit': git('rev-parse', 'HEAD'),
            'worktree_status': git('status', '--short'), 'product_sha256': product_hashes(),
            'harness_sha256': {p.name: sha256(p.read_bytes()).hexdigest()
                               for p in Path(__file__).parent.glob('*.py')}}


def rss_bytes():
    # Memória residente atual, não pico de memória nem tamanho de allocations Python.
    try:
        pages = int(Path('/proc/self/statm').read_text().split()[1])
        return pages * os.sysconf('SC_PAGE_SIZE')
    except (OSError, ValueError, IndexError, AttributeError):
        return None


def worker(case, sample_count=None, progress_path=None):
    import cProfile
    from PySide6.QtCore import QObject, QEvent, QEventLoop, QTimer, Qt, QPointF, QRectF
    from PySide6.QtGui import QTextCursor, QImage
    from PySide6.QtWidgets import QApplication, QGraphicsItem
    from shiboken6 import isValid
    from core.ui_font import install_ui_font
    from core.themes import theme_manager
    from core.model_document import persistent_model_document
    from core.fornax_container import save_public_fornax, save_protected_fornax
    from core.fornax_session import FornaxSessionManager
    from core.organogram import UNITS_PER_MM
    from features.editor.editor_window import EditorWindow
    from features.editor.canvas_items import DesignerBox, ImageItem, SignatureItem
    from features.editor.organogram_editor import BoardConnectorItem, BoardGroupItem
    from features.editor.starter_dialog import StarterDialog
    from editor_scenarios import make_document, fingerprint

    class PaintObserver(QObject):
        def __init__(self, watched):
            super().__init__(watched)
            self.count = 0
            self.loop = None
            watched.installEventFilter(self)

        def eventFilter(self, source, event):
            if event.type() == QEvent.Type.Paint:
                self.count += 1
                if self.loop is not None:
                    QTimer.singleShot(0, self.loop.quit)
            return False

        def complete(self, previous, required):
            if required and self.count == previous:
                loop = QEventLoop()
                timer = QTimer()
                timer.setSingleShot(True)
                timer.timeout.connect(loop.quit)
                self.loop = loop
                timer.start(5000)
                loop.exec()
                self.loop = None
                timer.stop()
                if self.count == previous:
                    raise TimeoutError('A pintura esperada não foi concluída em 5 segundos.')
            # Processa notificações/pinturas enfileiradas até três turnos estáveis.
            unchanged, last = 0, self.count
            deadline = time.perf_counter() + 5
            while unchanged < 3:
                QApplication.sendPostedEvents()
                app.processEvents()
                unchanged = unchanged + 1 if self.count == last else 0
                last = self.count
                if time.perf_counter() > deadline:
                    raise TimeoutError('A interface não estabilizou em 5 segundos.')

    class Run:
        def __init__(self, root):
            self.root = root
            self.window = None
            self.sessions = None
            self.dialog = None
            self.document, self.provider = make_document(case)
            self.input_sha256 = fingerprint(self.document, self.provider)
            self.original_items = []
            self.iteration = 0

        def build(self):
            self.window = EditorWindow()
            w = self.window
            w.resize(1280, 800)
            if case.operation.startswith('autosave'):
                self.sessions = FornaxSessionManager()
                path = self.root / 'synthetic.fornax'
                if case.mode == 'public':
                    save_public_fornax(self.document, path, asset_provider=self.provider)
                    status = self.sessions.select(path)
                else:
                    save_protected_fornax(self.document, path, 'synthetic-benchmark-password',
                                          mode=case.mode, asset_provider=self.provider)
                    status = self.sessions.unlock(path, 'synthetic-benchmark-password')
                w.load_from_fornax(self.sessions.document(), path=path, mode=status.descriptor.mode,
                                  model_id=status.descriptor.model_id, asset_provider=self.sessions.asset,
                                  session_manager=self.sessions)
            else:
                w.load_starter_document(self.document, self.provider)
            w._autosave_timer.stop()
            if case.fixture in ('connected', 'grid', 'institutional'):
                w.switch_model_page('organogram')
            w.show()
            self.observer = PaintObserver(w.view.viewport())
            previous = self.observer.count
            w._zoom_to_fit()
            self.observer.complete(previous, True)
            self.restore()

        def restore(self):
            w = self.window
            if w.canvas_edit.box:
                w.canvas_edit.finish()
            if case.operation == 'page_cycles':
                w.switch_model_page('front')
            # A reconstrução de referência fica fora do intervalo medido.
            unchanged_ops = {'select_all', 'layers', 'snapshot_unchanged', 'gallery', 'page_cycles'}
            if (not case.operation.startswith('autosave') and case.operation not in unchanged_ops
                    and not case.operation.startswith('paint_')):
                w._load_document_into_scene(deepcopy_document(self.document))
            if case.fixture in ('connected', 'grid', 'institutional'):
                w.switch_model_page('organogram')
                w._zoom_to_fit()
            w.scene.clearSelection()
            self.original_items = [i for i in w.scene.items()
                                   if isinstance(i, (DesignerBox, ImageItem, SignatureItem, BoardGroupItem, BoardConnectorItem))]
            boxes = [i for i in w.scene.items() if isinstance(i, DesignerBox)
                     and i.isVisible() and i.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable]
            self.box = boxes[0] if boxes else None
            if case.operation in ('paste', 'text_insert', 'text_resize'):
                self.box.setSelected(True)
                if case.operation == 'paste':
                    w.copy_selected_items()
                elif case.operation == 'text_insert':
                    w.canvas_edit.begin(self.box)
            if case.operation in ('drag_one', 'drag_four', 'block_outline', 'paint_small'):
                self.groups = w._board_items()
                if case.operation == 'block_outline':
                    self.groups[0].setSelected(True)
            if case.operation == 'connector_opacity':
                self.edge = next(i for i in w.scene.items() if isinstance(i, BoardConnectorItem))
                self.edge.setSelected(True)
            if case.operation in ('paint_near', 'paint_far'):
                self.groups = w._board_items()
                w._zoom_to_fit()
                if case.operation == 'paint_near':
                    w.view.resetTransform()
                    w.view.scale(.7, .7)
                    w.view.centerOn(self.groups[0].sceneBoundingRect().topLeft() + QPointF(180, 180))
            if case.operation.startswith('autosave'):
                box = next(i for i in w.scene.items() if isinstance(i, DesignerBox))
                box.state.html_content = '<p>Recuperação sintética <b>{Nome}</b></p>'
                box.apply_state()
                if case.operation != 'autosave_repeat':
                    w.fornax_recovery_path(w._fornax_path).unlink(missing_ok=True)
            self.observer.complete(self.observer.count, False)
            self.state_before = persistent_model_document(w._document_with_active_page())

        def operation(self):
            w = self.window
            op = case.operation
            if op == 'select_all':
                w.select_all_items()
            elif op == 'paste':
                w.paste_copied_items()
            elif op == 'layers':
                w.refresh_layer_list()
            elif op == 'snapshot_unchanged':
                w.save_snapshot()
            elif op in ('drag_one', 'drag_four'):
                for item in self.groups[:1 if op == 'drag_one' else 4]:
                    item.moveBy(5 * (self.iteration + 1) * UNITS_PER_MM, 0)
            elif op == 'connector_opacity':
                w.change_board_connector_style(opacity=.63)
            elif op == 'block_outline':
                w.change_board_border(cards=True, width_mm=1.6)
            elif op.startswith('paint_'):
                bounds = self.groups[0].sceneBoundingRect()
                rect = QRectF(bounds.center().x(), bounds.center().y(), 10, 10)
                w.scene.update(rect if op == 'paint_small' else w.view.mapToScene(w.view.viewport().rect()).boundingRect())
            elif op == 'text_insert':
                cursor = self.box.text_item.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.insertText(' exemplo')
                self.box.text_item.setTextCursor(cursor)
            elif op == 'text_resize':
                self.box.resize_from_handle(650, 2000)
            elif op == 'switch_back':
                w.switch_model_page('back')
            elif op == 'switch_board':
                w.switch_model_page('front')
                w.switch_model_page('organogram')
            elif op == 'page_cycles':
                for _ in range(20):
                    w.switch_model_page('back')
                    w.switch_model_page('front')
            elif op.startswith('autosave'):
                for _ in range(3 if op == 'autosave_repeat' else 1):
                    w._write_fornax_recovery()
                if not w.fornax_recovery_path(w._fornax_path).is_file():
                    raise AssertionError('A recuperação não foi publicada.')
            elif op == 'gallery':
                self.dialog = StarterDialog(case.fixture, w, document=w._document_with_active_page())
                self.dialog.show()
                self.gallery_observer = PaintObserver(self.dialog.gallery.viewport())
                self.gallery_observer.complete(0, True)
            elif op == 'load':
                w.load_starter_document(self.document, self.provider)
            else:
                raise ValueError(op)

        def verify(self):
            w = self.window
            state = persistent_model_document(w._document_with_active_page())
            if case.operation in ('layers', 'select_all', 'snapshot_unchanged') or case.operation.startswith('paint_'):
                if state != self.state_before:
                    raise AssertionError('Uma operação de interface alterou o documento.')
            if case.operation == 'paste':
                if len(state['pages'][0]['boxes']) != len(self.state_before['pages'][0]['boxes']) + 1:
                    raise AssertionError('A colagem não acrescentou exatamente um texto.')
            if case.operation == 'text_insert' and not self.box.text_item.toPlainText().endswith(' exemplo'):
                raise AssertionError('Conteúdo digitado incompleto.')
            if case.operation == 'switch_back' and w._active_page_id != 'back':
                raise AssertionError('Página incorreta depois da troca.')
            if case.operation == 'switch_board' and w._active_page_id != 'organogram':
                raise AssertionError('Organograma não restaurado.')
            if case.operation.startswith('autosave'):
                saved = self.sessions.read_recovery(w.fornax_recovery_path(w._fornax_path), path=w._fornax_path).document()
                if saved['pages'][0]['boxes'][0]['html'] != '<p>Recuperação sintética <b>{Nome}</b></p>':
                    raise AssertionError('Texto não recuperado.')
            return {'rss_bytes': rss_bytes(), 'scene_items': len(w.scene.items()),
                    'selected_items': len(w.scene.selectedItems()),
                    'original_items_retained': sum(isValid(i) and i.scene() is w.scene for i in self.original_items),
                    'operation_index': self.iteration,
                    'history_index': w.history._current_index,
                    'visual_cache_bytes': w._visual_cache.proxies.retained_bytes + w._visual_cache.previews.retained_bytes}

        def clean(self):
            if self.dialog:
                self.dialog.reject()
                self.dialog.deleteLater()
                self.dialog = None
            if self.window and isValid(self.window):
                w = self.window
                w._autosave_timer.stop()
                w._finish_page_interaction()
                w._last_saved_state = w.get_current_scene_state()
                w._last_saved_document_state = w._capture_document_history_state()
                protected = w._fornax_mode in ('full', 'signatures')
                w.close()
                if not protected:
                    w.deleteLater()
                QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                app.processEvents()
            if self.sessions:
                self.sessions.close()

    def deepcopy_document(value):
        from copy import deepcopy
        return deepcopy(value)

    with TemporaryDirectory(prefix='fornax-perf-') as temporary, ExitStack() as stack:
        root = Path(temporary)
        for name, folder in (('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                             ('XDG_CACHE_HOME', 'cache'), ('APPDATA', 'config')):
            os.environ[name] = str(root/folder)
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        stack.enter_context(patch('core.paths._data_home', return_value=root/'data'))
        errors = []
        old_hook = sys.excepthook
        sys.excepthook = lambda typ, value, tb: errors.append(''.join(traceback.format_exception(typ, value, tb)))
        try:
            app = QApplication.instance() or QApplication([])
            app.setQuitOnLastWindowClosed(False)
            install_ui_font(app)
            theme_manager().select('dark')
            counts, samples, memory, identity = [], [], [], None
            count = sample_count or (5 if case.cold else 20)
            warmups = 0 if case.cold else 2
            run = None
            for repetition in range(warmups + count + 1):
                profiling = repetition == warmups + count
                if run is None or case.cold:
                    if run:
                        run.clean()
                    run = Run(root)
                    run.build()
                    if case.operation == 'load':
                        # Editor vazio para medir a abertura, com caches vazios.
                        run.window._load_document_into_scene(make_document(type(case)('empty', 'select_all', 'simple', 1))[0])
                else:
                    if run.dialog:
                        run.dialog.reject()
                        run.dialog.deleteLater()
                        run.dialog = None
                        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                    run.restore()
                if identity is None:
                    identity = run.input_sha256
                if run.input_sha256 != identity:
                    raise AssertionError('O cenário mudou entre repetições.')
                profiler = cProfile.Profile() if profiling else None
                run.iteration = repetition
                previous = run.observer.count
                if profiler:
                    profiler.enable()
                started = time.perf_counter_ns()
                run.operation()
                require_paint = case.operation not in ('snapshot_unchanged', 'layers', 'gallery', 'autosave', 'autosave_repeat')
                run.observer.complete(previous, require_paint)
                elapsed = (time.perf_counter_ns() - started) / 1e6
                if profiler:
                    profiler.disable()
                result = run.verify()
                if errors:
                    raise RuntimeError('Exceção de callback Qt: '+errors[0])
                if profiling:
                    names = {'apply_scene_state', 'refresh_layer_list', 'on_selection_changed', '_groupable_items',
                             '_update_board_connections', '_update_board_extent', 'refresh', 'get_current_scene_state',
                             '_capture_document_history_state', 'connector_paths', 'board_routes', '_routes', 'cutouts',
                             'paint', 'recalculate_text_position', 'line_reference_ink_bounds', 'write_recovery'}
                    for entry in profiler.getstats():
                        code = entry.code
                        if not isinstance(code, str) and code.co_name in names:
                            counts.append({'file': str(Path(code.co_filename).relative_to(ROOT)),
                                           'function': code.co_name, 'qualname': code.co_qualname,
                                           'calls': entry.callcount})
                elif repetition >= warmups:
                    samples.append(elapsed)
                    memory.append(result)
                    if progress_path:
                        write_json(progress_path, {'scenario': asdict(case), 'status': 'in_progress',
                                                  'input_sha256': identity, 'samples_ms': samples,
                                                  'summary': distribution(samples), 'memory_and_structure': memory,
                                                  'profile_counts': [], 'expected_samples': count})
            viewport = [run.window.view.viewport().width(), run.window.view.viewport().height()]
            run.clean()
            if errors:
                raise RuntimeError('Exceção durante limpeza: '+errors[0])
            return {'scenario': asdict(case), 'status': 'ok', 'input_sha256': identity,
                    'samples_ms': samples, 'summary': distribution(samples), 'memory_and_structure': memory,
                    'profile_counts': counts, 'viewport': viewport, 'ui_font': app.font().key(),
                    'completion': 'Paint processado e três turnos de eventos estáveis; arquivo verificado para autosave.'}
        finally:
            sys.excepthook = old_hook


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--label', default='antes')
    parser.add_argument('--case', help='Executar somente o cenário informado.')
    parser.add_argument('--samples', type=int, help='Amostra de diagnóstico; não substitui a rodada oficial.')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.samples is not None and args.samples < 1:
        parser.error('--samples precisa ser maior que zero.')
    from editor_scenarios import scenarios
    cases = [case for case in scenarios() if args.case is None or case.id == args.case]
    if not cases:
        parser.error('Cenário desconhecido.')
    if args.worker:
        try:
            result = worker(cases[0], args.samples, args.output)
        except Exception:
            result = json.loads(args.output.read_text()) if args.output.exists() else {'scenario': asdict(cases[0])}
            result.update(status='error', error=traceback.format_exc())
        write_json(args.output, result)
        return 0 if result['status'] == 'ok' else 1
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output/'ambiente.json', environment())
    results = []
    for case in cases:
        path = args.output/'raw'/args.label/(case.id+'.json')
        path.unlink(missing_ok=True)
        command = [sys.executable, str(Path(__file__).resolve()), '--worker', '--case', case.id,
                   '--output', str(path)]
        if args.samples:
            command += ['--samples', str(args.samples)]
        print('INICIANDO '+case.id, flush=True)
        with TemporaryDirectory(prefix='fornax-perf-env-') as root:
            env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'XDG_CONFIG_HOME': root+'/config',
                   'XDG_DATA_HOME': root+'/data', 'XDG_CACHE_HOME': root+'/cache', 'APPDATA': root+'/config'}
            try:
                execution = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=2400)
                log = execution.stdout + execution.stderr
                result = json.loads(path.read_text()) if path.exists() else {
                    'scenario': asdict(case), 'status': 'error', 'error': 'Worker sem resultado.'}
            except subprocess.TimeoutExpired:
                log = 'Timeout: o cenário excedeu 2400 segundos.'
                result = json.loads(path.read_text()) if path.exists() else {'scenario': asdict(case)}
                result.update(status='timeout', error=log)
                write_json(path, result)
        path.with_suffix('.log').write_text(log, encoding='utf-8')
        results.append(result)
        write_json(args.output/(args.label+'.json'), {'protocol': 1, 'results': results,
                                                     'diagnostic_samples': args.samples})
        print(case.id+': '+result['status']+
              (f" mediana={result['summary']['median_ms']:.2f} ms" if result['status'] == 'ok' else ''), flush=True)
    return int(any(result['status'] != 'ok' for result in results))


if __name__ == '__main__':
    raise SystemExit(main())
