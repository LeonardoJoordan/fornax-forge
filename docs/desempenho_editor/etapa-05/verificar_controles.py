"""Confere comandos de camadas antigas e novas após colagem, sem dados pessoais."""
import argparse
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tests/performance')]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    with TemporaryDirectory(prefix='fornax-copy-controls-') as root:
        os.environ.update(QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=root+'/config',
                          XDG_DATA_HOME=root+'/data',XDG_CACHE_HOME=root+'/cache')
        from PySide6.QtWidgets import QPushButton
        from PySide6.QtCore import Qt,QEvent
        from shiboken6 import isValid
        from test_editor_performance_contracts import PerformanceContractsTest
        from features.editor.canvas_items import DesignerBox
        case=PerformanceContractsTest();case.setUpClass();case.setUp()
        try:
            w=case.editor('simple',20)
            original=next(i for i in w.scene.items() if isinstance(i,DesignerBox) and i.layer_id==20)
            def row(item):
                return next(w.layer_list.item(n) for n in range(w.layer_list.count())
                            if w.layer_list.item(n).data(Qt.ItemDataRole.UserRole) is item)
            original_widget=w.layer_list.itemWidget(row(original));original_id=original.layer_id
            original.setSelected(True);w.copy_selected_items();w.paste_copied_items()
            case.app.sendPostedEvents(None,QEvent.Type.DeferredDelete);case.app.processEvents()
            existing=next(i for i in w.scene.items() if isinstance(i,DesignerBox) and i.layer_id==original_id)
            copied=next(i for i in w.scene.selectedItems() if isinstance(i,DesignerBox))
            widget=w.layer_list.itemWidget(row(existing))
            widget.findChildren(QPushButton)[0].click()
            assert not existing.isVisible() and copied.isVisible()
            widget.findChildren(QPushButton)[-1].click()
            assert not bool(existing.flags() & existing.GraphicsItemFlag.ItemIsMovable)
            assert bool(copied.flags() & copied.GraphicsItemFlag.ItemIsMovable)
            w.layer_list.itemWidget(row(copied)).findChildren(QPushButton)[0].click()
            assert not copied.isVisible() and not existing.isVisible()
            assert not case.errors
            result={'old_object_retained':isValid(original) and original is existing,
                    'old_widget_retained':isValid(original_widget) and original_widget is widget,
                    'existing_visibility_button':True,'existing_lock_button':True,
                    'copied_visibility_button':True,'qt_callback_errors':0}
            args.output.write_text(json.dumps(result,indent=2)+'\n')
            print(json.dumps(result))
        finally:
            if not case.doCleanups():raise AssertionError('Falha na limpeza do editor.')
    return 0

if __name__=='__main__':raise SystemExit(main())
