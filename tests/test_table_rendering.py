"""Etapa 03: conteúdo, medidas, clipping, camadas e saídas reais de tabelas."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent/'performance'))
from PySide6.QtCore import Qt,QPointF,QRectF,QCoreApplication,QEvent,QSettings
from PySide6.QtGui import QColor,QImage,QPainter,QPen,QTextCursor,QFont,QFontInfo
from PySide6.QtWidgets import QApplication,QGraphicsItem,QGraphicsScene
from pypdf import PdfReader

from core.ui_font import install_ui_font,DOCUMENT_FONT_FAMILY
from core.table_layout import TableLayout
from core.table_paint import paint_table
from core.table_model import new_table,set_cell_html,format_cells,format_edges,merge_cells,table_size
from core.model_document import adapt_model_page,add_model_table,add_blank_back_page,normalize_model_document
from core.font_utils import template_font_families,missing_template_fonts
from core.model_info import current_model_snapshot
from core.organogram import add_organogram,new_group,row_is_valid,card_fields
from core.table_warnings import table_warning_messages
from core.text_layout import resolve_rich_text
from features.generator.renderer import NativeRenderer,renderers_for_document
from features.generator.organogram import OrganogramRenderer,OrganogramWorker
from features.generator.workers import DirectRenderWorker,PageRenderWorker,SecureGroupedPdfWorker
from table_document_fixtures import documents
from table_render_evidence import specimen_table,document,vector_pdf


def image_for(layout,width=1500,height=860):
    image=QImage(width,height,QImage.Format.Format_ARGB32)
    image.setDotsPerMeterX(3780);image.setDotsPerMeterY(3780)
    image.fill(Qt.GlobalColor.white)
    painter=QPainter(image)
    try:paint_table(painter,layout)
    finally:painter.end()
    return image


class TableRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        install_ui_font(cls.app)
        cls.errors=[];cls.previous_hook=sys.excepthook
        sys.excepthook=lambda typ,value,tb:cls.errors.append(str(value))

    @classmethod
    def tearDownClass(cls):
        sys.excepthook=cls.previous_hook

    def setUp(self):
        self.temp=TemporaryDirectory(prefix='fornax-table-render-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.table=specimen_table()
        self.enterContext(patch('core.paths._data_home',return_value=self.root/'data'))

    def tearDown(self):
        self.app.processEvents()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.assertEqual(self.errors,[])

    def test_geometry_has_expected_independent_measures_and_merged_coverage(self):
        layout=TableLayout(self.table)
        self.assertEqual((layout.width,layout.height),(1440,800))
        self.assertEqual(layout.x,[0,360,720,1080,1440])
        self.assertEqual(layout.y,[0,200,400,600,800])
        self.assertEqual(len(layout.cells),10)
        self.assertEqual(layout.cells[0].rect,QRectF(0,0,1440,200))
        self.assertEqual(layout.cells[0].inner,QRectF(7,7,1426,186))
        merged=next(c for c in layout.cells if (c.cell['row'],c.cell['column'])==(2,2))
        self.assertEqual(merged.rect,QRectF(720,400,720,400))
        self.assertEqual(layout.hit(QPointF(1400,790)),(2,2))
        self.assertIsNone(layout.hit(QPointF(1440,0)))
        self.assertEqual(len(layout.visible_edges),33)

    def test_physical_decimal_font_fixed_device_and_rich_character_styles(self):
        layout=TableLayout(self.table)
        entry=next(c for c in layout.cells if c.cell['row']==1 and c.cell['column']==0)
        self.assertEqual(layout.device.logicalDpiX(),300)
        self.assertEqual(entry.document.defaultFont().pointSizeF(),9.5)
        cursor=QTextCursor(entry.document);cursor.setPosition(1)
        self.assertGreater(cursor.charFormat().fontWeight(),QFont.Weight.Normal)
        self.assertAlmostEqual(cursor.charFormat().fontPointSize() or entry.document.defaultFont().pointSizeF(),9.5)

    def test_missing_fields_do_not_hide_fixed_content_fill_or_grid(self):
        table=set_cell_html(new_table(1,1,width=600,height=250),0,0,'<p>Nota: <b>{nota}</b> · {nome}</p>')
        layout=TableLayout(table,{'nota':None})
        self.assertEqual(layout.cells[0].document.toPlainText(),'Nota:  · ')
        self.assertEqual(len(layout.visible_edges),4)
        preview=TableLayout(table)
        self.assertIn('{nota}',preview.cells[0].document.toPlainText())
        self.assertIn('{nome}',preview.cells[0].document.toPlainText())

    def test_bundled_inter_alias_uses_actual_family_without_changing_global_fonts(self):
        global_family=QFontInfo(QFont('Inter')).family()
        table=new_table(1,1,width=900,height=300)
        table['style']['font_family']='Inter'
        table=set_cell_html(table,0,0,'<p>𝄞 <span style="font-family:&quot;Inter&quot;;font-size:11.5pt;"><b>{nome}</b></span></p>')
        layout=TableLayout(table,{'nome':'Ana'})
        entry=layout.cells[0]
        self.assertEqual(entry.document.defaultFont().family(),DOCUMENT_FONT_FAMILY)
        fmt=entry.document.find('Ana').charFormat()
        self.assertEqual(fmt.fontFamilies(),[DOCUMENT_FONT_FAMILY])
        self.assertEqual(QFontInfo(fmt.font()).family(),DOCUMENT_FONT_FAMILY)
        self.assertEqual(fmt.fontPointSize(),11.5)
        self.assertGreater(fmt.fontWeight(),400)
        self.assertEqual(QFontInfo(QFont('Inter')).family(),global_family)

    def test_optional_sections_and_non_bmp_utf16_formatted_placeholders(self):
        table=set_cell_html(new_table(1,1,width=900,height=400),0,0,
            '<p>𝄞 Ω — <b>{no<i>me}</i></b> |Detalhe: {detalhe}| · |literal|</p>')
        layout=TableLayout(table,{'nome':'Ána 𝄞','detalhe':'<p> </p>'})
        plain=layout.cells[0].document.toPlainText()
        self.assertEqual(plain,'𝄞 Ω — Ána 𝄞  · |literal|')
        cursor=layout.cells[0].document.find('Ána')
        self.assertGreater(cursor.charFormat().fontWeight(),400)
        populated=TableLayout(table,{'nome':'Ána','detalhe':'Atividade'})
        self.assertIn('Detalhe: Atividade',populated.cells[0].document.toPlainText())
        self.assertNotIn('|Detalhe',populated.cells[0].document.toPlainText())

    def test_spreadsheet_html_only_adds_emphasis_and_does_not_replace_model_typography(self):
        table=set_cell_html(new_table(1,1,width=900,height=400),0,0,'<p><b>{nome}</b></p>')
        table['style'].update(font_family='DejaVu Serif',font_size=12.5,font_color='#112233')
        content='<html><body style="font-family:Arial;font-size:80pt;color:red;"><p><i>Ana</i><br>Ω</p></body></html>'
        layout=TableLayout(table,{'nome':content})
        cell=layout.cells[0]
        self.assertEqual(cell.document.toPlainText(),'Ana\nΩ')
        cursor=cell.document.find('Ana');fmt=cursor.charFormat()
        self.assertGreater(fmt.fontWeight(),400);self.assertTrue(fmt.fontItalic())
        font=fmt.font().resolve(cell.document.defaultFont())
        self.assertEqual(font.family(),'DejaVu Serif')
        self.assertEqual(font.pointSizeF(),12.5)
        self.assertEqual(fmt.foreground().color().name(),'#112233')

    def test_box_missing_value_policy_remains_unchanged(self):
        box=dict(html='<p>Nota: {nota}</p>',font_size=10,font_family='DejaVu Sans',w=300,rich_text_version=1)
        self.assertIsNone(resolve_rich_text(box,{}))
        self.assertEqual(TableLayout(set_cell_html(new_table(1,1),0,0,box['html']),{}).cells[0].document.toPlainText(),'Nota: ')

    def test_alignment_wrap_manual_break_and_overflow_are_measured(self):
        layout=TableLayout(self.table)
        by={(c.cell['row'],c.cell['column']):c for c in layout.cells}
        center=by[1,2];bottom=by[1,3]
        self.assertAlmostEqual(center.offset_y,(center.inner.height()-center.text_height)/2)
        self.assertAlmostEqual(bottom.offset_y,bottom.inner.height()-bottom.text_height)
        self.assertGreater(center.lines[0][2],0)
        self.assertGreater(bottom.lines[0][2],0)
        self.assertTrue(by[2,1].overflow_x)
        self.assertTrue(by[3,0].overflow_y)
        self.assertEqual(by[3,0].offset_y,0)
        self.assertEqual(len(by[1,1].lines),2)
        self.assertEqual(len(layout.warnings),2)

    def test_text_clip_keeps_adjacent_cell_clean_even_with_long_no_wrap_or_many_lines(self):
        table=new_table(2,2,width=700,height=400)
        table['style']['fill_color']='#aaddcc'
        table=set_cell_html(table,0,0,'<p>'+'X'*70+'</p>')
        table=format_cells(table,0,0,0,0,{'wrap':False})
        table=set_cell_html(table,1,0,'<p>'+'<br>'.join(['VERTICAL']*20)+'</p>')
        image=image_for(TableLayout(table),700,400)
        for y in (20,60,110,220,300,375):
            self.assertEqual(image.pixelColor(500,y).name(),'#aaddcc')
        self.assertEqual(TableLayout(table).width,700)

    def test_border_styles_are_unique_hidden_merges_stay_hidden_and_neighbor_insets_use_each_side(self):
        table=new_table(2,2,width=700,height=400)
        table=format_edges(table,0,0,1,1,{'color':'#ff0000','width':12},target='outer')
        table=format_edges(table,0,0,1,1,{'color':'#0000ff','width':4,'opacity':.5},target='inner')
        layout=TableLayout(table)
        self.assertEqual(layout.cells[0].inner,QRectF(12,12,330,180))
        image=image_for(layout,700,400)
        self.assertEqual(image.pixelColor(2,100).name(),'#ff0000')
        shared=image.pixelColor(350,100)
        self.assertAlmostEqual(shared.red(),127,delta=1)
        merged=merge_cells(table,0,0,0,1)
        self.assertNotIn(('v',0,1),TableLayout(merged).visible_edges)
        self.assertEqual(image_for(TableLayout(merged),700,400).pixelColor(350,100).name(),'#ffffff')

    def test_painter_transform_opacity_clip_pen_and_hints_are_restored(self):
        image=QImage(1800,1000,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.white)
        painter=QPainter(image)
        try:
            painter.translate(19,23);painter.setOpacity(.6);painter.setPen(QPen(QColor('magenta'),5))
            painter.setClipRect(QRectF(0,0,1700,900))
            before=(painter.transform(),painter.opacity(),painter.pen(),painter.clipPath(),painter.renderHints())
            paint_table(painter,TableLayout(self.table))
            self.assertEqual(before,(painter.transform(),painter.opacity(),painter.pen(),painter.clipPath(),painter.renderHints()))
        finally:painter.end()

    def test_no_source_mutation_row_changes_empty_values_or_emphasis_leak(self):
        original=deepcopy(self.table);renderer=NativeRenderer(adapt_model_page(document(self.table)))
        first=renderer.render_to_qimage({'nome':'Ana'},{'nome':'<b>Ana</b>','nota':'9'})
        empty=renderer.render_to_qimage({},{});renderer.render_to_qimage({'nome':'Bruno'},{'nome':'Bruno','nota':'5'})
        again=renderer.render_to_qimage({'nome':'Ana'},{'nome':'<b>Ana</b>','nota':'9'})
        self.assertEqual(first,again);self.assertNotEqual(first,empty)
        self.assertEqual(self.table,original)

    def test_static_base_prefix_matches_uncached_and_does_not_cache_variable_table_or_cover_layers(self):
        static=new_table(1,1,width=700,height=400);static.update(x=30,y=30)
        static=set_cell_html(static,0,0,'<p>Texto fixo</p>')
        dynamic=set_cell_html(new_table(1,1,width=600,height=300),0,0,'<p><b>{nome}</b></p>')
        dynamic.update(x=70,y=100)
        source=add_model_table(document(static),dynamic)
        page=adapt_model_page(source)
        a=NativeRenderer(page);b=NativeRenderer(page);b.pre_render_static_base()
        for values in ({'nome':'Ana'}, {}, {'nome':'Bruno'}, {'nome':'Ana'}):
            self.assertEqual(a.render_to_qimage(values,values),b.render_to_qimage(values,values))
        self.assertEqual(b._static_base_cache,NativeRenderer(adapt_model_page(document(static))).render_to_qimage({},{}))

    def test_legacy_flat_page_without_layer_order_and_table_between_other_layers(self):
        table=new_table(1,1,width=600,height=300)
        table['style']['fill_color']='#ffdd00'
        page=dict(canvas_size={'w':600,'h':300},boxes=[],images=[],shapes=[],signatures=[],tables=[table])
        self.assertEqual(NativeRenderer(page).render_preview_image().pixelColor(300,220).name(),'#ffdd00')
        page['shapes']=[dict(object_id='front-shape',shape_type='rectangle',width=100,height=100,x=200,y=150,fill_color='#ff0000')]
        page['layer_order']=[table['object_id'],'front-shape']
        self.assertEqual(NativeRenderer(page).render_preview_image().pixelColor(240,190).name(),'#ff0000')

    def test_image_preview_and_png_file_match_with_expected_physical_dimensions(self):
        source=document(self.table);renderer=NativeRenderer(adapt_model_page(source))
        values={'nome':'Ana','nota':'9'}
        image=renderer.render_to_qimage(values,values)
        self.assertEqual(image,renderer.render_preview_image(values))
        path=self.root/'table.png';renderer.render_row(values,values,path)
        saved=QImage(str(path))
        self.assertEqual(saved.size(),image.size())
        self.assertEqual(saved.pixelColor(40,40).name(),'#203746')
        self.assertAlmostEqual(saved.width()*1000/saved.dotsPerMeterX(),127,delta=.01)
        self.assertEqual(bytes(saved.constBits()),bytes(image.constBits()))

    def test_font_collection_missing_font_and_model_info_include_tables_back_and_board(self):
        table=set_cell_html(new_table(1,1),0,0,'<p><span style="font-family:\'Fonte Sintética Inline\';">X</span></p>')
        table['style']['font_family']='Fonte Sintética Padrão'
        source=add_blank_back_page(document(table))
        other=new_table(1,1);other['style']['font_family']='Fonte Sintética Verso'
        source=add_model_table(source,other,'back')
        fonts=template_font_families(source)
        self.assertIn('Fonte Sintética Padrão',fonts);self.assertIn('Fonte Sintética Inline',fonts)
        self.assertIn('Fonte Sintética Verso',fonts)
        with patch('core.font_utils.system_font_families',return_value=set()):
            self.assertEqual(missing_template_fonts(source),fonts)
        snapshot=current_model_snapshot(source)
        self.assertEqual(len(snapshot['text_boxes']),2)
        source=add_organogram(document())
        source=add_model_table(source,other,'organogram')
        self.assertIn('Fonte Sintética Verso',template_font_families(source))
        self.assertIn('Fonte Sintética Verso',current_model_snapshot(source)['text_boxes'][-1]['fonts'])

    def test_table_only_dynamic_card_is_valid_and_empty_record_is_not(self):
        source=document(set_cell_html(new_table(1,1),0,0,'<p><b>{nome}</b></p>'))
        self.assertEqual(card_fields(source),({'nome'},set()))
        self.assertTrue(row_is_valid(source,{'nome':'Ana'}));self.assertFalse(row_is_valid(source,{}))
        source['pages'][0]['tables'][0]['visible']=False
        self.assertFalse(row_is_valid(source,{'nome':'Ana'}))

    def test_board_tables_behind_and_ahead_are_distinct_and_do_not_repeat_card_table(self):
        source=add_organogram(document())
        group=new_group(source,columns=1,rows=1,card_width_mm=30,x=50,y=50)
        source['organogram']['groups'].append(group)
        behind=new_table(1,1,width=500,height=400);behind.update(board_behind=True)
        behind['style']['fill_color']='#22cc77'
        ahead=new_table(1,1,width=100,height=100);ahead.update(x=100,y=100,board_behind=False)
        ahead['style']['fill_color']='#ee8800'
        source=add_model_table(source,behind,'organogram');source=add_model_table(source,ahead,'organogram')
        renderer=OrganogramRenderer(source,[{'nome':'Ana'}])
        self.assertEqual([t['object_id'] for t in renderer.artwork_planes[True].tpl['tables']],[behind['object_id']])
        self.assertEqual([t['object_id'] for t in renderer.artwork_planes[False].tpl['tables']],[ahead['object_id']])
        image=QImage(1600,1000,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.white)
        painter=QPainter(image)
        try:renderer.paint(painter)
        finally:painter.end()
        self.assertEqual(image.pixelColor(20,350).name(),'#22cc77')
        self.assertEqual(image.pixelColor(150,150).name(),'#ee8800')

    def test_all_synthetic_cases_front_back_render_in_both_empty_and_filled_contexts(self):
        for name,source in documents().items():
            with self.subTest(name=name):
                for renderer in renderers_for_document(source):
                    self.assertFalse(renderer.render_preview_image(max_side=600).isNull())
                    self.assertFalse(renderer.render_to_qimage({},{}).isNull())

    def test_real_worker_thread_forks_without_qt_objects_or_ui_references_and_warns(self):
        renderer=NativeRenderer(adapt_model_page(document()))
        renderer.pre_render_static_base()
        task=(0,7,1,{'nome':'Ana'},{'nome':'Ana'},'exemplo')
        worker=DirectRenderWorker([task],[renderer],self.root)
        errors=[];warnings=[];finished=[]
        worker.error_occurred.connect(errors.append);worker.warning_occurred.connect(warnings.append)
        worker.card_finished.connect(lambda *args:finished.append(args))
        worker.start();self.assertTrue(worker.wait(20000));self.app.processEvents()
        self.assertEqual(errors,[]);self.assertEqual(len(finished),1)
        self.assertTrue((self.root/'exemplo.png').is_file())
        self.assertTrue(any('Registro 8' in message for message in warnings))
        self.assertNotIn('Ana',' '.join(warnings))

    def test_rotated_scene_item_matches_renderer_without_selection_overlay(self):
        table=deepcopy(self.table);table.update(x=100,y=100,rotation=8,opacity=.7)
        layout=TableLayout(table)
        class Item(QGraphicsItem):
            def boundingRect(self):return QRectF(0,0,layout.width,layout.height).adjusted(-1,-1,1,1)
            def paint(self,painter,option,widget=None):layout.paint(painter)
        scene=QGraphicsScene();scene.setSceneRect(0,0,1700,1200)
        item=Item();item.setPos(table['x'],table['y']);item.setTransformOriginPoint(layout.width/2,layout.height/2)
        item.setRotation(table['rotation']);item.setOpacity(table['opacity']);scene.addItem(item)
        image=QImage(1700,1200,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.white)
        painter=QPainter(image)
        try:scene.render(painter,QRectF(0,0,1700,1200),scene.sceneRect())
        finally:painter.end()
        self.assertEqual(image,image_for(layout,1700,1200))
        scene.clear()

    def test_workspace_preview_and_fields_open_public_and_protected_table_only_models(self):
        from core.fornax_container import save_public_fornax,save_protected_fornax
        from core.fornax_session import FornaxSessionManager
        from test_signature_preview import PreviewWorkspace
        source=document(set_cell_html(new_table(1,1,width=1200,height=500),0,0,'<p>Nota: <b>{nota}</b></p>'))
        source=add_blank_back_page(source)
        source=add_model_table(source,set_cell_html(new_table(1,1),0,0,'<p>{campo_verso}</p>'),'back')
        source['imposition_settings']={'enabled':False,'active_preset_name':PreviewWorkspace.SYSTEM_IMPOSITION_PRESET}
        source['pages'][0]['tables'][0]['style']['font_family']='FornaxFonteInexistente9'
        for protected in (False,True):
            with self.subTest(protected=protected):
                path=self.root/('protected.fornax' if protected else 'public.fornax')
                if protected:save_protected_fornax(source,path,'senha-teste',mode='full')
                else:save_public_fornax(source,path)
                sessions=FornaxSessionManager()
                window=None
                try:
                    status=sessions.unlock(path,'senha-teste') if protected else sessions.select(path)
                    settings=QSettings(str(self.root/'settings.ini'),QSettings.Format.IniFormat)
                    window=PreviewWorkspace(path,sessions,settings)
                    self.assertFalse(window.preview_panel.preview._pixmap.isNull())
                    headers=[window.table_panel.table.horizontalHeaderItem(c).text()
                             for c in range(window.table_panel.table.columnCount())]
                    self.assertIn('nota',headers);self.assertIn('campo_verso',headers)
                    self.assertEqual(window.preview_renderer.tpl['tables'][0]['object_id'],source['pages'][0]['tables'][0]['object_id'])
                    messages=[];window.log_panel.append=messages.append
                    window._load_fornax_document(sessions.document(),sessions.asset,sessions.status(path))
                    self.assertTrue(any('FornaxFonteInexistente9' in message for message in messages))
                    window._on_preview_page_changed(1)
                    self.assertEqual(window._preview_page_index,1)
                    expected=window._preview_renderers[1].render_to_pixmap(row_rich=None,max_side=1600)
                    self.assertEqual(window.preview_panel.preview._pixmap.toImage(),expected.toImage())
                    self.assertFalse(window.preview_panel.preview._pixmap.isNull())
                finally:
                    if window is not None:
                        window._preview_refresh_timer.stop();window.deleteLater()
                        self.app.processEvents();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
                    sessions.close()

    def test_pdf_workers_report_cell_overflow_through_existing_signals(self):
        renderer=NativeRenderer(adapt_model_page(document()))
        task=(0,4,1,{'nome':'Ana'},{'nome':'Ana'},'pdf-teste')
        settings={'enabled':True,'target_w_mm':127,'target_h_mm':860*25.4/300,
                  'sheet_w_mm':210,'sheet_h_mm':297,'crop_marks':False,'bleed_margin':False}
        workers=[PageRenderWorker([{'page_num':1,'front':[task],'back':None,'output_base':'folha'}],
                                  [renderer],self.root,settings,export_format='PDF')]
        for enabled in (False,True):
            output=self.root/('agrupado-folhas' if enabled else 'agrupado-itens');output.mkdir()
            workers.append(SecureGroupedPdfWorker([task],[renderer],output,{**settings,'enabled':enabled},127,860*25.4/300))
        for worker in workers:
            with self.subTest(worker=type(worker).__name__):
                errors=[];warnings=[]
                worker.error_occurred.connect(errors.append);worker.warning_occurred.connect(warnings.append)
                worker.start();self.assertTrue(worker.wait(20000));self.app.processEvents()
                self.assertEqual(errors,[])
                self.assertTrue(any('Registro 5' in message for message in warnings))
                self.assertNotIn('Ana',' '.join(warnings))
                pdfs=list(worker.output_dir.glob('*.pdf'));self.assertTrue(pdfs)
                for path in pdfs:self.assertGreaterEqual(len(PdfReader(path).pages),1)

    def test_static_overflow_warnings_survive_cache_and_fork_without_accumulating(self):
        table=set_cell_html(new_table(1,1,width=150,height=100),0,0,'<p>'+'X'*40+'</p>')
        table['style']['wrap']=False
        renderer=NativeRenderer(adapt_model_page(document(table)))
        renderer.pre_render_static_base()
        expected=deepcopy(renderer.render_warnings)
        self.assertEqual(len(expected),1)
        fork=renderer.fork()
        for record in ({'nome':'Ana'},{},{'nome':'Bruno'}):
            fork.render_to_qimage(record,record)
            self.assertEqual(fork.render_warnings,expected)
        table['visible']=False
        hidden=NativeRenderer(adapt_model_page(document(table)))
        hidden.render_to_qimage({},{});self.assertEqual(hidden.render_warnings,[])

    def test_foreground_transparent_table_cuts_connectors_but_background_does_not(self):
        source=add_organogram(document(set_cell_html(new_table(1,1),0,0,'<p>{nome}</p>')))
        top=new_group(source,columns=1,rows=1,card_width_mm=30,x=0,y=0)
        source['organogram']['groups'].append(top)
        bottom=new_group(source,columns=1,rows=1,card_width_mm=30,x=0,y=700)
        source['organogram']['groups'].append(bottom)
        source['organogram']['connections']=[{'source':top['id'],'target':bottom['id']}]
        table=new_table(1,1,width=100,height=100);table.update(x=130,y=400)
        table['style']['fill_opacity']=0;table['border']['visible']=False
        source=add_model_table(source,table,'organogram')
        def render(document):
            renderer=OrganogramRenderer(document,[],layout_preview=True)
            image=QImage(500,1100,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.white)
            painter=QPainter(image)
            try:renderer.paint(painter)
            finally:painter.end()
            return renderer,image
        renderer,image=render(source)
        self.assertEqual(image.pixelColor(177,450),QColor('white'))
        source['organogram']['tables'][0]['board_behind']=True
        renderer,behind=render(source)
        self.assertNotEqual(behind.pixelColor(177,450),QColor('white'))
        path=self.root/'organograma.pdf';renderer.export_pdf(path)
        self.assertEqual(len(PdfReader(path).pages[0].images),0)
        png=self.root/'organograma.png';renderer.export_png(png,dpi=150)
        self.assertFalse(QImage(str(png)).isNull())

    def test_rich_record_resources_are_not_loaded_or_painted_in_cells(self):
        table=set_cell_html(new_table(1,1,width=900,height=400),0,0,'<p>{nome}</p>')
        marker=self.root/'red.png'
        image=QImage(10,10,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.red);image.save(str(marker))
        layout=TableLayout(table,{'nome':f'<p>Ana<img src="{marker}"/><img src="https://invalid.example/a.png"/></p>'})
        self.assertEqual(layout.cells[0].document.toPlainText(),'Ana')
        painted=image_for(layout)
        self.assertFalse(any(painted.pixelColor(x,y)==QColor('red') for x in range(40) for y in range(40)))

    def test_vector_pdf_has_real_text_correct_page_size_no_raster_and_matches_png_positions(self):
        renderer=NativeRenderer(adapt_model_page(document()))
        path=self.root/'vector.pdf';vector_pdf(renderer,path,{'nome':'Ana','nota':'9'})
        page=PdfReader(path).pages[0]
        self.assertAlmostEqual(float(page.mediabox.width),360,delta=.5)
        self.assertAlmostEqual(float(page.mediabox.height),206.4,delta=.5)
        text=page.extract_text()
        for required in ('FORNAX','Ana','Nota:','mesclada'):self.assertIn(required,text)
        self.assertEqual(len(page.images),0)
        self.assertIn('/Font',page['/Resources'])
        subprocess.run(['pdftoppm','-r','300','-png','-singlefile',str(path),str(self.root/'pdf')],check=True,capture_output=True)
        image=QImage(str(self.root/'pdf.png'));direct=renderer.render_to_qimage({'nome':'Ana','nota':'9'},{'nome':'Ana','nota':'9'})
        self.assertLessEqual(abs(image.height()-direct.height()),3)
        # Posições de referência conhecidas, longe do texto e das divisórias.
        for x,y in ((40,40),(50,180),(760,410),(1400,750)):
            self.assertEqual(image.pixelColor(x,y).name(),direct.pixelColor(x,y).name())


if __name__=='__main__':unittest.main()
