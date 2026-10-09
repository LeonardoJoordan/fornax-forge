"""Fluxos completos com persistência e comparação visual; dados temporários."""
import argparse,json,os,sys,traceback
from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tests/performance')]


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--reference',type=Path);p.add_argument('--theme',default='dark');args=p.parse_args()
    if args.reference:
        # Substituir pacotes completos, sem alterar os arquivos em uso.
        import core,features
        core.__path__=[str(args.reference/'core')]
        features.__path__=[str(args.reference/'features')]
    from PySide6.QtCore import Qt,QModelIndex,QEvent
    from PySide6.QtGui import QTextCursor
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication,QGraphicsItem
    from shiboken6 import isValid
    from core.ui_font import install_ui_font
    from core.themes import theme_manager
    from core.model_document import persistent_model_document,adapt_model_page,iter_page_asset_paths
    from core.fornax_container import save_public_fornax,save_protected_fornax
    from core.fornax_session import FornaxSessionManager
    from features.editor.editor_window import EditorWindow
    from features.editor.canvas_items import DesignerBox
    from features.editor.organogram_editor import BoardConnectorItem
    from features.generator.renderer import NativeRenderer
    from features.generator.organogram import OrganogramRenderer
    from editor_scenarios import Scenario,make_document
    from copy_cases import canonical_copy_document
    from recovery_cases import wait_recovery,canonical_recovery
    from paint_cases import settle,screen_image,image_hash
    from page_cases import close_window
    from benchmark_editor import write_json,environment,rss_bytes
    errors=[];sys.excepthook=lambda typ,val,tb:errors.append(''.join(traceback.format_exception(typ,val,tb)))
    app=QApplication([]);app.setQuitOnLastWindowClosed(False);app.setCursorFlashTime(0);install_ui_font(app);theme_manager().select(args.theme)
    results=[]
    with TemporaryDirectory(prefix='fornax-final-journey-') as temp:
        os.environ.update(XDG_CONFIG_HOME=temp+'/config',XDG_DATA_HOME=temp+'/data',XDG_CACHE_HOME=temp+'/cache')
        capture_count=0
        def snapshot(w,label):
            nonlocal capture_count
            capture_count+=1
            args.output.parent.mkdir(parents=True,exist_ok=True)

            document=persistent_model_document(w._document_with_active_page());settle(app)
            asset_hashes={ref:sha256(w._save_asset_provider(ref)).hexdigest() for _,_,ref in iter_page_asset_paths(document)}
            canonical=canonical_recovery(canonical_copy_document(document,history=True),asset_hashes)
            tpl=adapt_model_page(document,w._active_page_id)
            image=(OrganogramRenderer(document,[],asset_provider=w._save_asset_provider,layout_preview=True,fixed_layout=True).preview(600)
                   if w._active_page_id=='organogram' else NativeRenderer(tpl,asset_provider=w._save_asset_provider).render_preview_image(None,600))
            picture=screen_image(w); picture.save(str(args.output.parent/f'{capture_count:02}-{label}.png'))
            geometry={'viewport':[w.view.viewport().width(),w.view.viewport().height()], 'transform': [w.view.transform().m11(),w.view.transform().m22()], 'scroll':[w.view.horizontalScrollBar().value(),w.view.verticalScrollBar().value()], 'selected':sorted(map(str,w._selection_keys()))}
            w.view.viewport().update();settle(app)
            full=screen_image(w);full.save(str(args.output.parent/f'{capture_count:02}-{label}-full.png'))
            original_transform=w.view.transform();sx=w.view.horizontalScrollBar().value();sy=w.view.verticalScrollBar().value()
            w._zoom_to_fit();settle(app)
            fitted=screen_image(w);fitted.save(str(args.output.parent/f'{capture_count:02}-{label}-fit.png'))
            w.view.setTransform(original_transform);w.view.horizontalScrollBar().setValue(sx);w.view.verticalScrollBar().setValue(sy);settle(app)
            return {'raw_pixels':image_hash(picture),'full_pixels':image_hash(full),'fit_pixels':image_hash(fitted),'geometry':geometry, 'label':label,'document':canonical,'canvas_pixels':image_hash(screen_image(w)),
                    'render_pixels':image_hash(image),'history_index':w.history._current_index,'rss':rss_bytes()}
        for fixture,mode in [('mixed','public'),('duplex','public'),('connected','public'),('mixed','full'),('mixed','signatures')]:
            doc,provider=make_document(Scenario('journey','select_all',fixture,20 if fixture!='connected' else 12))
            manager=FornaxSessionManager();path=Path(temp)/f'{fixture}-{mode}.fornax'
            if mode=='public':save_public_fornax(doc,path,asset_provider=provider);status=manager.select(path)
            else:save_protected_fornax(doc,path,'journey-test',mode=mode,asset_provider=provider);status=manager.unlock(path,'journey-test')
            w=EditorWindow();w.resize(1280,800)
            try:
                w.load_from_fornax(manager.document(),path=path,mode=status.descriptor.mode,model_id=status.descriptor.model_id,asset_provider=manager.asset,session_manager=manager)
                w._autosave_timer.stop();w.show();w._zoom_to_fit();settle(app)
                states=[snapshot(w,'opened')]
                w.select_all_items();settle(app);w.scene.clearSelection()
                box=min((i for i in w.scene.items() if isinstance(i,DesignerBox) and i.isVisible() and i.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable and not getattr(i,'group_id',None)),key=lambda i:i.layer_id)
                box.setSelected(True);w.canvas_edit.begin(box);cursor=box.text_item.textCursor();cursor.movePosition(QTextCursor.MoveOperation.End);box.text_item.setTextCursor(cursor);w.view.setFocus();settle(app)
                QTest.keyClicks(w.view.viewport(),' etapa final');settle(app)
                assert w.canvas_edit.box is box and box.state.html_content==box.text_item.toHtml()
                w.canvas_edit.finish();w.copy_selected_items();w.paste_copied_items();settle(app)
                copied=persistent_model_document(w._document_with_active_page());w.undo();w.redo();redone=persistent_model_document(w._document_with_active_page())
                if redone!=copied:
                    write_json(args.output.with_name('diagnostico-redo.json'),{'copied':copied,'redone':redone,'fixture':fixture,'mode':mode})
                assert canonical_copy_document(redone,history=True)==canonical_copy_document(copied,history=True)
                states.append(snapshot(w,'edited-pasted-redone'))
                row=next(w.layer_list.item(i) for i in range(1,w.layer_list.count()) if isinstance(w.layer_list.item(i).data(Qt.ItemDataRole.UserRole),DesignerBox) and not getattr(w.layer_list.item(i).data(Qt.ItemDataRole.UserRole),'group_id',None))
                assert w.layer_list.model().moveRows(QModelIndex(),w.layer_list.row(row),1,QModelIndex(),0)
                states.append(snapshot(w,'layer-reordered'))
                if fixture=='duplex':
                    w.switch_model_page('back');states.append(snapshot(w,'back'))
                    w.switch_model_page('front');states.append(snapshot(w,'front-return'))
                if fixture=='connected':
                    w.switch_model_page('organogram')
                    from board_input import move_board_drag
                    groups=w._board_items()[:3];w.scene.clearSelection()
                    for group in groups:group.setSelected(True)
                    w._zoom_to_fit();settle(app)
                    start=w.view.mapFromScene(groups[0].mapToScene(groups[0].rect().center()))
                    QTest.mousePress(w.view.viewport(),Qt.MouseButton.LeftButton,pos=start)
                    assert w.scene.mouseGrabberItem() is groups[0]
                    move_board_drag(w,start,10);settle(app)
                    states.append(snapshot(w,'board-moved'))
                    w.add_new_box();added=w.canvas_edit.box or next(i for i in w.scene.selectedItems() if isinstance(i,DesignerBox))
                    # Alvo geométrico explícito, independente do enquadramento da view.
                    added.setPos(300,100);w.canvas_edit.begin(added)
                    cursor=added.text_item.textCursor();cursor.select(QTextCursor.SelectionType.Document);added.text_item.setTextCursor(cursor)
                    w.view.setFocus();QTest.keyClicks(w.view.viewport(),'Quadro de pessoal');w.canvas_edit.finish();w.save_snapshot();settle(app)
                    states.append(snapshot(w,'board-text-added'))
                    w.scene.clearSelection();w._board_items()[0].setSelected(True)
                    w.change_board_border(cards=True,group=True,width_mm=1.2,radius_mm=2);w.scene.clearSelection()
                    edge=next(i for i in w.scene.items() if isinstance(i,BoardConnectorItem));edge.setSelected(True)
                    w.change_board_connector_style(width_mm=1.3,radius_mm=4,color='#3d668a');settle(app)
                    states.append(snapshot(w,'board-properties'));w.undo();w.redo();states.append(snapshot(w,'board-redone'))
                    w.switch_model_page('front');states.append(snapshot(w,'card-return'))
                w._write_fornax_recovery();wait_recovery(w,app)
                recovered=manager.read_recovery(w.fornax_recovery_path(path),path=path)
                expected=persistent_model_document(w._document_with_active_page())
                expected_assets={ref:sha256(w._save_asset_provider(ref)).hexdigest() for _,_,ref in iter_page_asset_paths(expected)}
                recovered_doc=recovered.document(); recovered_assets={ref:sha256(recovered.asset(ref)).hexdigest() for _,_,ref in iter_page_asset_paths(recovered_doc)}
                expected_canonical=canonical_recovery(canonical_copy_document(expected,history=True),expected_assets)
                recovered_canonical=canonical_recovery(canonical_copy_document(recovered_doc,history=True),recovered_assets)
                if expected_canonical!=recovered_canonical:
                    write_json(args.output.with_name('diagnostico-recovery.json'),{'expected':expected_canonical,'recovered':recovered_canonical,'fixture':fixture,'mode':mode})
                assert expected_canonical==recovered_canonical
                destination=Path(temp)/f'{fixture}-{mode}-copy.fornax'
                from core.fornax_container import open_public_fornax,unlock_fornax
                if mode=='public':
                    save_public_fornax(expected,destination,asset_provider=w._save_asset_provider)
                    opened=open_public_fornax(destination)
                else:
                    save_protected_fornax(expected,destination,'journey-test',mode=status.descriptor.mode,asset_provider=w._save_asset_provider)
                    opened=unlock_fornax(destination,'journey-test')
                loaded=opened.document()
                assert canonical_recovery(canonical_copy_document(expected,history=True),expected_assets)==canonical_recovery(canonical_copy_document(loaded,history=True),{ref:sha256(opened.asset(ref)).hexdigest() for _,_,ref in iter_page_asset_paths(loaded)})
                states.append(snapshot(w,'recovery-and-save'))
                results.append({'fixture':fixture,'mode':mode,'states':states,'saved_and_recovered_equal':True})
                assert not errors,errors
            finally:
                close_window(w,app);wait_recovery(w,app);manager.close();settle(app)
                if mode!='public' and isValid(w):assert w._model_document is None
    assert not errors,errors
    meta=environment()
    meta['theme']=args.theme
    if args.reference:
        for name in list(meta['product_sha256']):
            file=args.reference/name
            if file.is_file():meta['product_sha256'][name]=sha256(file.read_bytes()).hexdigest()
    write_json(args.output,{'theme':args.theme,'reference':str(args.reference) if args.reference else None,'journeys':results,'callback_errors':errors,'environment':meta})
    print('5 fluxos completos: OK',flush=True)

if __name__=='__main__':
    try:main()
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
