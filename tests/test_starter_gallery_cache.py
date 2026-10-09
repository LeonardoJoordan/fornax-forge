"""Contratos da galeria e invalidação das miniaturas, sem tocar na biblioteca pessoal."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import QApplication, QMainWindow
from core.starter_templates import starter_catalog, model_from_starter
from core.themes import theme_manager
from features.editor import starter_dialog as module
from test_organogram import card_document
from test_editor_visual_cache import image_bytes


def pixels(dialog):
    return [sha256(bytes(dialog.gallery.item(i).icon().pixmap(320,232).toImage().constBits())).hexdigest()
            for i in range(dialog.gallery.count())]


class GalleryContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp=TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.parent=QMainWindow(); self.addCleanup(lambda:self.parent.deleteLater() if __import__('shiboken6').isValid(self.parent) else None)
        self.card=card_document(); self.dialogs=[]
        self.addCleanup(self.cleanup_dialogs)

    def cleanup_dialogs(self):
        for dialog in self.dialogs:
            if __import__('shiboken6').isValid(dialog): dialog.reject(); dialog.deleteLater()
        self.app.sendPostedEvents(); self.app.processEvents()

    def dialog(self,kind='organogram',document=None):
        from itertools import count
        from uuid import UUID
        ids=count(1)
        with patch('core.organogram.uuid4',side_effect=lambda:UUID(int=next(ids))):
            result=module.StarterDialog(kind,self.parent,document=document or self.card)
        self.dialogs.append(result); return result

    def test_catalog_order_titles_dimensions_and_blank_are_preserved(self):
        for kind in ('model','organogram'):
            dialog=self.dialog(kind); catalog=starter_catalog(kind)
            self.assertEqual(dialog.gallery.count(),6)
            self.assertIsNone(dialog.gallery.item(0).data(Qt.ItemDataRole.UserRole))
            self.assertEqual(dialog.gallery.currentRow(),0)
            for index,template in enumerate(catalog,1):
                item=dialog.gallery.item(index)
                self.assertEqual(item.data(Qt.ItemDataRole.UserRole),template.id)
                self.assertTrue(item.data(module.TEMPLATE_DIMENSIONS_ROLE))
                self.assertFalse(item.icon().isNull())

    def test_reopening_preserves_all_thumbnail_pixels(self):
        for kind in ('model','organogram'):
            self.assertEqual(pixels(self.dialog(kind)),pixels(self.dialog(kind)))

    def test_grid_changes_dimensions_and_restores_original_preview(self):
        dialog=self.dialog(); row=next(i for i in range(1,6) if dialog._templates[dialog.gallery.item(i).data(Qt.ItemDataRole.UserRole)].configurable_grid)
        dialog.gallery.setCurrentRow(row); original=pixels(dialog)[row]
        dimensions=dialog.gallery.item(row).data(module.TEMPLATE_DIMENSIONS_ROLE)
        dialog.columns.setValue(2); dialog.rows.setValue(3); dialog._update_grid_preview()
        self.assertNotEqual(dialog.gallery.item(row).data(module.TEMPLATE_DIMENSIONS_ROLE),dimensions)
        dialog.columns.setValue(5); dialog.rows.setValue(4); dialog._update_grid_preview()
        self.assertEqual(pixels(dialog)[row],original)

    def test_card_edit_updates_art_without_modifying_input(self):
        original=deepcopy(self.card); first=pixels(self.dialog())
        changed=deepcopy(self.card); changed['pages'][0]['shapes'][0]['fill_color']='#ff0000'
        self.assertNotEqual(first,pixels(self.dialog(document=changed)))
        self.assertEqual(self.card,original)

    def test_theme_preserves_artwork_colors(self):
        old=theme_manager().theme_id
        try:
            theme_manager().select('dark'); first=pixels(self.dialog())
            theme_manager().select('light'); self.assertEqual(first,pixels(self.dialog()))
        finally: theme_manager().select(old)

    def test_accept_produces_independent_documents_and_blank_still_works(self):
        for kind in ('model','organogram'):
            first=self.dialog(kind); first.gallery.setCurrentRow(1); first.accept()
            second=self.dialog(kind); second.gallery.setCurrentRow(1); second.accept()
            first.result_document['pages'][0]['boxes'][0]['html']='changed'
            self.assertNotEqual(first.result_document['pages'],second.result_document['pages'])
            blank=self.dialog(kind); blank.accept()
            if kind=='model': self.assertIsNone(blank.result_document)
            else: self.assertEqual(blank.result_document['organogram']['groups'],[])


class GalleryCacheChecks(GalleryContracts):
    # Não repetir os contratos herdados no runner; loadTestsFromTestCase seleciona métodos locais.
    def test_reopen_and_grid_return_do_not_render_again(self):
        with patch.object(module,'starter_thumbnail',wraps=module.starter_thumbnail) as render:
            first=self.dialog(); self.assertEqual(render.call_count,5)
            self.dialog(); self.assertEqual(render.call_count,5)
            row=next(i for i in range(1,6) if first._templates[first.gallery.item(i).data(Qt.ItemDataRole.UserRole)].configurable_grid)
            first.gallery.setCurrentRow(row); first._update_grid_preview(); self.assertEqual(render.call_count,5)
            first.rows.setValue(3); first._update_grid_preview(); self.assertEqual(render.call_count,6)
            first.rows.setValue(4); first._update_grid_preview(); self.assertEqual(render.call_count,6)

    def test_same_size_and_timestamp_asset_replacement_changes_pixels(self):
        path=self.root/'photo.bmp'; red,blue=image_bytes('red'),image_bytes('blue')
        self.assertEqual(len(red),len(blue)); path.write_bytes(red); stamp=path.stat()
        self.card['pages'][0]['images']=[{'object_id':'photo','layer_id':4,'path':str(path),'x':0,'y':0,'width':400,'height':500}]
        self.card['pages'][0]['layer_order'].append('photo')
        first=pixels(self.dialog()); path.write_bytes(blue); os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        self.assertNotEqual(first,pixels(self.dialog()))

    def test_content_of_preset_not_its_name_identifies_preview(self):
        templates=list(starter_catalog('organogram')); target=next(t for t in templates if t.path.suffix=='.json')
        from dataclasses import replace
        source=self.root/'preset.json'; source.write_bytes(target.path.read_bytes())
        templates[templates.index(target)]=replace(target,path=source)
        with patch.object(module,'starter_catalog',return_value=templates):
            first=pixels(self.dialog())
            import json
            data=json.loads(source.read_text()); data['title']['text']='Novo título do exemplo'
            source.write_text(json.dumps(data))
            self.assertNotEqual(first,pixels(self.dialog()))

    def test_font_change_and_database_change_invalidate(self):
        with patch.object(module,'starter_thumbnail',wraps=module.starter_thumbnail) as render:
            self.dialog(); old=self.app.font()
            try:
                font=QFont(old); font.setPointSize(old.pointSize()+1); self.app.setFont(font)
                self.dialog(); self.assertEqual(render.call_count,10)
                self.app.fontDatabaseChanged.emit(); self.dialog(); self.assertEqual(render.call_count,15)
            finally:self.app.setFont(old)

    def test_bounded_memory_eviction_and_copies(self):
        from features.editor.starter_cache import StarterPreviewCache
        cache=StarterPreviewCache(self.parent,limit=320*320*4)
        # Somente um resultado cabe; chamadas devolvem uma cópia implícita.
        from PySide6.QtGui import QPixmap
        calls=[]
        def render(doc,provider):
            calls.append(1); pixmap=QPixmap(320,320); pixmap.fill(QColor('red')); return pixmap
        first=cache.preview(self.card,None,['one'],render); first.fill(QColor('blue'))
        self.assertEqual(cache.preview(self.card,None,['one'],render).toImage().pixelColor(0,0),QColor('red'))
        cache.preview(self.card,None,['two'],render); cache.preview(self.card,None,['one'],render)
        self.assertEqual(len(calls),3); self.assertLessEqual(cache.pixels.retained_bytes,cache.pixels.limit)
        cache.clear(); self.assertEqual(cache.pixels.retained_bytes,0)

    def test_assets_shared_between_the_five_structures_are_read_once(self):
        self.card['pages'][0]['images']=[{'object_id':'photo','layer_id':4,'path':'photo','x':0,'y':0,'width':400,'height':500}]
        self.card['pages'][0]['layer_order'].append('photo')
        provider=__import__('unittest.mock',fromlist=['Mock']).Mock(return_value=image_bytes('red'))
        self.parent._fornax_asset_provider=provider
        self.dialog(); self.assertEqual(provider.call_count,1)

    def test_provider_asset_replacement_invalidates_and_new_document_discards_old_entries(self):
        self.card['pages'][0]['images']=[{'object_id':'photo','layer_id':4,'path':'photo','x':0,'y':0,'width':400,'height':500}]
        self.card['pages'][0]['layer_order'].append('photo')
        self.parent._fornax_asset_provider=lambda _:image_bytes('red')
        first=pixels(self.dialog()); self.parent._fornax_asset_provider=lambda _:image_bytes('blue')
        self.assertNotEqual(first,pixels(self.dialog()))
        old_keys=set(self.parent._starter_preview_cache.pixels.entries)
        changed=deepcopy(self.card); changed['name']='Documento distinto'
        self.dialog(document=changed)
        self.assertTrue(old_keys.isdisjoint(self.parent._starter_preview_cache.pixels.entries))

    def test_protected_expiration_purges_pixels_open_dialog_and_forbids_accept(self):
        from core.fornax_container import save_protected_fornax,FULL_MODE
        from core.fornax_session import FornaxSessionManager
        path=self.root/'protected.fornax'
        save_protected_fornax(self.card,path,password='gallery-test',mode=FULL_MODE)
        clock=[0]; manager=FornaxSessionManager(grace_seconds=1,clock=lambda:clock[0]); self.addCleanup(manager.close)
        manager.select(path); manager.unlock(path,'gallery-test')
        self.parent._fornax_path=path; self.parent._fornax_mode=FULL_MODE
        self.parent._fornax_session_manager=manager
        self.parent._fornax_asset_provider=manager.asset
        dialog=self.dialog(); cache=self.parent._starter_preview_cache
        self.assertGreater(cache.pixels.retained_bytes,0)
        manager.leave_active(); clock[0]=2; manager.expire_due()
        self.assertFalse(cache.check_authorization())
        self.assertEqual(cache.pixels.retained_bytes,0); self.assertIsNone(dialog.document)
        self.assertTrue(all(dialog.gallery.item(i).icon().isNull() for i in range(6)))
        dialog.accept(); self.assertIsNone(dialog.result_document)
        manager.select(path); manager.unlock(path,'gallery-test')
        self.assertFalse(self.dialog().gallery.item(1).icon().isNull())

    def test_missing_protected_authorization_does_not_render_or_accept_blank(self):
        self.parent._fornax_mode='full'
        with patch.object(module,'starter_thumbnail',wraps=module.starter_thumbnail) as render:
            dialog=self.dialog(); dialog.accept()
            self.assertEqual(render.call_count,0); self.assertIsNone(dialog.result_document)

    def test_close_releases_dialog_payloads_and_owner_destruction_releases_cache(self):
        from PySide6.QtCore import QEvent
        dialog=self.dialog(); cache=self.parent._starter_preview_cache
        dialog.reject(); self.assertIsNone(dialog.document); self.assertIsNone(dialog._preview_assets)
        self.assertTrue(all(dialog.gallery.item(i).icon().isNull() for i in range(6)))
        self.parent.deleteLater(); self.app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.assertEqual(cache.pixels.retained_bytes,0)


    def test_result_transfer_releases_hidden_dialog_and_keeps_editable_copy(self):
        from PySide6.QtCore import QEvent
        from shiboken6 import isValid
        dialog=self.dialog(); dialog.gallery.setCurrentRow(1); dialog.accept()
        result,provider=dialog.take_result()
        self.assertTrue(result['organogram']['groups']); self.assertIsNone(dialog.result_document)
        self.app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.assertFalse(isValid(dialog))
        result['pages'][0]['boxes'][0]['html']='independent'
        self.assertNotEqual(result['pages'],self.card['pages'])

    def test_file_changed_during_loading_is_not_cached_under_the_new_content(self):
        dialog=self.dialog(); template=starter_catalog('organogram')[0]
        from dataclasses import replace
        source=self.root/'changing.json'; source.write_bytes(template.path.read_bytes())
        template=replace(template,path=source)
        cache=self.parent._starter_preview_cache; count=len(cache.pixels.entries)
        preview=__import__('core.starter_templates',fromlist=['organogram_from_starter']).organogram_from_starter(self.card,template)
        with patch.object(module,'starter_thumbnail',wraps=module.starter_thumbnail) as render:
            dialog._cached_thumbnail(preview,None,template,source_stamp='different')
            self.assertEqual(render.call_count,1); self.assertEqual(len(cache.pixels.entries),count)



def load_tests(loader,tests,pattern):
    suite=loader.loadTestsFromTestCase(GalleryContracts)
    if os.environ.get('FORNAX_GALLERY_CACHE_CHECKS')=='1':
        suite.addTests(GalleryCacheChecks(name) for name in GalleryCacheChecks.__dict__ if name.startswith('test_'))
    return suite
