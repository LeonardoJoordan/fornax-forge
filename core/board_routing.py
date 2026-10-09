"""Rotas ortogonais com portas permitidas e canais separados por superior.

O cache usa somente geometria, portas e conexões; dados pessoais não participam.
"""
from bisect import bisect_left, bisect_right, insort
from collections import OrderedDict
from functools import lru_cache
import heapq
import math
from statistics import median

from PySide6.QtCore import QPointF
from core.board_borders import bordered_group_bounds

UNITS_PER_MM = 300 / 25.4
SIDES = ("top", "right", "bottom", "left")
NORMALS = {"top": (0, -1), "right": (1, 0), "bottom": (0, 1), "left": (-1, 0)}


def _port(rect, side):
    left, top, right, bottom = rect
    return {"top": ((left + right) / 2, top), "bottom": ((left + right) / 2, bottom),
            "left": (left, (top + bottom) / 2), "right": (right, (top + bottom) / 2)}[side]


def _distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _clean(points):
    result = []
    for point in points:
        if result and _distance(point, result[-1]) < 1e-7:
            continue
        while len(result) > 1:
            a, b = result[-2:]
            cross = (b[0] - a[0]) * (point[1] - b[1]) - (b[1] - a[1]) * (point[0] - b[0])
            dot = (b[0] - a[0]) * (point[0] - b[0]) + (b[1] - a[1]) * (point[1] - b[1])
            if abs(cross) > 1e-7 or dot < 0:
                break
            result.pop()
        result.append(point)
    return tuple(result)


class _Rectangles:
    CACHE_LIMIT = 16384

    def __init__(self, rects):
        self.rects = rects
        # Obstáculos ficam fixos durante uma chamada de _routes. Canais de
        # conectores, que mudam a cada ligação, deliberadamente não entram aqui.
        self._hit_cache = OrderedDict()
        self.cell = max(10 * UNITS_PER_MM, median(max(r[2] - r[0], r[3] - r[1]) for r in rects.values()))
        self.buckets = {}
        self.large = set()
        for identifier, rect in rects.items():
            cells = self._cells(rect)
            if cells is None:
                self.large.add(identifier)
            else:
                for cell in cells:
                    self.buckets.setdefault(cell, set()).add(identifier)

    def _cells(self, rect):
        x0, y0, x1, y1 = (math.floor(value / self.cell) for value in rect)
        if (x1 - x0 + 1) * (y1 - y0 + 1) > 512:
            return None
        return ((x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1))

    def query(self, rect):
        cells = self._cells(rect)
        if cells is None:
            ids = self.rects.keys()
        else:
            ids = set(self.large)
            for cell in cells:
                ids.update(self.buckets.get(cell, ()))
        left, top, right, bottom = rect
        result = []
        for identifier in ids:
            r = self.rects[identifier]
            if r[0] <= right and r[2] >= left and r[1] <= bottom and r[3] >= top:
                result.append((identifier, r))
        return result

    def hits(self, a, b, excluded=()):
        # Sem arredondar coordenadas: inclusive consultas próximas às bordas
        # conservam os mesmos resultados e a mesma tolerância geométrica.
        key = (a, b, tuple(excluded)) if a <= b else (b, a, tuple(excluded))
        cached = self._hit_cache.get(key)
        if cached is not None:
            self._hit_cache.move_to_end(key)
            return cached
        count = self._count_hits(a, b, excluded)
        if self.CACHE_LIMIT > 0:
            if len(self._hit_cache) >= self.CACHE_LIMIT:
                self._hit_cache.popitem(last=False)
            self._hit_cache[key] = count
        return count

    def _count_hits(self, a, b, excluded=()):
        bounds = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
        count = 0
        for identifier, (left, top, right, bottom) in self.query(bounds):
            if identifier in excluded:
                continue
            if abs(a[0] - b[0]) < 1e-7:
                hit = left + 1e-6 < a[0] < right - 1e-6 and min(b[1], a[1]) < bottom - 1e-6 and max(b[1], a[1]) > top + 1e-6
            else:
                hit = top + 1e-6 < a[1] < bottom - 1e-6 and min(b[0], a[0]) < right - 1e-6 and max(b[0], a[0]) > left + 1e-6
            count += bool(hit)
        return count


