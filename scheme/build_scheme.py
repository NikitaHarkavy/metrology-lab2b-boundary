"""Подробная схема алгоритма process_table (ГОСТ 19.701-90) и расчёт метрики граничных значений.

Запуск: python3 build_scheme.py
  -> Схема_алгоритма.drawio, PNG-файлы листов (если установлен draw.io) и metrics.json.

Каждому блоку схемы соответствует один оператор программы. Циклы for изображены
с инициализацией, проверкой и изменением переменной цикла, оператор match –
вложенными друг в друга символами «Решение». Номера блоков – номера вершин графа.
"""
import html
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageFont

DRAWIO = Path('/Applications/draw.io.app/Contents/MacOS/draw.io')
HERE = Path(__file__).parent

FONT_SIZE = 13
FONT = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', FONT_SIZE)
GAP = 26         # расстояние между последовательными блоками
TURN = 10        # отступ линии от нижней границы блока перед поворотом
SIDE = 16        # отступ боковых линий от блоков
COL_GAP = 56     # расстояние между колонками листа

BASE_STYLE = f'whiteSpace=wrap;html=1;fontFamily=Arial;fontSize={FONT_SIZE};strokeWidth=1;fillColor=#FFFFFF;strokeColor=#000000;fontColor=#000000;'
SHAPE_STYLE = {
    'proc': 'rounded=0;',
    'term': 'rounded=1;arcSize=50;',
    'dec': 'rhombus;',
    'conn': 'ellipse;aspect=fixed;',
}
EDGE_STYLE = 'edgeStyle=none;rounded=0;html=1;strokeWidth=1;strokeColor=#000000;endSize=6;'
LABEL_STYLE = 'text;html=1;fontFamily=Arial;fontSize=12;align=left;verticalAlign=middle;fillColor=none;strokeColor=none;'
NUMBER_STYLE = 'text;html=1;fontFamily=Arial;fontSize=11;align=left;verticalAlign=bottom;fillColor=none;strokeColor=none;fontColor=#000000;'


def text_width(text):
    return max(FONT.getlength(line) for line in text.split('\n'))


class Diagram:
    def __init__(self):
        self.cells = []
        self.count = 0

    def new_id(self):
        self.count += 1
        return f'c{self.count}'

    def vertex(self, kind, text, x, y, w, h):
        cid = self.new_id()
        value = '<br>'.join(html.escape(line, quote=False) for line in text.split('\n'))
        self.cells.append(
            f'<mxCell id="{cid}" value="{html.escape(value)}" style="{SHAPE_STYLE[kind]}{BASE_STYLE}" vertex="1" parent="1">'
            f'<mxGeometry x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" as="geometry"/></mxCell>')
        return cid

    def text(self, text, x, y, style=LABEL_STYLE, w=30, h=16):
        cid = self.new_id()
        self.cells.append(
            f'<mxCell id="{cid}" value="{text}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x:.0f}" y="{y:.0f}" width="{w}" height="{h}" as="geometry"/></mxCell>')

    def label(self, text, x, y):
        self.text(text, x, y)

    def edge(self, src, dst, points=(), arrow=True):
        """src/dst – порт: ('cell', id, fx, fy, x, y) или ('pt', x, y).

        src может быть незавершённой линией ('path', порт, изломы): тогда она продолжается
        одной линией до dst, и на её изломах стрелок нет.
        """
        if src[0] == 'path':
            src, points = src[1], list(src[2]) + list(points)
        cid = self.new_id()
        style = EDGE_STYLE + ('endArrow=block;endFill=1;' if arrow else 'endArrow=none;')
        attrs = ''
        geom = ''
        if src[0] == 'cell':
            style += f'exitX={src[2]};exitY={src[3]};exitDx=0;exitDy=0;'
            attrs += f' source="{src[1]}"'
        else:
            geom += f'<mxPoint x="{src[1]:.0f}" y="{src[2]:.0f}" as="sourcePoint"/>'
        if dst[0] == 'cell':
            style += f'entryX={dst[2]};entryY={dst[3]};entryDx=0;entryDy=0;'
            attrs += f' target="{dst[1]}"'
        else:
            geom += f'<mxPoint x="{dst[1]:.0f}" y="{dst[2]:.0f}" as="targetPoint"/>'
        if points:
            geom += '<Array as="points">' + ''.join(
                f'<mxPoint x="{px:.0f}" y="{py:.0f}"/>' for px, py in points) + '</Array>'
        self.cells.append(
            f'<mxCell id="{cid}" style="{style}" edge="1" parent="1"{attrs}>'
            f'<mxGeometry relative="1" as="geometry">{geom}</mxGeometry></mxCell>')


