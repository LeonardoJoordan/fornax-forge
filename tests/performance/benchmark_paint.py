"""Pintura da view em processos isolados, com tempos e perfis separados."""
import argparse
import cProfile
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmark_editor import distribution, environment, rss_bytes, write_json
from paint_cases import cases


def worker(case, path, samples=20):
    from PySide6.QtWidgets import QApplication
    from features.editor.organogram_editor import BoardGraphicsView
    from features.editor.editor_window import EditorWindow
    from core.ui_font import install_ui_font
    from core.themes import theme_manager
    from editor_scenarios import fingerprint
    from copy_cases import canonical_copy_document
    from paint_cases import PaintSession, close_window, settle

    class ObservedView(BoardGraphicsView):
        def __init__(self, *args):
            super().__init__(*args)
            self.paints = []

        def paintEvent(self, event):
            started = time.perf_counter_ns()
            super().paintEvent(event)
            rect = event.region().boundingRect()
            self.paints.append({'ms': (time.perf_counter_ns() - started) / 1e6,
                                'bounding_area': rect.width() * rect.height(),
                                'regions': event.region().rectCount()})

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setCursorFlashTime(0)
    install_ui_font(app)
    theme_manager().select('dark')
    errors = []
    old_hook = sys.excepthook
    sys.excepthook = lambda typ, value, tb: errors.append(''.join(traceback.format_exception(typ, value, tb)))
    timings, structure, profiles = [], [], []
    window = None
    try:
        with patch('features.editor.controls.BoardGraphicsView', ObservedView):
            window = EditorWindow()
        session = PaintSession(window, case, app)
        identity = fingerprint(session.document, session.provider)
        for repetition in range(2 + samples + 1):
            if repetition:
                session.restore()
            previous = len(window.view.paints)
            profiler = cProfile.Profile() if repetition == 2 + samples else None
            if profiler:
                profiler.enable()
            started = time.perf_counter_ns()
            session.perform()
            settle(app)
            elapsed = (time.perf_counter_ns() - started) / 1e6
            if profiler:
                profiler.disable()
            painted = window.view.paints[previous:]
            if not painted:
                raise AssertionError('Operação sem pintura efetiva da view.')
            capture_before = len(window.view.paints)
            state = session.verify()
            if len(window.view.paints) != capture_before:
                raise AssertionError('A captura de pixels provocou repintura.')
            state['document_sha256'] = sha256(json.dumps(canonical_copy_document(state.pop('document')),
                                                       sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            state.update(rss_bytes=rss_bytes(), paint_duration_ms=sum(p['ms'] for p in painted),
                         paint_events=len(painted),
                         dirty_bounding_area=sum(p['bounding_area'] for p in painted),
                         viewport_area=window.view.viewport().width() * window.view.viewport().height())
            if errors:
                raise AssertionError(errors[0])
            if state['rss_bytes'] and state['rss_bytes'] > 2 * 1024**3:
                raise MemoryError('RSS excede o limite de 2 GiB.')
            if profiler:
                for entry in profiler.getstats():
                    code = entry.code
                    if isinstance(code, str):
                        if 'drawImage' in code:
                            profiles.append({'function': 'QPainter.drawImage', 'calls': entry.callcount})
                    elif code.co_qualname in ('BoardGroupItem.paint', 'BoardConnectorItem.paint',
                                             'RulerWorkspace.refresh', 'Ruler.paintEvent',
                                             'DesignerBox.paint', 'BleedTextItem.paint'):
                        profiles.append({'function': code.co_qualname, 'calls': entry.callcount})
            elif repetition >= 2:
                timings.append(elapsed)
                structure.append(state)
                write_json(path, {'scenario': asdict(case), 'status': 'in_progress',
                                  'input_sha256': identity, 'samples_ms': timings,
                                  'summary': distribution(timings), 'states': structure})
        return {'scenario': asdict(case), 'status': 'ok', 'input_sha256': identity,
                'samples_ms': timings, 'summary': distribution(timings), 'states': structure,
                'profile_counts': profiles, 'ui_font': app.font().key(),
                'viewport': [window.view.viewport().width(), window.view.viewport().height()],
                'paint_summary': distribution([s['paint_duration_ms'] for s in structure]),
                'completion': 'Pintura nativa e seis turnos de eventos; captura sem repintura.'}
    finally:
        if window is not None:
            close_window(window, app)
        sys.excepthook = old_hook
        if errors:
            raise AssertionError(errors[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--label', default='antes')
    parser.add_argument('--case', action='append')
    parser.add_argument('--samples', type=int, default=20)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    selected = [c for c in cases() if args.case is None or c.id in args.case]
    if not selected or args.samples < 1:
        parser.error('Cenário/amostras inválidos.')
    if args.worker:
        try:
            result = worker(selected[0], args.output, args.samples)
        except Exception:
            result = {'scenario': asdict(selected[0]), 'status': 'error', 'error': traceback.format_exc()}
        write_json(args.output, result)
        return int(result['status'] != 'ok')
    args.output.mkdir(parents=True, exist_ok=True)
    metadata = environment()
    metadata.update(warm_samples=args.samples, benchmark='benchmark_paint.py', scale_factor=1)
    write_json(args.output/'ambiente.json', metadata)
    results = []
    for case in selected:
        path = args.output/'raw'/args.label/(case.id+'.json')
        print('INICIANDO '+case.id, flush=True)
        with TemporaryDirectory(prefix='fornax-paint-bench-') as root:
            env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'QT_SCALE_FACTOR': '1', 'XDG_CONFIG_HOME': root+'/config',
                   'XDG_DATA_HOME': root+'/data', 'XDG_CACHE_HOME': root+'/cache', 'APPDATA': root+'/config'}
            result = subprocess.run([sys.executable, __file__, '--worker', '--case', case.id,
                                     '--output', str(path), '--samples', str(args.samples)],
                                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.with_suffix('.log').write_text(result.stdout + result.stderr)
        value = json.loads(path.read_text()) if path.exists() else {'scenario': asdict(case), 'status': 'error', 'error': 'Processo sem resultado.'}
        if result.returncode and value['status'] == 'ok':
            value.update(status='error', error=f'Código de saída {result.returncode}')
        results.append(value)
        write_json(args.output/(args.label+'.json'), {'results': results})
        print(case.id+': '+value['status']+' '+str(value.get('summary', {})), flush=True)
        if value['status'] != 'ok':
            print(value.get('error', ''), flush=True)
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
