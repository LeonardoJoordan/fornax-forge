"""Same atomic-publication contracts against the pre-stage module and current one."""
import importlib.util
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication
from core.model_document import normalize_model_document
from core.file_transactions import file_lock
import core.fornax_container as container

reference = os.environ.get('FORNAX_REFERENCE_CONTAINER')
if reference:
    spec = importlib.util.spec_from_file_location('fornax_reference_container', reference)
    container = importlib.util.module_from_spec(spec);sys.modules[spec.name] = container;spec.loader.exec_module(container)


class RecoveryPackagePublicationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        image=QImage(10,10,QImage.Format.Format_ARGB32);image.fill(QColor('red'));self.asset=self.root/'signature.png';self.assertTrue(image.save(str(self.asset)))
        self.document=normalize_model_document({'name':'Inicial','canvas_size':{'w':300,'h':300},'boxes':[],
          'signatures':[{'path':str(self.asset),'x':30,'y':30,'width':50,'height':50,'signature_id':'director'}],
          'protection_preferences':{'public_signatures_acknowledged':True}})
        self.path=self.root/'model.fornax'
        container.save_public_fornax(self.document,self.path)
        self.old=self.path.read_bytes();self.document['name']='Atualizado'

    def assert_clean(self):
        self.assertFalse(list(self.root.glob('*.pending-*')));self.assertFalse(list(self.root.glob('*.backup-*')))

    def test_public_save_has_valid_previous_backup_and_exact_asset(self):
        container.save_public_fornax(self.document,self.path)
        self.assertEqual(self.path.with_name(self.path.name+'.bak').read_bytes(),self.old)
        opened=container.open_public_fornax(self.path);self.assertEqual(opened.document()['name'],'Atualizado')
        self.assertIn(self.asset.read_bytes(),[opened.asset(r) for r in opened.asset_references]);self.assert_clean()

    def test_same_protected_credentials_keep_decryptable_previous_revision(self):
        for mode in (container.SIGNATURES_MODE,container.FULL_MODE):
            with self.subTest(mode=mode):
                path=self.root/(mode+'.fornax');container.save_protected_fornax(self.document,path,'senha-teste',mode=mode)
                old=path.read_bytes();doc=dict(self.document,name='Outra revisão')
                opened,key=container._unlock_fornax_with_key(path,'senha-teste');descriptor=opened.descriptor
                container.save_protected_fornax_with_key(doc,path,key,descriptor.salt,mode=mode,model_id=descriptor.model_id)
                backup=path.with_name(path.name+'.bak');self.assertEqual(backup.read_bytes(),old)
                self.assertEqual(container.unlock_fornax(backup,'senha-teste').document()['name'],'Atualizado')
                self.assertEqual(container.unlock_fornax(path,'senha-teste').document()['name'],'Outra revisão');self.assert_clean()

    def test_protection_upgrade_does_not_leave_public_backup(self):
        container.save_protected_fornax(self.document,self.path,'senha-nova',mode=container.FULL_MODE)
        backup=self.path.with_name(self.path.name+'.bak');self.assertEqual(backup.read_bytes(),self.path.read_bytes())
        for path in (self.path,backup):
            self.assertEqual(container.inspect_fornax(path).mode,container.FULL_MODE)
            self.assertEqual(container.unlock_fornax(path,'senha-nova').document()['name'],'Atualizado')
            with zipfile.ZipFile(path) as archive:self.assertEqual(set(archive.namelist()),{'manifest.json','protected.bin'})
        self.assert_clean()

    def test_password_change_does_not_leave_backup_with_old_credentials(self):
        container.save_protected_fornax(self.document,self.path,'senha-antiga',mode=container.FULL_MODE)
        container.reencrypt_fornax(self.path,'senha-antiga',self.path,'senha-nova',mode=container.FULL_MODE)
        for path in (self.path,self.path.with_name(self.path.name+'.bak')):
            self.assertEqual(container.unlock_fornax(path,'senha-nova').document()['name'],'Atualizado')
            with self.assertRaises(container.FornaxPasswordError):container.unlock_fornax(path,'senha-antiga')
        self.assert_clean()

    def test_staged_verification_failure_preserves_previous_file(self):
        with patch.object(container,'open_public_fornax',side_effect=container.FornaxFormatError('Falha de verificação')):
            with self.assertRaises(container.FornaxFormatError):container.save_public_fornax(self.document,self.path)
        self.assertEqual(self.path.read_bytes(),self.old);self.assert_clean()

    def test_replace_permission_failure_preserves_previous_file_and_valid_backup(self):
        replace=os.replace
        def deny(source,target):
            if Path(target)==self.path:raise PermissionError('Destino sem permissão')
            return replace(source,target)
        with patch.object(container.os,'replace',side_effect=deny):
            with self.assertRaises(PermissionError):container.save_public_fornax(self.document,self.path)
        self.assertEqual(self.path.read_bytes(),self.old)
        self.assertEqual(container.open_public_fornax(self.path.with_name(self.path.name+'.bak')).document()['name'],'Inicial');self.assert_clean()

    def test_file_lock_blocks_concurrent_save(self):
        with file_lock(self.path.with_name('.'+self.path.name+'.write.lock')):
            with self.assertRaises(OSError):container.save_public_fornax(self.document,self.path)
        self.assertEqual(self.path.read_bytes(),self.old);self.assert_clean()

    def test_external_destination_change_during_verification_is_preserved(self):
        other=self.root/'external.fornax';container.save_public_fornax(dict(self.document,name='Externo'),other);external=other.read_bytes()
        original=container.open_public_fornax
        def verify(path):
            result=original(path)
            if '.pending-' in str(path):self.path.write_bytes(external)
            return result
        with patch.object(container,'open_public_fornax',side_effect=verify):
            with self.assertRaises(container.FornaxFormatError):container.save_public_fornax(self.document,self.path)
        self.assertEqual(self.path.read_bytes(),external);self.assert_clean()

    def test_fsync_failure_does_not_publish_unconfirmed_file(self):
        with patch.object(container.os,'fsync',side_effect=OSError('Falha de fsync')):
            with self.assertRaises(OSError):container.save_public_fornax(self.document,self.path)
        self.assertEqual(self.path.read_bytes(),self.old);self.assert_clean()

    def test_external_change_after_backup_publication_is_preserved(self):
        other=self.root/'external.fornax';container.save_public_fornax(dict(self.document,name='Externo'),other);external=other.read_bytes()
        sync=container._fsync_directory
        def changed(directory):
            sync(directory)
            self.path.write_bytes(external)
        with patch.object(container,'_fsync_directory',side_effect=changed):
            with self.assertRaises(container.FornaxFormatError):container.save_public_fornax(self.document,self.path)
        self.assertEqual(self.path.read_bytes(),external);self.assert_clean()

if __name__=='__main__':unittest.main()