class Graph:
    """Управляющий граф программы: вершины – блоки схемы (кроме соединителей)."""

    def __init__(self):
        self.blocks = []
        self.succ = {}

    def add(self, block):
        self.blocks.append(block)
        block.num = len(self.blocks)
        self.succ[block.num] = []
        return block.num

    def link(self, a, b):
        if b not in self.succ[a]:
            self.succ[a].append(b)


def point(x, y):
    return ('pt', x, y)


class Block:
    """Одиночный символ: процесс, терминатор, решение, соединитель."""

    def __init__(self, kind, text):
        self.kind = kind
        self.text = text
        self.num = None

    def measure(self):
        lines = self.text.count('\n') + 1
        tw = text_width(self.text)
        if self.kind == 'conn':
            self.w = self.h = 30
        elif self.kind == 'dec':
            self.w = max(130, (tw + 18) / 0.72)
            self.h = 60 + 16 * (lines - 1)
        elif self.kind == 'term':
            self.w, self.h = max(110, tw + 40), 36
        else:
            self.w, self.h = max(130, tw + 24), 20 + 16 * lines
        self.w = 2 * round(self.w / 2)
        self.wl = self.wr = self.w / 2

    def graph(self, g):
        if self.kind == 'conn':
            return None  # соединитель – разрыв линии, а не вершина графа
        v = g.add(self)
        return v, [v]

    def place(self, d, x, y):
        self.x, self.y = x, y
        self.id = d.vertex(self.kind, self.text, x - self.w / 2, y, self.w, self.h)
        if self.num is not None:
            # Номер символа по ГОСТ 19.701-90 – слева над символом (у «Решения» – в углу габарита).
            ny = y + 1 if self.kind == 'dec' else y - 15
            d.text(str(self.num), x - self.w / 2 + (4 if self.kind == 'dec' else 0), ny, NUMBER_STYLE, 26, 14)
        return self.port(0.5, 0), self.port(0.5, 1)

    def port(self, fx, fy):
        return ('cell', self.id, fx, fy, self.x - self.w / 2 + fx * self.w, self.y + fy * self.h)


def P(text):
    return Block('proc', text)


def to_node(item):
    if isinstance(item, str):
        return P(item)
    if isinstance(item, list):
        return Seq(item)
    return item


class Seq:
    def __init__(self, items):
        self.items = [to_node(i) for i in items]

    def graph(self, g):
        entry = exits = None
        for it in self.items:
            r = it.graph(g)
            if r is None:
                continue
            e, xs = r
            if exits is None:
                entry = e
            else:
                for x in exits:
                    g.link(x, e)
            exits = xs
        return None if entry is None else (entry, exits)

    def measure(self):
        for it in self.items:
            it.measure()
        self.wl = max(it.wl for it in self.items)
        self.wr = max(it.wr for it in self.items)
        self.h = sum(it.h for it in self.items) + GAP * (len(self.items) - 1)

    def place(self, d, x, y):
        entry = prev_exit = None
        for it in self.items:
            e, x_ = it.place(d, x, y)
            if prev_exit is None:
                entry = e
            else:
                d.edge(prev_exit, e)
            prev_exit = x_
            y += it.h + GAP
        return entry, prev_exit


