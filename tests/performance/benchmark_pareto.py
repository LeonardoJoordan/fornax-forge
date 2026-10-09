"""Rodada Pareto: entradas isoladas, medições sem profiler e evidências comparáveis."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmark_editor import distribution, environment, rss_bytes, write_json

CASES = ('page-200', 'routing-100', 'board-1000', 'recovery-public-small',
         'recovery-public-large', 'recovery-signatures-large', 'recovery-full-large')
PRODUCT = ('features/editor/canvas_items.py', 'features/editor/page_scenes.py',
           'core/board_routing.py', 'core/fornax_container.py', 'core/fornax_session.py')


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def worker(case, samples):
    if case.startswith('recovery-'):
        from benchmark_recovery import worker as recovery
        from recovery_cases import RecoveryCase
        from core.fornax_container import PUBLIC_MODE
        _, mode, size = case.split('-')
        return recovery(RecoveryCase(case, PUBLIC_MODE if mode == 'public' else mode, size == 'large'), samples)
    from PySide6.QtWidgets import QApplication
    from core.ui_font import install_ui_font
    from core.themes import theme_manager
    from core.board_routing import board_routes, _routes
    from editor_scenarios import Scenario, make_document, fingerprint
    from paint_cases import settle, close_window, screen_image, image_hash
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setCursorFlashTime(0)
    install_ui_font(app)
    theme_manager().select('dark')
    errors = []
    sys.excepthook = lambda typ, value, tb: errors.append(''.join(traceback.format_exception(typ, value, tb)))
    times, states, paint_times = [], [], []
    window = None
    try:
        if case == 'page-200':
            from features.editor.editor_window import EditorWindow
            from page_cases import PageSession, PageCase
            window = EditorWindow()
            session = PageSession(window, PageCase('duplex-200', 200), app)
            identity = fingerprint(session.document, session.provider)
            for index in range(samples + 2):
                start = time.perf_counter()
                session.perform()
                elapsed = (time.perf_counter() - start) * 1000
                state = session.verify()
                if index >= 2:
                    times.append(elapsed); states.append(state)
            final = session.verify(all_pages=True)
            cached = window._inactive_page_scene
            extra = {'retained_scenes': int(cached is not None),
                     'retained_estimated_bytes': cached.estimated_bytes if cached else 0,
                     'final_all_pages': final}
        else:
            document, provider = make_document(Scenario(case, 'drag_one', 'connected', 100))
            if case == 'board-1000':
                from core.model_document import normalize_model_document
                from core.organogram import group_rect
                from features.editor.editor_window import EditorWindow
                for index, group in enumerate(document['organogram']['groups']):
                    group.update(columns=2, rows=5)
                    rect = group_rect(group)
                    group.update(x=(index % 10) * (rect.width() + 400),
                                 y=(index // 10) * (rect.height() + 400))
                document = normalize_model_document(document)
                window = EditorWindow()
                window.load_starter_document(document, provider)
                window.resize(1280, 800); window.show(); window._autosave_timer.stop()
                window.switch_model_page('organogram'); window._zoom_to_fit(); settle(app)
                group_item = next(i for i in window._board_items() if i.data['id'] == 'block-000')
                origin = group_item.pos()
                window.history.clear()
                window.save_snapshot()
            identity = fingerprint(document, provider)
            extra = {'groups': 100, 'connections': 99, 'cards': 1000 if window else 100}
            for index in range(samples + 2):
                # Duas células evitam empates de arredondamento quando o centro
                # inicial do conjunto está exatamente na meia célula.
                distance = (index + 1) * (2 * window.scene._board_grid if window else 5 * 300 / 25.4)
                if window:
                    previous_position = group_item.pos()
                    start = time.perf_counter()
                    group_item.setPos(origin.x() + distance, origin.y())
                    window.save_snapshot(); settle(app)
                    elapsed = (time.perf_counter() - start) * 1000
                    assert group_item.pos() != previous_position, 'O magnetismo impediu o movimento medido.'
                    state = {'document': digest(window._document_with_active_page()),
                             'position': [group_item.x(), group_item.y()],
                             'pixels': image_hash(screen_image(window, workspace=True))}
                    start = time.perf_counter()
                    window.scene.update(window.view.mapToScene(window.view.viewport().rect()).boundingRect())
                    settle(app)
                    paint = (time.perf_counter() - start) * 1000
                    if index >= 2: paint_times.append(paint)
                else:
                    board = deepcopy(document['organogram'])
                    board['groups'][0]['x'] += distance
                    _routes.cache_clear()
                    start = time.perf_counter(); paths = board_routes(board)
                    elapsed = (time.perf_counter() - start) * 1000
                    state = digest([(key, [(p.x(), p.y()) for p in points], crowded)
                                    for key, (points, crowded) in sorted(paths.items())])
                if index >= 2: times.append(elapsed); states.append(state)
            if window:
                before = deepcopy(window._document_with_active_page())
                window.undo(); window.redo(); settle(app)
                assert window._document_with_active_page() == before
                extra['undo_redo_verified'] = True
        assert not errors, errors
        return {'status': 'ok', 'case': case, 'input_sha256': identity,
                'samples_ms': times, 'summary': distribution(times), 'states': states,
                'paint_samples_ms': paint_times,
                'paint_summary': distribution(paint_times) if paint_times else None,
                'rss_bytes': rss_bytes(), 'font': app.font().key(), **extra}
    finally:
        if window is not None: close_window(window, app)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--label', default='antes')
    parser.add_argument('--case', choices=CASES, action='append')
    parser.add_argument('--samples', type=int, default=5)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    if args.samples < 1: parser.error('Amostras devem ser positivas.')
    if args.worker:
        try: result = worker(args.case[0], args.samples)
        except Exception: result = {'status': 'error', 'error': traceback.format_exc()}
        write_json(args.output, result)
        return int(result['status'] != 'ok')
    args.output.mkdir(parents=True, exist_ok=True)
    metadata = environment()
    metadata['pareto_sha256'] = {path: sha256((ROOT / path).read_bytes()).hexdigest() for path in PRODUCT}
    metadata['instrument_sha256'] = sha256(Path(__file__).read_bytes()).hexdigest()
    metadata['samples'] = args.samples
    write_json(args.output / f'ambiente-{args.label}.json', metadata)
    results = {}
    for case in args.case or CASES:
        print('INICIANDO ' + case, flush=True)
        target = args.output / args.label / (case + '.json')
        target.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix='fornax-pareto-') as root:
            env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'QT_SCALE_FACTOR': '1',
                   'XDG_CONFIG_HOME': root+'/config', 'XDG_DATA_HOME': root+'/data',
                   'XDG_CACHE_HOME': root+'/cache', 'PYTHONDONTWRITEBYTECODE': '1'}
            with target.with_suffix('.log').open('w') as log:
                process = subprocess.run([sys.executable, __file__, '--worker', '--case', case,
                                          '--samples', str(args.samples), '--output', str(target)],
                                         cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=900)
        result = json.loads(target.read_text())
        results[case] = result
        write_json(args.output / (args.label+'.json'), results)
        print(case + ' ' + result['status'] + ' ' + str(result.get('summary')), flush=True)
        if process.returncode: return process.returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
