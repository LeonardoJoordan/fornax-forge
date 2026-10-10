"""Etapa 03: PDF/PNG independentes e comparação com o protótipo isolado."""
from copy import deepcopy
from hashlib import sha256
import argparse
import gc
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(Path(__file__).parent)]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_SCALE_FACTOR','1')

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication
from pypdf import PdfReader
from core.ui_font import install_ui_font,UI_FONT_FAMILY
from core.model_document import adapt_model_page
from core.table_layout import TableLayout
from features.generator.renderer import NativeRenderer
from table_fixtures import table_spec
from table_layout_prototype import FixedTableLayout,render_image
from table_document_fixtures import document_from_spec
from table_render_evidence import document,vector_pdf
from run_table_prototype import distribution,ink_bbox,rss


def paint_image(layout,scale=.25):
    image=QImage(math.ceil((layout.width+48)*scale),math.ceil((layout.height+48)*scale),QImage.Format.Format_ARGB32)
    image.setDotsPerMeterX(round(300*scale/.0254));image.setDotsPerMeterY(round(300*scale/.0254))
    image.fill(Qt.GlobalColor.white)
    painter=QPainter(image)
    try:
        painter.scale(scale,scale);painter.translate(24,24);layout.paint(painter)
    finally:painter.end()
    return image


def measure(factory,painter):
    retained=factory();painter(retained);gc.collect()
    memory_before=rss();data={}
    for name in ('build_and_first_paint','paint_existing'):
        times=[]
        for index in range(22):
            begin=time.perf_counter()
            layout=factory() if name=='build_and_first_paint' else retained
            image=painter(layout)
            elapsed=(time.perf_counter()-begin)*1000
            assert not image.isNull()
            if index>=2:times.append(elapsed)
            if name=='build_and_first_paint':del layout
            del image
        data[name]=distribution(times)
    return dict(operations=data,rss_with_layout_bytes=memory_before,rss_end_bytes=rss())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output;output.mkdir(parents=True,exist_ok=True)
    app=QApplication([]);install_ui_font(app)
    errors=[]
    def exception_hook(typ,value,tb):
        errors.append(str(value))
        sys.__excepthook__(typ,value,tb)
    sys.excepthook=exception_hook
    source=document();renderer=NativeRenderer(adapt_model_page(source))
    values={'nome':'Ana','nota':'9'}
    original=renderer.render_to_qimage(values,values)
    assert original.save(str(output/'tabela-300dpi.png'))
    vector_pdf(renderer,output/'tabela-vetorial.pdf',values)
    subprocess.run(['pdftoppm','-r','300','-png','-singlefile',str(output/'tabela-vetorial.pdf'),
                    str(output/'pdf-300dpi')],capture_output=True,check=True)
    page=PdfReader(output/'tabela-vetorial.pdf').pages[0]
    assert len(page.images)==0
    pdf=QImage(str(output/'pdf-300dpi.png'))
    boxes=[];layout=TableLayout(source['pages'][0]['tables'][0],values)
    for cell in layout.cells:
        area=cell.inner.translated(layout.table['x'],layout.table['y'])
        png_box=ink_bbox(original,area,cell.style['fill_color'])
        pdf_box=ink_bbox(pdf,area,cell.style['fill_color'])
        assert png_box is not None and pdf_box is not None
        delta=max(abs(a-b) for a,b in zip(png_box,pdf_box))
        assert delta<=3,(cell.cell['id'],png_box,pdf_box)
        boxes.append(dict(anchor=[cell.cell['row'],cell.cell['column']],png=png_box,pdf=pdf_box,delta_px=delta))
    dense=table_spec('densa',40,20)
    dense.update(default_font=UI_FONT_FAMILY,default_font_size_pt=7,padding_mm=.5)
    for cell in dense['cells']:cell['html']=f'<p><b>{cell["row"]+1}</b>/{cell["column"]+1}</p>'
    converted=document_from_spec({'id':'densa','pages':[{'page':'front','tables':[dense]}]})
    table=converted['pages'][0]['tables'][0]
    initial=deepcopy(table)
    baseline=measure(lambda:FixedTableLayout(dense),lambda layout:render_image(layout,.25))
    actual=measure(lambda:TableLayout(table),paint_image)
    assert table==initial
    assert len(TableLayout(table).cells)==800
    paths=['core/table_layout.py','core/table_text.py','core/table_paint.py',
           'features/generator/renderer.py','tests/performance/run_table_render_evidence.py']
    result=dict(python=sys.version,platform=platform.platform(),logical_dpi=300,qt_scale=os.environ['QT_SCALE_FACTOR'],
                pdf=dict(page_points=[float(page.mediabox.width),float(page.mediabox.height)],
                         expected_points=[360,206.4],text=page.extract_text(),text_boxes=boxes,raster_images=0),
                benchmark=dict(cells=800,rows=40,columns=20,warmups=2,samples=20,
                    baseline_prototype=baseline,production=actual,input_sha256=sha256(json.dumps(dense,sort_keys=True).encode()).hexdigest()),
                source_hashes={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in paths},callback_errors=errors)
    (output/'evidencias.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert not errors,errors
    print(json.dumps(dict(pdf_max_delta=max(box['delta_px'] for box in boxes),
        benchmark={name:{operation:{key:measure[key] for key in ('median_ms','p95_ms')}
                        for operation,measure in result['benchmark'][name]['operations'].items()}
                   for name in ('baseline_prototype','production')}),indent=2))


if __name__=='__main__':main()
