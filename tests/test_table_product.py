"""Etapa 07: limites do quadro, saídas e ciclo de biblioteca com tabelas."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from uuid import uuid5, NAMESPACE_URL
from PySide6.QtCore import Qt, QRectF, QSettings
from PySide6.QtGui import QImage, QPainter
from pypdf import PdfReader
import test_table_canvas as canvas
from core.table_model import new_table, set_cell_html, format_edges, resize_table
from core.model_document import normalize_model_document, add_model_table, add_blank_back_page, adapt_model_page
from core.organogram import add_organogram, new_group, board_bounds, UNITS_PER_MM
from core.fornax_container import save_public_fornax, open_public_fornax, PUBLIC_MODE
from core.fornax_export import ExportRequest, export_models
from core.fornax_import import open_import_package, import_candidate
from core.fornax_session import FornaxSessionManager
from core.model_library import scan_model_library
from core.tiling import build_tile_plan
from features.editor.table_item import TableItem
from features.generator.renderer import renderers_for_document
from features.generator.organogram import OrganogramRenderer, OrganogramWorker
from features.generator.workers import DirectRenderWorker, PageRenderWorker, SecureGroupedPdfWorker, PreviewRenderWorker


def specimen(*, groups=1, columns=2, rows=2):
    table=set_cell_html(new_table(1,1,width=120,height=160),0,0,'<p><b>{nome}</b></p>')
    table['style'].update(font_size=7,fill_color='#dceeff')
    table['object_id']=str(uuid5(NAMESPACE_URL,'fornax/product/table'))
    table['cells'][0]['id']=str(uuid5(NAMESPACE_URL,'fornax/product/cell'))
    doc=add_organogram(add_model_table(normalize_model_document({'name':'Tabela sintética','canvas_size':{'w':120,'h':160}}),table))
    doc['organogram']['margin_mm']=0
    for index in range(groups):
        group=new_group(doc,columns=columns,rows=rows,card_width_mm=12,gap_mm=1,
                        start_row=index*columns*rows,x=index*columns*50,y=0)
        group.update(id=f'product-block-{index}',name=f'Grupo {index+1}',card_w=40,card_h=160/3,gap_x=4,gap_y=4)
        doc['organogram']['groups'].append(group)
    return normalize_model_document(doc)


class TableProductTest(unittest.TestCase):
    setUpClass=classmethod(canvas.TableCanvasTest.setUpClass.__func__)
    tearDownClass=classmethod(canvas.TableCanvasTest.tearDownClass.__func__)
    setUp=canvas.TableCanvasTest.setUp
    tearDown=canvas.TableCanvasTest.tearDown
    editor=canvas.TableCanvasTest.editor

    def geometry_case(self):
        doc=specimen()
        table=new_table(2,2,width=300,height=180)
        table.update(x=-450,y=-200,rotation=27)
        table=format_edges(table,0,0,1,1,{'width':14},target='outer')
        doc=add_model_table(doc,table,'organogram')
        w,_=self.editor(doc);w.switch_model_page('organogram')
        item=next(i for i in w.scene.items() if isinstance(i,TableItem))
        return w,item

    def test_board_bounds_include_rotated_table_stroke_without_reading_html(self):
        w,item=self.geometry_case()
        expected=board_bounds(w._capture_document_history_state()['document']['organogram'])
        with patch.object(item,'to_data',side_effect=AssertionError('Geometria não deve serializar conteúdo')):
            self.assertEqual(w._board_geometry()[3],expected)
        w._update_board_extent()
        self.assertEqual(w._get_document_rect(),expected)

    def test_bounds_cache_tracks_move_resize_rotation_visibility_and_stroke(self):
        w,item=self.geometry_case();paths=w._board_geometry()[1]
        actions=[lambda:item.setPos(-550,-300),lambda:item.setRotation(45),
                 lambda:item.publish_table_data(resize_table(item.to_data(),600,200)),
                 lambda:item.publish_table_data(format_edges(item.to_data(),0,0,1,1,{'width':30},target='outer')),
                 lambda:item.setVisible(False),lambda:item.setVisible(True)]
        for action in actions:
            action()
            expected=board_bounds(w._capture_document_history_state()['document']['organogram'])
            actual=w._board_geometry()
            self.assertEqual(actual[3],expected)
            self.assertIs(actual[1],paths,'Arte complementar não deve recalcular rotas')

    def test_layout_preview_and_real_rows_accept_a_field_only_in_table(self):
        doc=specimen()
        preview=OrganogramRenderer(doc,[],layout_preview=True)
        self.assertEqual(len(preview.slots),4)
        self.assertFalse(preview.preview(600).isNull())
        real=OrganogramRenderer(doc,[{'nome':'Um'},{'nome':''},{'nome':'Dois'}])
        self.assertEqual(len(real.slots),2);self.assertEqual(real.assignment_issues,[])
        self.assertEqual(doc,specimen())

    def test_thousand_cards_in_twenty_groups_draw_without_per_card_editors(self):
        doc=specimen(groups=20,columns=10,rows=5)
        from features.editor.organogram_editor import BoardGroupItem
        w,_=self.editor(doc);w.switch_model_page('organogram')
        groups=[i for i in w.scene.items() if isinstance(i,BoardGroupItem)]
        self.assertEqual(len(groups),20)
        self.assertFalse(any(isinstance(i,TableItem) for i in w.scene.items()))
        self.assertEqual({i.preview.cacheKey() for i in groups},{w._board_card_preview.cacheKey()})
        previous=w._board_card_preview.copy()
        w.switch_model_page('front')
        table=next(i for i in w.scene.items() if isinstance(i,TableItem))
        candidate=table.to_data();candidate['style']['fill_color']='#ffccaa'
        table.publish_table_data(candidate);w.switch_model_page('organogram')
        self.assertNotEqual(w._board_card_preview,previous)
        renderer=OrganogramRenderer(doc,[{'nome':str(i)} for i in range(1000)])
        self.assertEqual(len(renderer.slots),1000);self.assertEqual(len(doc['organogram']['groups']),20)
        self.assertEqual(renderer.assignment_issues,[])
        image=renderer.preview(1200)
        self.assertEqual(max(image.width(),image.height()),1200)
        self.assertFalse(image.isNull())

    def run_worker(self,worker):
        errors=[];worker.error_occurred.connect(errors.append)
        worker.start();self.assertTrue(worker.wait(60000));self.app.processEvents()
        self.assertEqual(errors,[])

    def duplex(self):
        front=specimen();front.pop('organogram')
        doc=add_blank_back_page(front)
        table=set_cell_html(new_table(1,1,width=120,height=160),0,0,'<p>{verso}</p>')
        table['style'].update(font_size=7,fill_color='#ffddcc')
        return add_model_table(doc,table,'back')

    def test_direct_png_and_pdf_batch_preserve_both_faces(self):
        doc=self.duplex();renderers=renderers_for_document(doc)
        tasks=[(i,i,0,{'nome':str(i),'verso':'V'},{'nome':str(i),'verso':'V'},f'card{i}') for i in range(2)]
        for mode in ('PNG','PDF'):
            out=self.root/mode;out.mkdir()
            self.run_worker(DirectRenderWorker(tasks,renderers,out,mode,target_w_mm=12,target_h_mm=16))
            files=list(out.iterdir());self.assertEqual(len(files),4 if mode=='PNG' else 2)
            for file in files:
                if mode=='PDF':self.assertEqual(len(PdfReader(file).pages),2)
                else:
                    image=QImage(str(file));self.assertEqual((image.width(),image.height()),(120,160))
                    color='#dceeff' if 'pag1' in file.name else '#ffddcc'
                    self.assertEqual(image.pixelColor(50,120).name(),color)

    def test_multiple_per_sheet_duplex_separate_and_single_pdf(self):
        renderers=renderers_for_document(self.duplex())
        tasks=[(i,i,0,{'nome':str(i),'verso':'V'},{'nome':str(i),'verso':'V'},f'card{i}') for i in range(2)]
        settings={'enabled':True,'duplex':True,'target_w_mm':12,'target_h_mm':16,
                  'sheet_w_mm':48,'sheet_h_mm':48,'crop_marks':True,'bleed_margin':True}
        out=self.root/'sheets';out.mkdir()
        page_tasks=[{'page_num':0,'front':tasks,'back':tasks,'output_base':'folha'}]
        self.run_worker(PageRenderWorker(page_tasks,renderers,out,settings,'PDF'))
        for file in out.glob('*.pdf'):self.assertEqual(len(PdfReader(file).pages),2)
        self.assertEqual(len(list(out.glob('*.pdf'))),1)
        out=self.root/'single';out.mkdir()
        self.run_worker(SecureGroupedPdfWorker(tasks,renderers,out,settings,12,16))
        pdf=PdfReader(next(out.glob('*.pdf')));self.assertEqual(len(pdf.pages),2)
        self.assertAlmostEqual(float(pdf.pages[0].mediabox.width),48*72/25.4,delta=.1)

    def test_tiles_reassemble_table_and_board_artwork_exactly(self):
        doc=specimen();table=new_table(1,1,width=32,height=24);table.update(x=-10,y=-10)
        table['style']['fill_color']='#aaddcc';doc=add_model_table(doc,table,'organogram')
        renderer=OrganogramRenderer(doc,[{'nome':str(i)} for i in range(4)],fixed_layout=True)
        plan=build_tile_plan(renderer.bounds,(40/UNITS_PER_MM,60/UNITS_PER_MM),margin_mm=0,overlap_mm=0,crop_marks=False)
        size=(round(plan.columns*40),round(plan.rows*60))
        expected=QImage(*size,QImage.Format.Format_ARGB32);expected.fill(Qt.GlobalColor.white)
        painter=QPainter(expected)
        try:
            painter.translate(-renderer.bounds.topLeft());renderer.paint(painter)
        finally:painter.end()
        actual=QImage(expected.size(),expected.format());actual.fill(Qt.GlobalColor.white)
        painter=QPainter(actual)
        try:
            origin=plan.tiles[0].trim.topLeft()
            for tile in plan.tiles:painter.drawImage(tile.trim.topLeft()-origin,renderer.tile_image(plan,tile,scale=1))
        finally:painter.end()
        self.assertEqual(actual,expected)

    def test_organogram_png_pdf_and_tiled_single_or_separate_outputs(self):
        doc=specimen();rows=[{'nome':str(i)} for i in range(4)]
        options={'paper':(40/UNITS_PER_MM,60/UNITS_PER_MM),'margin_mm':0,'overlap_mm':0,'crop_marks':False}
        plan=build_tile_plan(OrganogramRenderer(doc,rows,fixed_layout=True).bounds,**options)
        for mode,tiling,separate in [('png',None,False),('pdf',None,False),('png',options,True),('pdf',options,True),('pdf',options,False)]:
            out=self.root/f'{mode}-{bool(tiling)}-{separate}';out.mkdir()
            self.run_worker(OrganogramWorker(doc,rows,rows,out,mode,tiling_options=tiling,separate_files=separate,dpi=96))
            files=list(out.iterdir());self.assertEqual(len(files),len(plan.tiles) if tiling and (separate or mode=='png') else 1)
            if tiling and separate:self.assertEqual({f.stem for f in files},{'organograma_'+t.name for t in plan.tiles})
            for file in files:
                if mode=='pdf':self.assertEqual(len(PdfReader(file).pages),len(plan.tiles) if tiling and not separate else 1)
                else:self.assertFalse(QImage(str(file)).isNull())

    def test_library_import_export_duplicate_rename_reopen_and_thumbnail(self):
        source=self.root/'source.fornax';doc=self.duplex();save_public_fornax(doc,source)
        shared=self.root/'shared.fornax';export_models([ExportRequest(source,'Sintético')],shared,include_signatures=False)
        from core.paths import get_models_dir
        library=get_models_dir();library.mkdir(exist_ok=True,parents=True)
        with open_import_package(shared) as candidates:
            imported=import_candidate(candidates[0],library/'imported.fornax',include_signatures=False,model_name='Importado')
        self.assertEqual(imported.mode,PUBLIC_MODE)
        models=scan_model_library(library);self.assertEqual(len(models),1)
        sessions=FornaxSessionManager()
        try:
            status=sessions.select(models[0].path);self.assertEqual(status.descriptor.mode,PUBLIC_MODE)
            from test_signature_preview import PreviewWorkspace
            w=PreviewWorkspace(models[0].path,sessions,QSettings(str(self.root/'ui.ini'),QSettings.Format.IniFormat))
            try:
                w._reload_models_from_disk(select_name='Importado')
                original=models[0].path.read_bytes()
                with patch.object(w,'_legacy_migration_credentials',return_value=(PUBLIC_MODE,None)):
                    w._on_duplicate_model()
                copy=w._current_library_entry();self.assertNotEqual(copy.descriptor.model_id,imported.model_id)
                with patch('features.workspace.main_window.dialog_get_text',return_value=('Renomeado',True)),patch('features.workspace.main_window.QMessageBox.critical',side_effect=AssertionError('Falha ao renomear')):
                    w._on_rename_model()
                renamed=w._current_library_entry()
                reopened=open_public_fornax(renamed.path).document()
                self.assertEqual(reopened['pages'],doc['pages']);self.assertEqual(reopened['name'],'Renomeado')
                self.assertEqual(renamed.descriptor.mode,PUBLIC_MODE)
                self.assertEqual(models[0].path.read_bytes(),original)
                self.assertFalse(w.preview_panel.preview._pixmap.isNull())
            finally:w._preview_refresh_timer.stop();w.deleteLater();self.app.processEvents()
        finally:sessions.close()

    def test_legacy_v6_thumbnail_publishes_only_current_source(self):
        from core.model_document import save_model_document
        doc=self.duplex();folder=self.root/'legacy';folder.mkdir()
        save_model_document(doc,folder)
        ready=[];worker=PreviewRenderWorker('Sintético',adapt_model_page(doc),folder)
        worker.preview_ready.connect(lambda name,path:ready.append(path));self.run_worker(worker)
        self.assertEqual(len(ready),1);self.assertFalse(QImage(ready[0]).isNull())
        stale=PreviewRenderWorker('Sintético',adapt_model_page(doc),folder)
        doc['name']='Alterado';save_model_document(doc,folder)
        stale.preview_ready.connect(lambda *args:self.fail('Miniatura de revisão antiga publicada'))
        self.run_worker(stale)


if __name__=='__main__':unittest.main()