class IfChain:
    """if / elif / else и match/case: условия друг под другом, ветвь «нет» обходит справа."""

    def __init__(self, branches, else_body=None):
        self.branches = [(Block('dec', c), to_node(b)) for c, b in branches]
        self.else_body = to_node(else_body) if else_body is not None else None

    def graph(self, g):
        entry = prev = None
        exits = []
        for dec, body in self.branches:
            d = g.add(dec)
            if prev is None:
                entry = d
            else:
                g.link(prev, d)
            be, bx = body.graph(g)
            g.link(d, be)
            exits += bx
            prev = d
        if self.else_body:
            ee, ex = self.else_body.graph(g)
            g.link(prev, ee)
            exits += ex
        else:
            exits.append(prev)
        return entry, exits

    def measure(self):
        parts = [p for br in self.branches for p in br] + ([self.else_body] if self.else_body else [])
        for p in parts:
            p.measure()
        self.has_rail = len(self.branches) > 1 or self.else_body is not None
        self.rail = max(p.wl for p in parts) + SIDE
        self.wl = self.rail + 2 if self.has_rail else max(p.wl for p in parts)
        self.right = [max(dec.wr, body.wr) + SIDE for dec, body in self.branches]
        self.wr = max(self.right + ([self.else_body.wr] if self.else_body else [])) + 2

        y = 0
        self.rows = []
        for i, (dec, body) in enumerate(self.branches):
            last = i == len(self.branches) - 1 and self.else_body is None
            y_dec, y_body = y, y + dec.h + GAP
            y_end = y_body + body.h
            if last:
                self.rows.append((y_dec, y_body, None, None))
                self.y_merge = y_end + 18
                # Слева вливаются линии других ветвей, справа – «нет»: точки стыков разнесены.
                self.y_join = self.y_merge + (12 if self.has_rail else 0)
            else:
                y_turn, y_back = y_end + TURN, y_end + TURN + 12
                self.rows.append((y_dec, y_body, y_turn, y_back))
                y = y_back + 22
        if self.else_body:
            self.y_else = y
            self.y_merge = y + self.else_body.h + 18
            self.y_join = self.y_merge
        self.h = self.y_join

    def place(self, d, x, y):
        merge = point(x, y + self.y_merge)
        join = point(x, y + self.y_join)
        rail = x - self.rail
        entry = None
        pending_no = None
        for (dec, body), (y_dec, y_body, y_turn, y_back), right in zip(self.branches, self.rows, self.right):
            de, _ = dec.place(d, x, y + y_dec)
            if entry is None:
                entry = de
            if pending_no:
                d.edge(pending_no[0], de, pending_no[1])
            be, bx = body.place(d, x, y + y_body)
            d.edge(dec.port(0.5, 1), be)
            d.label('да', x + 4, y + y_dec + dec.h)
            d.label('нет', x + dec.w / 2 + 2, y + y_dec + dec.h / 2 - 16)
            cy = y + y_dec + dec.h / 2
            if y_turn is None:
                d.edge(bx, join, arrow=False)
                d.edge(dec.port(1, 0.5), join, [(x + right, cy), (x + right, y + self.y_join)])
            else:
                d.edge(bx, merge, [(x, y + y_turn), (rail, y + y_turn), (rail, y + self.y_merge)])
                pending_no = (dec.port(1, 0.5), [(x + right, cy), (x + right, y + y_back), (x, y + y_back)])
        if self.else_body:
            ee, ex = self.else_body.place(d, x, y + self.y_else)
            d.edge(pending_no[0], ee, pending_no[1])
            d.edge(ex, merge, arrow=False)
        return entry, join


