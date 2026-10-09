"""Pixels e documentos exatos; geometria com precisão numérica explícita."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    args = parser.parse_args()
    before, after = (json.loads(path.read_text()) for path in (args.before, args.after))
    assert before.keys() == after.keys(), 'Cenários diferentes.'
    maximum = 0.0
    for name, state in before.items():
        for field in ('document', 'pixels'):
            assert state[field] == after[name][field], (name, field)
        assert state['routes'].keys() == after[name]['routes'].keys()
        route_delta = 0.0
        for target, elements in state['routes'].items():
            other = after[name]['routes'][target]
            assert len(elements) == len(other), (name, target, 'elementCount')
            for (x,y,kind),(u,v,other_kind) in zip(elements,other):
                assert kind == other_kind, (name,target,'elementType')
                route_delta = max(route_delta,abs(x-u),abs(y-v))
        assert route_delta <= 1e-10, (name,'routes',route_delta)
        assert len(state['bounds']) == len(after[name]['bounds']) == 4
        delta = max(abs(x-y) for x,y in zip(state['bounds'], after[name]['bounds']))
        # Não há tolerância raster. Somente as coordenadas geométricas em ponto
        # flutuante admite ruído de cópia/cálculo de QRectF/QPainterPath.
        assert delta <= 1e-10, (name, 'bounds', delta)
        maximum = max(maximum, delta, route_delta)
        print(f'{name}: documentos e pixels idênticos; deltas dos pontos/limites={route_delta:.3g}/{delta:.3g}')
    print(f'TOTAL: {len(before)} cenários; maior delta geométrico={maximum:.17g} unidades da cena.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
