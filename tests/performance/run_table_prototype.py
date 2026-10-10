"""Etapa 01: candidato Qt, PDF vetorial, escalas e referência de 800 células.

Executar em Qt offscreen; --output recebe apenas evidências locais. Não abre,
salva ou altera modelos da biblioteca nem modifica o editor do produto.
"""
import argparse
from copy import deepcopy
import gc
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_SCALE_FACTOR', '1')

from PySide6.QtCore import QMarginsF, QSizeF, QRectF, Qt
from PySide6.QtGui import QPainter, QPdfWriter, QPageSize, QTextCursor, QImage
from PySide6.QtWidgets import QApplication, QGraphicsScene
from core.html_utils import TextOnlyDocument
from core.ui_font import install_ui_font
from core.organogram import UNITS_PER_MM
from table_layout_prototype import (
    FixedTableLayout, PrototypeTableItem, native_qtexttable, render_image, specimen, logical_device,
)
from table_fixtures import table_spec


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def distribution(samples):
    ordered = sorted(samples)
    position = (len(samples)-1)*.95
    index, fraction = int(position), position % 1
    return dict(samples_ms=samples, median_ms=statistics.median(samples),
                p95_ms=ordered[index]+fraction*(ordered[min(index+1,len(samples)-1)]-ordered[index]),
                stdev_ms=statistics.pstdev(samples))


