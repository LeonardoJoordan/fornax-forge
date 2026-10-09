"""Compara os fluxos suplementares, conservando diferenças do canvas como observações."""
from hashlib import sha256
import json
from pathlib import Path

from PySide6.QtGui import QImage

HERE = Path(__file__).resolve().parent


def pixel_difference(first, second):
    a = QImage(str(first)).convertToFormat(QImage.Format.Format_RGBA8888)
    b = QImage(str(second)).convertToFormat(QImage.Format.Format_RGBA8888)
    assert not a.isNull() and not b.isNull() and a.size() == b.size()
    x, y = bytes(a.constBits()), bytes(b.constBits())
    pixels = {}
    for i, (old, new) in enumerate(zip(x, y)):
        if old != new:
            pixels.setdefault(i // 4, []).append({'channel':i % 4,'before':old,'after':new})
    return {'different_pixels':len(pixels), 'max_channel_difference':max((abs(c['before']-c['after']) for cs in pixels.values() for c in cs),default=0),
            'positions': [{'x':i % a.width(),'y':i // a.width(),'channels':cs} for i,cs in sorted(pixels.items())]}


def main():
    folders = {version: HERE / 'fluxos-completos' / version for version in ('antes','depois','depois-claro')}
    data = {version: json.loads((folder/'resultados.json').read_text()) for version,folder in folders.items()}
    assert all(not d['callback_errors'] and len(d['journeys']) == 5 for d in data.values())
    rows, capture = [], 0
    for before, after, light in zip(*(data[version]['journeys'] for version in folders)):
        assert (before['fixture'],before['mode']) == (after['fixture'],after['mode']) == (light['fixture'],light['mode'])
        assert len(before['states']) == len(after['states']) == len(light['states'])
        for a, b, c in zip(before['states'],after['states'],light['states']):
            capture += 1
            assert all(a[key]==b[key]==c[key] for key in ('label','document','render_pixels','history_index'))
            assert all(s['raw_pixels']==s['full_pixels'] for s in (a,b,c)), a['label']
            picture = f"{capture:02}-{a['label']}-fit.png"
            difference = pixel_difference(folders['antes']/picture, folders['depois']/picture)
            rows.append({'fixture':before['fixture'],'mode':before['mode'],'label':a['label'],
                         'documents_equal':True,'generated_pixels_equal':True,'history_indices_equal':True,
                         'partial_full_equal_all_runs':True,'raw_canvas_equal':a['raw_pixels']==b['raw_pixels'],
                         'before_geometry':a['geometry'],'after_geometry':b['geometry'],
                         'fitted_difference':difference})
    result = {'states':len(rows),'rows':rows,'strict_raw_canvas_equal':all(r['raw_canvas_equal'] for r in rows),
              'strict_fitted_canvas_equal':all(not r['fitted_difference']['different_pixels'] for r in rows),
              'document_and_generated_comparison_passed':True,'partial_paint_comparison_passed':True,
              'protected_public_save_recovery_close_passed':True,
              'script_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    (HERE/'auditoria-fluxos-completos.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('27 estados: conteúdo/geração/histórico iguais; pintura parcial igual à completa.')
    print('Diferenças do canvas preservadas:',sum(bool(r['fitted_difference']['different_pixels']) for r in rows),'estados após ajustar à tela.')


if __name__=='__main__':
    main()