class IfSide:
    """if-else с ветвями по обе стороны от символа «Решение»."""

    def __init__(self, cond, yes, no):
        self.dec = Block('dec', cond)
        self.yes = to_node(yes)
        self.no = to_node(no)

    def graph(self, g):
        d = g.add(self.dec)
        ye, yx = self.yes.graph(g)
        ne, nx = self.no.graph(g)
        g.link(d, ye)
        g.link(d, ne)
        return d, yx + nx

    def measure(self):
        for p in (self.dec, self.yes, self.no):
            p.measure()
        self.ha = max(self.dec.w / 2, self.yes.wr + 12)
        self.hb = max(self.dec.w / 2, self.no.wl + 12)
        self.wl = self.ha + self.yes.wl
        self.wr = self.hb + self.no.wr
        self.y_merge = self.dec.h + GAP + max(self.yes.h, self.no.h) + 18
        self.y_join = self.y_merge + 12
        self.h = self.y_join

    def place(self, d, x, y):
        de, _ = self.dec.place(d, x, y)
        cy = y + self.dec.h / 2
        top = y + self.dec.h + GAP
        ye, yx = self.yes.place(d, x - self.ha, top)
        ne, nx = self.no.place(d, x + self.hb, top)
        d.edge(self.dec.port(0, 0.5), ye, [(x - self.ha, cy)])
        d.edge(self.dec.port(1, 0.5), ne, [(x + self.hb, cy)])
        d.edge(nx, point(x, y + self.y_join), [(x + self.hb, y + self.y_join)])
        out = ('path', yx, [(x - self.ha, y + self.y_merge), (x, y + self.y_merge)])
        d.label('да', x - self.dec.w / 2 - 22, cy - 16)
        d.label('нет', x + self.dec.w / 2 + 2, cy - 16)
        return de, out


class While:
    """Цикл с предусловием: «Решение» и линия возврата слева."""

    TOP = 18

    def __init__(self, cond, body):
        self.dec = Block('dec', cond)
        self.body = to_node(body)

    def graph(self, g):
        d = g.add(self.dec)
        be, bx = self.body.graph(g)
        g.link(d, be)
        for x in bx:
            g.link(x, d)
        return d, [d]

    def measure(self):
        self.dec.measure()
        self.body.measure()
        self.left = max(self.dec.wl, self.body.wl) + SIDE
        self.right = max(self.dec.wr, self.body.wr) + SIDE
        self.wl, self.wr = self.left + 2, self.right + 2
        self.y_body = self.TOP + self.dec.h + GAP
        self.y_back = self.y_body + self.body.h + TURN
        self.y_exit = self.y_back + 14
        self.h = self.y_exit

    def place(self, d, x, y):
        de, _ = self.dec.place(d, x, y + self.TOP)
        be, bx = self.body.place(d, x, y + self.y_body)
        d.edge(self.dec.port(0.5, 1), be)
        d.label('да', x + 4, y + self.TOP + self.dec.h)
        d.label('нет', x + self.dec.w / 2 + 2, y + self.TOP + self.dec.h / 2 - 16)
        join = y + 6
        d.edge(bx, point(x, join), [(x, y + self.y_back), (x - self.left, y + self.y_back), (x - self.left, join)])
        cy = y + self.TOP + self.dec.h / 2
        out = ('path', self.dec.port(1, 0.5), [(x + self.right, cy), (x + self.right, y + self.y_exit),
                                               (x, y + self.y_exit)])
        return de, out


def For(var, stop, body):
    """for var in range(stop): инициализация, проверка и изменение переменной цикла."""
    return Seq([f'{var} = 0', While(f'{var} < {stop}', [*body, f'{var} += 1'])])


def Conn(label):
    return Block('conn', str(label))


class Detach:
    """Фрагмент, перенесённый в другую колонку: здесь – соединитель-выход и соединитель-возврат.

    В графе фрагмент стоит на своём месте (нумерация идёт по порядку операторов),
    а рисуется в отдельной колонке через Detach.column().
    """

    def __init__(self, out_label, in_label, content):
        self.a, self.b = Conn(out_label), Conn(in_label)
        self.content = to_node(content)

    def graph(self, g):
        return self.content.graph(g)

    def column(self):
        return Seq([Conn(self.a.text), _Drawn(self.content), Conn(self.b.text)])

    def measure(self):
        self.a.measure()
        self.b.measure()
        self.wl = self.wr = 15
        self.h = 30 + 22 + 30

    def place(self, d, x, y):
        entry, _ = self.a.place(d, x, y)
        _, exit_ = self.b.place(d, x, y + 52)
        return entry, exit_