def rss():
    return int(Path('/proc/self/statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')


def candidate_evidence(data):
    observations = {}
    for fixed in (False, True):
        for long in (False, True):
            spec = deepcopy(data)
            spec['cells'][1]['html'] = '<p>' + '<br>'.join(['Texto longo']*(40 if long else 1)) + '</p>'
            doc, table, device = native_qtexttable(spec, fixed_height=fixed)
            doc.size()
            bounds = doc.documentLayout().frameBoundingRect(table)
            block = table.cellAt(1, 0).firstCursorPosition().block()
            text = doc.documentLayout().blockBoundingRect(block)
            observations[f'{"fixa" if fixed else "automatica"}-{ "longo" if long else "curto"}'] = dict(
                frame=[bounds.x(), bounds.y(), bounds.width(), bounds.height()],
                first_content_rect=[text.x(), text.y(), text.width(), text.height()],
                document_height=doc.size().height())
    doc, table, device = native_qtexttable(data)
    html = doc.toHtml()
    other_device = logical_device()
    other = TextOnlyDocument()
    other.documentLayout().setPaintDevice(other_device)
    other.setDefaultFont(doc.defaultFont())
    other.setDocumentMargin(0)
    other.setHtml(html)
    other.setTextWidth(doc.textWidth())
    cursor = other.find('FORNAX')
    reloaded = cursor.currentTable()
    assert reloaded is not None
    title = reloaded.cellAt(0, 0)
    anchor = title.firstCursorPosition()
    anchor.movePosition(QTextCursor.MoveOperation.NextCharacter)
    observations['html_roundtrip'] = dict(
        plain_text_equal=doc.toPlainText() == other.toPlainText(),
        title_span=[title.rowSpan(), title.columnSpan()],
        title_fill=title.format().background().color().name(),
        title_text_color=anchor.charFormat().foreground().color().name(),
        title_weight=anchor.charFormat().fontWeight(),
        document_before=[doc.size().width(),doc.size().height()],
        document_after=[other.size().width(),other.size().height()],
    )
    assert observations['automatica-longo']['document_height'] > observations['automatica-curto']['document_height']+1000
    assert observations['html_roundtrip']['plain_text_equal']
    assert observations['html_roundtrip']['title_span'] == [1, 4]
    assert observations['html_roundtrip']['title_weight'] > 400
    assert observations['html_roundtrip']['title_text_color'] == '#ffffff'
    return observations


def export_pdf(layout, path, margin=24):
    writer = QPdfWriter(str(path))
    writer.setResolution(300)
    writer.setPageSize(QPageSize(
        QSizeF((layout.width+2*margin)/UNITS_PER_MM, (layout.height+2*margin)/UNITS_PER_MM),
        QPageSize.Unit.Millimeter, '', QPageSize.SizeMatchPolicy.ExactMatch))
    writer.setPageMargins(QMarginsF(0, 0, 0, 0))
    painter = QPainter(writer)
    if not painter.isActive():
        raise RuntimeError('PDF não abriu')
    try:
        # Alinhar a área física da página; arredondamento do dispositivo <1 px.
        painter.scale(writer.width()/(layout.width+2*margin),
                      writer.height()/(layout.height+2*margin))
        painter.translate(margin, margin)
        layout.paint(painter)
    finally:
        painter.end()


def ink_bbox(image, rect, fill):
    from PySide6.QtGui import QColor
    background = QColor(fill)
    expected = background.red(), background.green(), background.blue()
    left, top, right, bottom = image.width(), image.height(), -1, -1
    for y in range(max(0,math.ceil(rect.top())+1), min(image.height(),math.floor(rect.bottom())-1)):
        for x in range(max(0,math.ceil(rect.left())+1), min(image.width(),math.floor(rect.right())-1)):
            color = image.pixelColor(x, y)
            if sum(abs(a-b) for a,b in zip((color.red(),color.green(),color.blue()),expected)) > 160:
                left, top, right, bottom = min(left,x), min(top,y), max(right,x), max(bottom,y)
    return [left,top,right,bottom] if right >= 0 else None


def pdf_evidence(layout, output):
    from pypdf import PdfReader
    export_pdf(layout, output/'prototipo.pdf')
    process = subprocess.run(['pdftoppm','-r','300','-png','-singlefile',
                              str(output/'prototipo.pdf'),str(output/'pdf-300dpi')],
                             capture_output=True,text=True,check=True)
    page = PdfReader(output/'prototipo.pdf').pages[0]
    expected = [(layout.width+48)/UNITS_PER_MM*72/25.4,
                (layout.height+48)/UNITS_PER_MM*72/25.4]
    actual = [float(page.mediabox.width),float(page.mediabox.height)]
    # QPageSize/QPdfWriter quantizam o MediaBox em pontos inteiros, mesmo com
    # ExactMatch. Registrar o erro, até meio ponto (0,176 mm), sem chamá-lo zero.
    assert all(abs(a-b) <= .5 for a,b in zip(expected,actual)), (expected,actual)
    text = page.extract_text()
    for required in ('FORNAX', '{nome}', 'Centralizado', 'mesclada'):
        assert required in text, (required,text)
    image = QImage(str(output/'pdf-300dpi.png'))
    assert not image.isNull()
    direct = render_image(layout)
    boxes = []
    for entry in layout.cells:
        area = entry.inner.translated(24,24)
        expected_box = ink_bbox(direct, area, entry.spec['fill'])
        actual_box = ink_bbox(image, area, entry.spec['fill'])
        assert actual_box is not None and expected_box is not None
        delta = max(abs(a-b) for a,b in zip(expected_box,actual_box))
        assert delta <= 2, (entry.spec['key'],expected_box,actual_box)
        boxes.append(dict(cell=entry.spec['key'],png=expected_box,pdf=actual_box,max_delta_px=delta))
    # Conferir cada fronteira por cor no rasterizador independente, não apenas
    # comparar dois chamadores da mesma função de pintura.
    from PySide6.QtGui import QColor
    border = QColor(layout.data['outline']['color'])
    probes = []
    for x in layout.x:
        probes.append((x+24, (layout.y[1]+layout.y[2])/2+24))
    for y in layout.y:
        probes.append((layout.x[0]+layout.padding/2+24, y+24))
    for x,y in probes:
        matches = [image.pixelColor(px,py) for px in range(round(x)-2,round(x)+3)
                   for py in range(round(y)-2,round(y)+3)]
        assert any(sum(abs(a-b) for a,b in zip((c.red(),c.green(),c.blue()),
                                              (border.red(),border.green(),border.blue())))<30
                   for c in matches), (x,y)
    return dict(page_points=actual,expected_page_points=expected,
                page_rounding_mm=[(a-b)*25.4/72 for a,b in zip(actual,expected)],
                text_required_present=True, borders_checked=len(probes),
                text_boxes=boxes, poppler_stderr=process.stderr,
                tolerance='Até 2 pixels a 300 DPI (0,17 mm); geometria/linhas verificadas à parte.')


def measurements(output, samples):
    dense = table_spec('densa',40,20)
    for entry in dense['cells']:
        entry['html'] = f'<p><b>{entry["row"]+1}</b>/{entry["column"]+1}</p>'
    dense['default_font_size_pt'] = 7
    dense['padding_mm'] = .5
    before = rss()
    warm = FixedTableLayout(dense)
    render_image(warm,.25)
    gc.collect()
    after = rss()
    evidence = dict(cells=800,rows=40,columns=20,documents=warm.build_count,
                    width_mm=warm.width/UNITS_PER_MM,height_mm=warm.height/UNITS_PER_MM,
                    rss_before_bytes=before,rss_with_layout_bytes=after,
                    overflow_cells=sum(e.overflow_x or e.overflow_y for e in warm.cells),
                    image_scale=.25,samples=samples,operations={})
    for operation in ('build_and_first_paint','paint_existing','select_interval'):
        times = []
        for index in range(samples+2):
            begin = time.perf_counter()
            if operation == 'build_and_first_paint':
                layout = FixedTableLayout(dense)
                image = render_image(layout,.25)
                assert layout.build_count == 800 and not image.isNull()
            elif operation == 'paint_existing':
                image = render_image(warm,.25)
                assert not image.isNull()
            else:
                area = warm.selection((5,5),(35,18))
                assert area.width() > 0
            elapsed = (time.perf_counter()-begin)*1000
            if index >= 2:
                times.append(elapsed)
            if operation == 'build_and_first_paint':
                del layout,image
        evidence['operations'][operation] = distribution(times)
    assert warm.build_count == 800
    evidence['rss_end_bytes'] = rss()
    write(output/'medicoes-800-celulas.json',evidence)
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=20)
    args = parser.parse_args()
    if args.samples < 20:
        parser.error('A rodada de referência exige pelo menos vinte amostras.')
    output = args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    app = QApplication.instance() or QApplication([])
    family = install_ui_font(app)
    errors = []
    previous_hook = sys.excepthook
    sys.excepthook = lambda kind,value,trace: errors.append(f'{kind.__name__}: {value}')
    try:
        data = specimen()
        layout = FixedTableLayout(data)
        identity = dict(python=sys.version,pyside=__import__('PySide6').__version__,
                        platform=platform.platform(),font=family,qt_backend=os.environ['QT_QPA_PLATFORM'],
                        screen_scale=os.environ['QT_SCALE_FACTOR'],logical_dpi=300,
                        units_per_mm=UNITS_PER_MM,
                        input_sha256=sha256(json.dumps(data,sort_keys=True).encode()).hexdigest(),
                        instruments={str(path.relative_to(ROOT)):sha256(path.read_bytes()).hexdigest()
                                     for path in (Path(__file__),ROOT/'tests/performance/table_layout_prototype.py',
                                                  ROOT/'tests/test_table_layout_prototype.py')})
        write(output/'ambiente.json',identity)
        write(output/'candidato-qtexttable.json',candidate_evidence(data))
        write(output/'medidas-layout-proprio.json',layout.measurements())
        for scale in (.25,.5,1,2):
            assert render_image(layout,scale).save(str(output/f'prototipo-escala-{scale:g}.png'))
        scene = QGraphicsScene()
        item = PrototypeTableItem(layout)
        scene.addItem(item)
        item.setTransformOriginPoint(layout.width/2,layout.height/2)
        item.setRotation(30)
        bounds = scene.itemsBoundingRect().adjusted(-24,-24,24,24)
        rotated = QImage(math.ceil(bounds.width()*.5),math.ceil(bounds.height()*.5),QImage.Format.Format_ARGB32)
        rotated.fill(Qt.GlobalColor.white)
        painter = QPainter(rotated)
        try:
            scene.render(painter,QRectF(0,0,bounds.width()*.5,bounds.height()*.5),bounds)
        finally:
            painter.end()
        assert rotated.save(str(output/'canvas-rotacao-30.png'))
        print('Candidato Qt, layout e quatro escalas concluídos.',flush=True)
        write(output/'verificacao-pdf.json',pdf_evidence(layout,output))
        print('PDF conferido por Poppler e pypdf.',flush=True)
        measured = measurements(output,args.samples)
        app.processEvents()
        assert not errors, errors
        for name,result in measured['operations'].items():
            print(name,round(result['median_ms'],3),'ms',flush=True)
    finally:
        sys.excepthook = previous_hook


if __name__ == '__main__':
    main()
