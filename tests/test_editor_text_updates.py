"""Contratos de edição e fidelidade para otimizações do layout de texto."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt,QRectF,QEvent
from PySide6.QtGui import QTextCursor,QFontMetrics,QInputMethodEvent,QImage,QPainter
from PySide6.QtTest import QTest
from core.text_layout import (build_document,line_reference_ink_bounds,text_geometry,
                              resolve_rich_text,variables_in_html,REFERENCE_GLYPHS)
from core.model_document import adapt_model_page
from core.starter_templates import starter_catalog,model_from_starter
from features.editor.canvas_items import DesignerBox
from features.generator.renderer import NativeRenderer
from features.generator.tiled_document import PageTilingRenderer
import test_editor_performance_contracts as contracts
from test_text_fidelity import editor_box,editor_text_image
from text_cases import rich_sample,text_document


def reference_bounds(doc,block,line,*_):
    fonts={};c=QTextCursor(doc)
    for i in range(line.textStart(),line.textStart()+line.textLength()):
        c.setPosition(block.position()+i)
        f=c.charFormat().font().resolve(doc.defaultFont());fonts[f.toString()]=f
    if not fonts:
        f=doc.defaultFont();fonts[f.toString()]=f
    rects=[QFontMetrics(f).tightBoundingRect(REFERENCE_GLYPHS) for f in fonts.values()]
    return min(r.top() for r in rects),max(r.bottom() for r in rects)


def image_hash(image):
    return {'size':[image.width(),image.height()], 'pixels':sha256(bytes(image.constBits())).hexdigest()}


class TextUpdateBehaviorTest(unittest.TestCase):
    setUpClass=classmethod(contracts.PerformanceContractsTest.setUpClass.__func__)
    setUp=contracts.PerformanceContractsTest.setUp
    editor=contracts.PerformanceContractsTest.editor

    def editable(self,long=False):
        w=self.editor('simple',1)
        w.load_starter_document(text_document(long=long),lambda _:b'')
        w.show();w._zoom_to_fit();self.app.processEvents()
        box=next(i for i in w.scene.items() if isinstance(i,DesignerBox))
        w.canvas_edit.begin(box);self.app.processEvents()
        return w,box

    def record(self,name,data):
        output=os.environ.get('FORNAX_TEXT_EVIDENCE')
        if output:
            p=Path(output);states=json.loads(p.read_text()) if p.exists() else {}
            states[name]=json.loads(json.dumps(data,ensure_ascii=False).replace(str(self.root),'__TEST_ROOT__'))
            p.write_text(json.dumps(states,ensure_ascii=False,indent=2)+'\n')

    def record_box(self,name,box):
        data=box.text_layout_data();data.update(html=box.state.html_content,x=70,y=90,w=410,h=190,rotation=box.rotation())
        # Posição/largura fixas apenas para a comparação raster do texto renderizado.
        image=editor_text_image(data)
        doc=box.text_item.document()
        self.record(name,dict(html=box.state.html_content,rect=[box.rect().width(),box.rect().height()],
                             geometry=text_geometry(doc,box.text_layout_data()),cursor=[box.text_item.textCursor().position(),box.text_item.textCursor().anchor()],image=image_hash(image)))

    def test_fragment_metrics_match_character_reference_including_utf16_and_boundaries(self):
        samples=[rich_sample(),rich_sample(True),'<p><b>A</b><i>B</i><span style="font-size:38pt">Ç😀</span>g</p>',
                 '<p> </p><p><b> </b></p><p> fim </p>', '<p>😀𝄞é</p><p></p>',
                 '<p><span style="font-family:missing-test-font;font-size:42pt">A</span><br/>j</p>']
        for html in samples:
            for width in (48,200,1000):
                data=dict(html=html,rich_text_version=1,font_family='DejaVu Sans',font_size=16,w=width,h=500)
                doc=build_document(data,html);doc.size();block=doc.begin()
                while block.isValid():
                    layout=block.layout()
                    for n in range(layout.lineCount()):
                        line=layout.lineAt(n)
                        self.assertEqual(line_reference_ink_bounds(doc,block,line),reference_bounds(doc,block,line))
                    block=block.next()
                actual=text_geometry(doc,data)
                with patch('core.text_layout.line_reference_ink_bounds',side_effect=reference_bounds):
                    expected=text_geometry(doc,data)
                self.assertEqual(actual,expected)

    def test_typing_paste_focus_cursor_and_native_undo_keep_state_immediate(self):
        w,box=self.editable();original=box.text_item.toPlainText()
        QTest.keyClicks(w.view.viewport(),' equipe')
        self.assertIs(w.scene.focusItem(),box.text_item)
        self.assertTrue(box.text_item.toPlainText().endswith(' equipe'))
        self.assertEqual(box.state.html_content,box.text_item.toHtml())
        event=QInputMethodEvent();event.setCommitString(' 😀𝄞 ação')
        w.scene.sendEvent(box.text_item,event)
        self.assertTrue(box.text_item.toPlainText().endswith(' 😀𝄞 ação'))
        self.assertEqual(box.state.html_content,box.text_item.toHtml())
        QTest.keyClick(w.view.viewport(),Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(box.state.html_content,box.text_item.toHtml())
        QTest.keyClick(w.view.viewport(),Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier)
        self.assertTrue(box.text_item.toPlainText().endswith(' 😀𝄞 ação'))
        self.app.clipboard().setText(' colagem com acento é 😀')
        QTest.keyClick(w.view.viewport(),Qt.Key.Key_V,Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(box.text_item.toPlainText().endswith(' colagem com acento é 😀'))
        self.assertEqual(box.state.html_content,box.text_item.toHtml())
        self.assertGreater(box.text_item.textCursor().position(),len(original))
        self.record_box('typing-paste',box)

    def test_selected_format_and_editor_history_are_preserved(self):
        w,box=self.editable();before=deepcopy(w.get_current_scene_state())
        cursor=box.text_item.textCursor();cursor.select(QTextCursor.SelectionType.Document);box.text_item.setTextCursor(cursor)
        position=(cursor.position(),cursor.anchor())
        for kind,value in [('bold',True),('italic',True),('underline',True),('size',21),('family','DejaVu Serif')]:
            self.assertTrue(w.canvas_edit.format(kind,value))
            self.assertEqual(box.state.html_content,box.text_item.toHtml())
            self.assertEqual((box.text_item.textCursor().position(),box.text_item.textCursor().anchor()),position)
            self.record_box('format-'+kind,box)
        w.canvas_edit.finish();after=deepcopy(w._document_with_active_page())
        self.assertNotEqual(before,w.get_current_scene_state());w.undo();self.assertEqual(w.get_current_scene_state()['boxes'][0]['html'],before['boxes'][0]['html'])
        w.redo();restored=w._document_with_active_page()
        for old,new in zip(after['pages'][0]['boxes'],restored['pages'][0]['boxes']):
            for key in ('html','w','h','font_size','font_family','x','y'):self.assertEqual(old[key],new[key])
        self.record('format-redo',restored)

    def test_alignment_spacing_indent_rotation_and_resize_keep_fidelity(self):
        for align,vertical in [('left','top'),('center','center'),('right','bottom'),('justify','center')]:
            data=dict(html=rich_sample(),rich_text_version=1,font_family='DejaVu Sans',font_size=16,
                      x=70,y=90,w=410,h=190,align=align,vertical_align=vertical,line_height=.75,indent_px=8,rotation=12)
            box=editor_box(data);box.resize_from_handle(380,180);data.update(w=380,h=180)
            values={k:'{'+k+'}' for k in variables_in_html(data['html'])}
            renderer=NativeRenderer(dict(canvas_size=dict(w=600,h=400),boxes=[data]))
            image=editor_text_image(data)
            preview=renderer.render_preview_image(values);generated=renderer.render_to_qimage(values,values)
            self.assertEqual(preview,generated)
            self.assertEqual(image,preview)
            self.assertEqual(box.text_item.y(),text_geometry(box.text_item.document(),box.text_layout_data())[0])
            self.record('alignment-'+align,dict(data=data,geometry=text_geometry(box.text_item.document(),box.text_layout_data()),pixels=image_hash(image),preview=image_hash(preview),generated=image_hash(generated)))

    def test_placeholder_emphasis_and_preview_renew_after_font_and_width_changes(self):
        data=dict(html='<p>Olá <b><i>{nome}</i></b> 😀</p>',rich_text_version=1,font_family='DejaVu Sans',font_size=16,w=400,h=150)
        for size,width in [(16,400),(23,180),(12,480)]:
            data.update(font_size=size,w=width)
            content=resolve_rich_text(data,{'nome':'<p>Ana Ç</p>'});doc=build_document(data,content)
            cursor=doc.find('Ana Ç');fmt=cursor.charFormat()
            self.assertGreater(fmt.fontWeight(),400);self.assertTrue(fmt.fontItalic())
            self.record(f'placeholder-{size}',dict(html=content,geometry=text_geometry(doc,data)))

    def test_collective_resize_preserves_four_texts_and_history(self):
        w=self.editor('simple',1);w.load_starter_document(text_document(4,long=True),lambda _:b'')
        w.select_all_items();before=deepcopy(w._document_with_active_page());bounds=w.scene.itemsBoundingRect()
        self.assertTrue(w.begin_multi_selection_resize(bounds.topLeft(),bounds))
        w.update_multi_selection_resize(1.2);w.end_multi_selection_resize();after=deepcopy(w._document_with_active_page())
        boxes=[i for i in w.scene.items() if isinstance(i,DesignerBox)]
        self.assertEqual(len(boxes),4)
        for box in boxes:self.assertEqual(box.text_item.y(),text_geometry(box.text_item.document(),box.text_layout_data())[0])
        self.record('collective-resize',after);w.undo();self.assertEqual([b['html'] for b in w._document_with_active_page()['pages'][0]['boxes']],[b['html'] for b in before['pages'][0]['boxes']])
        w.redo();restored=w._document_with_active_page()
        for old,new in zip(after['pages'][0]['boxes'],restored['pages'][0]['boxes']):
            for key in ('html','w','h','font_size','x','y'):self.assertEqual(old[key],new[key])
        self.record('collective-redo',restored)

    @unittest.skipUnless(shutil.which('pdftoppm'),'Poppler necessário para os pixels PDF')
    def test_approved_models_editor_preview_png_and_pdf_before_after(self):
        identities=('personnel','internship-certificate','identification-prism','formal-invitation')
        for identity in identities:
            template=next(t for t in starter_catalog('model') if t.id==identity)
            document,provider=model_from_starter(template)
            w=self.editor('simple',1);w.load_starter_document(document,provider)
            values={k:'{'+k+'}' for page in document['pages'] for box in page['boxes'] for k in variables_in_html(box['html'])}
            channels=[]
            for page in document['pages']:
                page_id=page['page_id'];w.switch_model_page(page_id)
                canvas=w._get_document_rect()
                editor=QImage(800,600,QImage.Format.Format_ARGB32);editor.fill(Qt.GlobalColor.white)
                painter=QPainter(editor)
                try:w.scene.render(painter,QRectF(0,0,800,600),canvas)
                finally:painter.end()
                data=adapt_model_page(document,page_id);renderer=NativeRenderer(data,asset_provider=provider)
                preview=renderer.render_preview_image(values,max_side=800)
                png=renderer.render_to_qimage(values,values)
                channel={'editor':image_hash(editor),'preview':image_hash(preview),'png':image_hash(png)}
                tiled=PageTilingRenderer(document,page_id,values,values,asset_provider=provider)
                paper=(tiled.bounds.width()/ (300/25.4),tiled.bounds.height()/(300/25.4))
                from core.tiling import build_tile_plan
                plan=build_tile_plan(tiled.bounds,paper=paper,margin_mm=0,overlap_mm=0,crop_marks=False,auto_orientation=False)
                self.assertEqual(len(plan.tiles),1)
                path=self.root/f'{identity}-{page_id}.pdf';tiled.export_pdf(path,plan=plan)
                prefix=self.root/f'{identity}-{page_id}-pdf'
                subprocess.run(['pdftoppm','-f','1','-l','1','-r','96','-singlefile','-png',str(path),str(prefix)],check=True,capture_output=True)
                raster=QImage(str(prefix)+'.png');self.assertFalse(raster.isNull());channel['pdf_pixels']=image_hash(raster)
                channels.append(channel)
                output=os.environ.get('FORNAX_TEXT_EVIDENCE')
                if output:
                    artifacts=Path(output).with_suffix('');artifacts.mkdir(exist_ok=True)
                    shutil.copy(path,artifacts/path.name);shutil.copy(str(prefix)+'.png',artifacts/(prefix.name+'.png'))
                    preview.save(str(artifacts/f'{identity}-{page_id}-preview.png'))
            self.record('model-'+identity,channels)


class TextUpdateWorkTest(unittest.TestCase):
    setUpClass=classmethod(contracts.PerformanceContractsTest.setUpClass.__func__)
    setUp=contracts.PerformanceContractsTest.setUp
    editor=contracts.PerformanceContractsTest.editor
    editable=TextUpdateBehaviorTest.editable

    def test_apply_state_measures_final_layout_once(self):
        box=editor_box(dict(html=rich_sample(True),rich_text_version=1,w=400,h=700))
        from features.editor import canvas_items
        with patch.object(canvas_items,'text_geometry',wraps=text_geometry) as measure:
            box.state.line_height=.8;box.state.font_size=23;box.apply_state()
        self.assertEqual(measure.call_count,1)
        self.assertEqual(box.text_item.y(),text_geometry(box.text_item.document(),box.text_layout_data())[0])

    def test_metrics_reuse_is_local_and_recomputed_on_font_changes(self):
        doc=build_document(dict(w=1000,h=2000,rich_text_version=1),rich_sample(True))
        with patch('core.text_layout.QFontMetrics',wraps=QFontMetrics) as metric:
            text_geometry(doc,dict(h=2000))
            self.assertLessEqual(metric.call_count,5)
            self.assertGreater(metric.call_count,0)
            first=metric.call_count
            doc.setDefaultFont(doc.defaultFont())
            text_geometry(doc,dict(h=2000))
            self.assertGreater(metric.call_count,first)

    def test_format_batches_layout_without_blocking_document_signals(self):
        w,box=self.editable(True);c=box.text_item.textCursor();c.select(QTextCursor.SelectionType.Document);box.text_item.setTextCursor(c)
        observed=[];box.text_item.document().contentsChanged.connect(lambda:observed.append(box.state.html_content==box.text_item.toHtml()))
        from features.editor import canvas_items
        with patch.object(canvas_items,'text_geometry',wraps=text_geometry) as measure:
            w.canvas_edit.format('size',25)
        self.assertEqual(measure.call_count,1);self.assertTrue(observed);self.assertTrue(all(observed))

    def test_resize_measures_once_and_keeps_final_width(self):
        box=editor_box(dict(html=rich_sample(True),rich_text_version=1,w=400,h=700))
        from features.editor import canvas_items
        with patch.object(canvas_items,'text_geometry',wraps=text_geometry) as measure:
            box.resize_from_handle(280,800)
        self.assertEqual(measure.call_count,1);self.assertEqual(box.text_item.textWidth(),280)
        self.assertEqual(box.text_item.y(),text_geometry(box.text_item.document(),box.text_layout_data())[0])

    def test_nested_batch_restores_flags_and_final_layout_even_with_exception(self):
        box=editor_box(dict(html=rich_sample(),rich_text_version=1,w=400,h=700))
        from features.editor import canvas_items
        with patch.object(canvas_items,'text_geometry',wraps=text_geometry) as measure:
            with self.assertRaisesRegex(ValueError,'ensaio'):
                with box._text_layout_batch():
                    with box._text_layout_batch():
                        box.state.html_content=rich_sample(True);box.apply_state()
                        raise ValueError('ensaio')
        self.assertEqual(measure.call_count,1);self.assertEqual(box._text_layout_depth,0)
        self.assertEqual(box.text_item.y(),text_geometry(box.text_item.document(),box.text_layout_data())[0])


    def test_cursor_font_queries_follow_lines_instead_of_character_count(self):
        doc=build_document(dict(w=1000,h=3000,rich_text_version=1),rich_sample(True))
        count=[]
        class Probe:
            def __init__(self,*args):self.cursor=QTextCursor(*args)
            def setPosition(self,*args):return self.cursor.setPosition(*args)
            def charFormat(self):count.append(1);return self.cursor.charFormat()
        with patch('core.text_layout.QTextCursor',Probe):text_geometry(doc,dict(h=3000))
        self.assertEqual(len(count),2)