class _Drawn:
    """Обёртка для рисования фрагмента без повторного добавления его вершин в граф."""

    def __init__(self, node):
        self.node = node

    def graph(self, g):
        return None

    def measure(self):
        self.node.measure()
        self.wl, self.wr, self.h = self.node.wl, self.node.wr, self.node.h

    def place(self, d, x, y):
        return self.node.place(d, x, y)


# ---------------------------------------------------------------- схема ---

INNER_LOOP = Detach(1, 2, For('j', 'cols', [
    'value = table[i][j]',
    IfChain([('value > 0', 'positive += 1'),
             ('value < 0', 'negative += 1')]),
    'total += value',
]))

SHEETS = [
    [
        Seq([
            Block('term', 'Начало'),
            'rows = len(table)',
            'total = 0',
            'positive = 0',
            'negative = 0',
            For('i', 'rows', [
                'cols = len(table[i])',
                INNER_LOOP,
            ]),
            Conn(3),
        ]),
        INNER_LOOP.column(),
    ],
    [
        Seq([
            Conn(3),
            'rest = abs(total)',
            'steps = 0',
            While('rest > limit', ['rest //= 2', 'steps += 1']),
            IfChain([('steps % 3 == 0', 'bonus = 10'),
                     ('steps % 3 == 1', 'bonus = 5')], 'bonus = 0'),
            Conn(4),
        ]),
        Seq([
            Conn(4),
            For('k', 'steps', [
                IfChain([('k % 2 == 0', 'bonus += k')]),
            ]),
            IfSide('positive > negative', 'result = total + bonus', 'result = total - bonus'),
            'return result',
            Block('term', 'Конец'),
        ]),
    ],
]

# Порядок вершин графа – порядок операторов программы (перенесённый фрагмент – на своём месте).
PROGRAM = [SHEETS[0][0], SHEETS[1][0], SHEETS[1][1]]


# ------------------------------------------------ метрика граничных значений ---

def boundary_metric(g):
    """Скорректированные сложности вершин графа по метрике граничных значений."""
    n = len(g.blocks)
    verts = list(range(1, n + 1))
    end = [v for v in verts if not g.succ[v]]
    assert len(end) == 1, 'граф должен иметь единственную конечную вершину'
    end = end[0]
    # Постдоминаторы: pdom(v) = {v} ∪ ⋂ pdom(s) по всем преемникам s.
    pdom = {v: set(verts) for v in verts}
    pdom[end] = {end}
    changed = True
    while changed:
        changed = False
        for v in verts:
            if v == end:
                continue
            new = {v} | set.intersection(*(pdom[s] for s in g.succ[v]))
            if new != pdom[v]:
                pdom[v], changed = new, True

    def ipdom(v):
        strict = pdom[v] - {v}
        # Ближайший постдоминатор – тот, которого постдоминируют все остальные.
        return next(p for p in strict if strict <= pdom[p])

    rows = []
    complexity = {}
    for v in verts:
        if v == end:
            complexity[v] = 0
        elif len(g.succ[v]) <= 1:
            complexity[v] = 1
        else:
            low = ipdom(v)
            seen, stack = set(), list(g.succ[v])
            while stack:
                u = stack.pop()
                if u == low or u in seen:
                    continue
                seen.add(u)
                stack.extend(g.succ[u])
            complexity[v] = len(seen) + 1  # вершины подграфа и нижняя граница
            rows.append({'vertex': v, 'text': g.blocks[v - 1].text, 'succ': sorted(g.succ[v]),
                         'complexity': complexity[v], 'subgraph': sorted(seen), 'lower': low})
    sa = sum(complexity.values())
    return {'v': n, 'Sa': sa, 'So': 1 - (n - 1) / sa, 'selection': rows,
            'complexity': [complexity[v] for v in verts],
            'blocks': [{'num': b.num, 'kind': b.kind, 'text': b.text} for b in g.blocks]}


