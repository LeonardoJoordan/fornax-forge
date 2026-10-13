"""Exportação real de 100 JPEGs; modelo privado lido sem modificar a biblioteca.

Cada amostra usa processo/configuração isolados. A medição inclui planejamento,
base estática, workers, codificação e publicação; leitura inicial do .fornax e
verificação dos arquivos ficam fora do intervalo. Evidências são locais.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def sample(args):
    import resource
    import platform
    from PySide6.QtCore import QEventLoop, QTimer, qVersion
    from PySide6.QtGui import QImageReader, QFont, QFontInfo
    from PySide6.QtWidgets import QApplication
    from core.fornax_container import open_public_fornax
    from core.performance import ExportPerformance
    from core.ui_font import install_ui_font
    from features.generator.renderer import renderers_for_document
    from features.generator.manager import RenderManager

    app = QApplication([])
    install_ui_font(app)
    opened = open_public_fornax(args.model)
    document = opened.document()
    boxes = [box for page in document['pages'] for box in page['boxes']
             if box.get('custom_name') == args.box]
    if len(boxes) != 1:
        raise ValueError('A caixa solicitada deve existir uma única vez.')
    box = boxes[0]
    if args.mode == 'on':
        from core.text_effects import normalize_shadow
        box['shadow'] = normalize_shadow(dict(enabled=True, color='#000000',
            opacity=.5, angle=45., distance=8., blur=6.))
    else:
        box.pop('shadow', None)
    plain = [dict(nome=f'Pessoa de Teste {i + 1:03d}', postgrad='Capitão',
                  conjuge='Acompanhante de Teste', data='12 de outubro') for i in range(100)]
    rows = [dict(row) for row in plain]
    errors = []
    loop = QEventLoop()
    with tempfile.TemporaryDirectory(prefix='fornax-shadow-jpeg-') as output:
        started = time.perf_counter()
        renderers = renderers_for_document(document, asset_provider=opened.asset)
        static_times = []
        for renderer in renderers:
            original = renderer.pre_render_static_base
            def measured(original=original):
                before = time.perf_counter()
                original()
                static_times.append((time.perf_counter() - before) * 1000)
            renderer.pre_render_static_base = measured
        manager = RenderManager(renderers, plain, rows, Path(output), '{nome}',
            export_format='JPEG', target_w_mm=document['target_w_mm'],
            target_h_mm=document['target_h_mm'], performance=ExportPerformance())
        manager.error_occurred.connect(errors.append)
        manager.error_occurred.connect(loop.quit)
        manager.finished_process.connect(loop.quit)
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(lambda: (errors.append('Tempo limite'), manager.stop(), loop.quit()))
        timeout.start(180000)
        manager.start()
        if not errors:
            loop.exec()
        for worker in manager.workers:
            worker.wait()
        elapsed = time.perf_counter() - started
        timeout.stop()
        if errors:
            raise AssertionError(errors)
        files = sorted(Path(output).glob('*.jpg'))
        if len(files) != 100:
            raise AssertionError(f'Esperados 100 JPEGs; encontrados {len(files)}')
        expected = renderers[0].output_dimensions()
        hashes, size = {}, 0
        for path in files:
            image = QImageReader(str(path)).read()
            if image.isNull() or (image.width(), image.height()) != expected:
                raise AssertionError(f'JPEG inválido: {path.name}')
            raw = path.read_bytes()
            hashes[path.name] = hashlib.sha256(raw).hexdigest()
            size += len(raw)
        args.evidence.mkdir(parents=True, exist_ok=True)
        (args.evidence / (args.mode + '.jpg')).write_bytes(files[0].read_bytes())
    return dict(seconds=elapsed, static_ms=sum(static_times), workers=len(manager.workers),
        count=len(files), dimensions=expected, bytes=size, jpeg_hashes=hashes,
        peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        source_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),
        model_name=document.get('name'), box=args.box, mode=args.mode,
        font=box['font_family'], resolved_font=QFontInfo(QFont(box['font_family'])).family(),
        python=sys.version, qt=qVersion(), cpu=platform.processor(), cpu_count=os.cpu_count(),
        dpi=300, quality=95, shadow=box.get('shadow'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--box', default='Texto')
    parser.add_argument('--mode', choices=('off', 'on'), default='off')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, default=ROOT / 'build/text-shadow-benchmark')
    parser.add_argument('--samples', type=int, default=5)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.worker:
        args.output.write_text(json.dumps(sample(args), indent=2, ensure_ascii=False))
        return
    samples, rejected = [], []
    warmup = None
    for index in range(args.samples + 6):
        with tempfile.TemporaryDirectory(prefix='fornax-shadow-bench-') as root:
            env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'QT_SCALE_FACTOR': '1',
                   'XDG_CONFIG_HOME': root+'/config', 'XDG_DATA_HOME': root+'/data',
                   'XDG_CACHE_HOME': root+'/cache'}
            output = Path(root) / 'sample.json'
            command = [sys.executable, str(Path(__file__).resolve()), '--worker',
                       '--model', str(args.model.resolve()), '--box', args.box,
                       '--mode', args.mode, '--output', str(output),
                       '--evidence', str(args.evidence.resolve())]
            process = subprocess.run(command, cwd=ROOT, env=env, check=True,
                                     capture_output=True, text=True, timeout=210)
            result = json.loads(output.read_text())
        if ('[WARN]' in process.stdout or '[WARN]' in process.stderr
                or warmup is not None and result['jpeg_hashes'] != warmup['jpeg_hashes']):
            rejected.append(dict(sample=result, stdout=process.stdout, stderr=process.stderr))
            print(f'{args.mode} {index}: AMOSTRA REJEITADA (aviso/pixels divergentes)', flush=True)
            continue
        print(f'{args.mode} {index}: {result["seconds"]:.3f}s, '
              f'base {result["static_ms"]:.1f}ms, {result["peak_rss_mib"]:.1f} MiB', flush=True)
        if warmup is not None:  # aquecimento de bibliotecas/arquivos descartado
            samples.append(result)
        else:
            warmup = result
        args.output.write_text(json.dumps(dict(warmup=warmup, rejected=rejected,
            samples=samples, median_s=statistics.median(s['seconds'] for s in samples) if samples else None),
            indent=2, ensure_ascii=False))
        if len(samples) == args.samples:
            return
    raise RuntimeError('Não foi possível obter amostras consistentes; veja os resultados rejeitados.')


if __name__ == '__main__':
    main()