class _Channels:
    def __init__(self, spacing):
        self.spacing = spacing
        self.coordinates = [[], []]
        self.lines = [{}, {}]

    def _segment(self, a, b):
        axis = 0 if abs(a[0] - b[0]) < 1e-7 else 1
        coordinate = round(a[axis], 6)
        lo, hi = sorted((a[1 - axis], b[1 - axis]))
        return axis, coordinate, lo, hi

    def hits(self, a, b, owner):
        if _distance(a, b) < 1e-7:
            return 0
        axis, coordinate, lo, hi = self._segment(a, b)
        coordinates = self.coordinates[axis]
        count = 0
        for fixed in coordinates[bisect_left(coordinates, coordinate - self.spacing + 1e-5):bisect_right(coordinates, coordinate + self.spacing - 1e-5)]:
            for start, end, parent in self.lines[axis][fixed]:
                if parent != owner and min(end, hi) - max(start, lo) > 1e-5:
                    count += 1
        return count

    def crossings(self, a, b, owner):
        """Interseções perpendiculares com outras hierarquias, inclusive quinas."""
        if _distance(a, b) < 1e-7:
            return 0
        axis, coordinate, lo, hi = self._segment(a, b)
        opposite = 1 - axis
        coordinates = self.coordinates[opposite]
        intersections = set()
        for fixed in coordinates[bisect_left(coordinates, lo - 1e-5):bisect_right(coordinates, hi + 1e-5)]:
            for start, end, parent in self.lines[opposite][fixed]:
                if parent != owner and start - 1e-5 <= coordinate <= end + 1e-5:
                    intersections.add((fixed, parent))
        return len(intersections)

    def add(self, points, owner):
        for a, b in zip(points, points[1:]):
            axis, fixed, lo, hi = self._segment(a, b)
            if fixed not in self.lines[axis]:
                insort(self.coordinates[axis], fixed)
                self.lines[axis][fixed] = []
            self.lines[axis][fixed].append((lo, hi, owner))


def _core_candidates(a, b, rects, spacing):
    xmid, ymid = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    yield [a, (a[0], ymid), (b[0], ymid), b]
    yield [a, (xmid, a[1]), (xmid, b[1]), b]
    # Canais vizinhos do meio evitam empurrar uma ligação até a porta do
    # subordinado e bloquear a ligação seguinte em um quadro com vários setores.
    for step in (1, -1, 2, -2, 3, -3, 5, -5, 8, -8, 13, -13):
        y, x = ymid + step * spacing, xmid + step * spacing
        yield [a, (a[0], y), (b[0], y), b]
        yield [a, (x, a[1]), (x, b[1]), b]
    yield [a, (b[0], a[1]), b]
    yield [a, (a[0], b[1]), b]
    xs = [xmid, min(r[0] for r in rects) - spacing, max(r[2] for r in rects) + spacing]
    ys = [ymid, min(r[1] for r in rects) - spacing, max(r[3] for r in rects) + spacing]
    for step in (0, 1, -1, 2, -2, 3, -3, 5, -5, 8, -8, 13, -13):
        xs.extend((a[0] + step * spacing, b[0] + step * spacing))
        ys.extend((a[1] + step * spacing, b[1] + step * spacing))
    for x in dict.fromkeys(xs):
        yield [a, (x, a[1]), (x, b[1]), b]
    for y in dict.fromkeys(ys):
        yield [a, (a[0], y), (b[0], y), b]