def check_method_examples():
    """Проверка расчёта на схемах из методички (рис. 1, 2, 3): Sa = 10, 14, 32."""
    examples = {
        10: {1: [2], 2: [3, 4], 3: [2], 4: [5, 6], 5: [7], 6: [7], 7: []},
        14: {1: [2], 2: [3], 3: [4, 5, 6, 7, 8], 4: [9], 5: [9], 6: [9], 7: [9], 8: [9], 9: [10], 10: []},
        32: {1: [2], 2: [3], 3: [4, 5], 4: [12], 5: [6, 7], 6: [12], 7: [8, 9], 8: [12], 9: [10, 11],
             10: [12], 11: [12], 12: [13], 13: []},
    }
    for expected, succ in examples.items():
        g = Graph()
        g.blocks = [Block('proc', str(v)) for v in succ]
        g.succ = succ
        assert boundary_metric(g)['Sa'] == expected, expected


# ------------------------------------------------------------------ сборка ---

def build_sheet(columns):
    d = Diagram()
    x = 20
    height = 0
    for col in columns:
        col.measure()
        axis = round(x + col.wl)
        col.place(d, axis, 30)
        x = axis + col.wr + COL_GAP
        height = max(height, col.h)
    return d, x - COL_GAP + 20, height + 50


def main():
    check_method_examples()
    g = Graph()
    Seq(PROGRAM).graph(g)
    metric = boundary_metric(g)
    (HERE / 'metrics.json').write_text(json.dumps(metric, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"v = {metric['v']}, вершин выбора = {len(metric['selection'])}, "
          f"Sa = {metric['Sa']}, So = {metric['So']:.4f}")

    pages = []
    for idx, cols in enumerate(SHEETS, start=1):
        d, w, h = build_sheet(cols)
        pages.append(
            f'<diagram id="sheet{idx}" name="Лист {idx}">'
            f'<mxGraphModel dx="{w:.0f}" dy="{h:.0f}" grid="0" gridSize="10" guides="1" tooltips="1" connect="1" '
            f'arrows="1" fold="1" page="1" pageScale="1" pageWidth="{w:.0f}" pageHeight="{h:.0f}" math="0" shadow="0">'
            f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>{"".join(d.cells)}</root></mxGraphModel></diagram>')
        print(f'Лист {idx}: {w:.0f} x {h:.0f}')
    out = HERE / 'Схема_алгоритма.drawio'
    out.write_text('<mxfile host="drawio" type="device">' + ''.join(pages) + '</mxfile>', encoding='utf-8')
    print('saved', out)
    if DRAWIO.exists():
        export_png(out, len(pages))


def export_png(drawio_file, page_count):
    sheets = []
    for idx in range(1, page_count + 1):
        png = drawio_file.with_name(f'Схема_алгоритма_лист{idx}.png')
        subprocess.run([str(DRAWIO), '--export', '--format', 'png', '--scale', '2', '--border', '10',
                        '--page-index', str(idx), '--output', str(png), str(drawio_file)],
                       check=True, capture_output=True)
        sheets.append(Image.open(png).convert('RGB'))
        print('saved', png)
    gap = 60
    width = max(im.width for im in sheets)
    combined = Image.new('RGB', (width, sum(im.height for im in sheets) + gap * (len(sheets) - 1)), 'white')
    y = 0
    for im in sheets:
        combined.paste(im, (0, y))
        y += im.height + gap
    target = drawio_file.with_name('Схема_алгоритма.png')
    combined.save(target)
    print('saved', target)


if __name__ == '__main__':
    main()