def _search(a, b, obstacles, channels, owner, spacing, local):
    """Busca limitada para contornar obstáculos ou cruzamentos evitáveis."""
    xs, ys = {a[0], b[0]}, {a[1], b[1]}
    for _, rect in local:
        xs.update((rect[0] - spacing, rect[2] + spacing))
        ys.update((rect[1] - spacing, rect[3] + spacing))
    for axis, coordinates in enumerate(channels.coordinates):
        near = sorted(coordinates, key=lambda value: min(abs(value - a[axis]), abs(value - b[axis])))[:12]
        for fixed in near:
            (xs if axis == 0 else ys).update((fixed - spacing, fixed + spacing))
            # As extremidades permitem contornar uma linha, em vez de atravessá-la.
            ends = sorted({value for start, end, parent in channels.lines[axis][fixed]
                           if parent != owner for value in (start, end)},
                          key=lambda value: min(abs(value - a[1 - axis]), abs(value - b[1 - axis])))[:12]
            for value in ends:
                (ys if axis == 0 else xs).update((value - spacing, value + spacing))
    for value in (a[0], b[0]):
        xs.update((value - spacing, value + spacing))
    for value in (a[1], b[1]):
        ys.update((value - spacing, value + spacing))
    xs, ys = sorted(xs), sorted(ys)
    start = (xs.index(a[0]), ys.index(a[1]))
    goal = (xs.index(b[0]), ys.index(b[1]))
    queue = [(0, 0, start, -1)]
    previous, costs, clear, crossing_cost = {}, {(start, -1): 0}, {}, {}
    for _ in range(6000):
        if not queue:
            break
        _, cost, node, direction = heapq.heappop(queue)
        key = (node, direction)
        if cost != costs.get(key):
            continue
        if node == goal:
            points = []
            while key is not None:
                (x, y), _ = key
                points.append((xs[x], ys[y]))
                key = previous.get(key)
            return list(reversed(points))
        x, y = node
        for nx, ny, axis in ((x - 1, y, 0), (x + 1, y, 0), (x, y - 1, 1), (x, y + 1, 1)):
            if not (0 <= nx < len(xs) and 0 <= ny < len(ys)):
                continue
            next_node = (nx, ny)
            edge_key = tuple(sorted((node, next_node)))
            if edge_key not in clear:
                p, q = (xs[x], ys[y]), (xs[nx], ys[ny])
                clear[edge_key] = not obstacles.hits(p, q) and not channels.hits(p, q, owner)
                crossing_cost[edge_key] = (channels.crossings(p, q, owner) * spacing * 16
                                           if clear[edge_key] else 0)
            if not clear[edge_key]:
                continue
            next_cost = (cost + abs(xs[nx] - xs[x]) + abs(ys[ny] - ys[y])
                         + (spacing if direction not in (-1, axis) else 0) + crossing_cost[edge_key])
            next_key = (next_node, axis)
            if next_cost < costs.get(next_key, math.inf):
                costs[next_key] = next_cost
                previous[next_key] = key
                heuristic = abs(xs[nx] - b[0]) + abs(ys[ny] - b[1])
                heapq.heappush(queue, (next_cost + heuristic, next_cost, next_node, axis))
    return None


@lru_cache(maxsize=16)
def _routes(groups, edges, spacing):
    geometry = {identifier: rect for identifier, rect, _, _ in groups}
    ports = {identifier: (entry, exit) for identifier, _, entry, exit in groups}
    padding = spacing / 3
    expanded = {identifier: (r[0] - padding, r[1] - padding, r[2] + padding, r[3] + padding) for identifier, r in geometry.items()}
    obstacles, channels = _Rectangles(expanded), _Channels(spacing)
    results = []
    for parent, child in edges:
        choices = []
        # O armazenamento histórico é superior -> subordinado; as portas são
        # entrada no superior e saída no subordinado.
        for entry in ports[parent][0]:
            for exit in ports[child][1]:
                first, last = _port(geometry[parent], entry), _port(geometry[child], exit)
                n1, n2 = NORMALS[entry], NORMALS[exit]
                a = (first[0] + n1[0] * spacing, first[1] + n1[1] * spacing)
                b = (last[0] + n2[0] * spacing, last[1] + n2[1] * spacing)
                choices.append((_distance(a, b), first, last, a, b))
        choices.sort()
        best, best_cost, fallback, fallback_score = None, math.inf, None, (math.inf, math.inf)
        best_crossings = math.inf
        searches = []
        def score(points):
            crossings = sum(channels.crossings(p, q, parent) for p, q in zip(points, points[1:]))
            cost = (sum(_distance(p, q) for p, q in zip(points, points[1:]))
                    + max(0, len(points) - 2) * spacing + crossings * spacing * 16)
            # Não troca um canal central por outro distante apenas por ruído
            # de ponto flutuante em caminhos com o mesmo comprimento.
            return round(cost, 6), crossings
        pair = (geometry[parent], geometry[child])
        for _, first, last, a, b in choices:
            terminal_hits = (obstacles.hits(first, a, (parent,)) + obstacles.hits(b, last, (child,))
                             + channels.hits(first, a, parent) + channels.hits(b, last, parent))
            if terminal_hits == 0:
                searches.append((first, last, a, b))
            for core in _core_candidates(a, b, pair, spacing):
                points = _clean([first, *core, last])
                cost, crossings = score(points)
                if best is not None and cost >= best_cost:
                    continue
                hits = terminal_hits + sum(obstacles.hits(p, q) + channels.hits(p, q, parent) for p, q in zip(core, core[1:]))
                if (hits, cost) < fallback_score:
                    fallback, fallback_score = points, (hits, cost)
                if hits == 0 and cost < best_cost:
                    best, best_cost, best_crossings = points, cost, crossings
        if best is None or best_crossings:
            # Examina no máximo quatro pares de portas para manter a edição ágil.
            for first, last, a, b in searches[:4]:
                bounds = (min(a[0], b[0]) - spacing * 2, min(a[1], b[1]) - spacing * 2,
                          max(a[0], b[0]) + spacing * 2, max(a[1], b[1]) + spacing * 2)
                local = sorted(obstacles.query(bounds), key=lambda item: _distance(_port(item[1], "top"), a))[:24]
                core = _search(a, b, obstacles, channels, parent, spacing, local)
                if core:
                    points = _clean([first, *core, last])
                    cost, crossings = score(points)
                    if cost < best_cost:
                        best, best_cost, best_crossings = points, cost, crossings
                if best is not None and best_crossings == 0:
                    break
        points = best or fallback
        channels.add(points, parent)
        results.append((parent, child, points, best is None))
    return tuple(results)


def board_routes(board):
    groups = []
    for group in board["groups"]:
        # A folga e o traço do contorno externo delimitam as portas e os
        # obstáculos. Bordas internas dos cartões não mudam a rota.
        bounds = bordered_group_bounds(group)
        rect = (bounds.left(), bounds.top(), bounds.right(), bounds.bottom())
        groups.append((group["id"], rect,
                       tuple(side for side in SIDES if side in group.get("entry_sides", ["bottom"])),
                       tuple(side for side in SIDES if side in group.get("exit_sides", ["top"]))))
    if not board["connections"]:
        return {}
    from core.board_connectors import connector_style
    width = max(connector_style(edge, board)["width_mm"] for edge in board["connections"])
    spacing = max(3, width + 1) * UNITS_PER_MM
    geometry = {identifier: rect for identifier, rect, _, _ in groups}
    def position(identifier):
        left, top, right, bottom = geometry[identifier]
        return ((left + right) / 2, (top + bottom) / 2)
    # Hierarquias seguem a ordem espacial, sem depender dos UUIDs criados ao salvar/copiar.
    edges = tuple(sorted(((edge["source"], edge["target"]) for edge in board["connections"]),
                         key=lambda edge: (position(edge[0]), position(edge[1]), edge)))
    return {(parent, child): ([QPointF(*point) for point in points], crowded)
            for parent, child, points, crowded in _routes(tuple(sorted(groups)), edges, spacing)}
