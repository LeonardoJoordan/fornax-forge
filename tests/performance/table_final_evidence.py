"""Etapa 08: capturas sintéticas por idioma, tema, zoom e escala de tela."""
import argparse
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    with TemporaryDirectory(prefix='fornax-table-final-') as directory:
        for key,folder in [('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),('APPDATA','config')]:
            os.environ[key]=directory+'/'+folder
        from PySide6.QtCore import QCoreApplication,QEvent,QSettings
        from PySide6.QtGui import QFont,QFontInfo
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from shiboken6 import isValid
        from core.ui_font import install_ui_font,DOCUMENT_FONT_FAMILY
        from core.i18n import initialize_i18n
        from core.themes import theme_manager
        from core.table_model import new_table,merge_cells,set_cell_html,format_cells
        from core.model_document import normalize_model_document,add_model_table
        from features.editor.editor_window import EditorWindow
        from features.editor.table_item import TableItem
        from features.help.help_dialog import HelpDialog
        app=QApplication([]);app.setQuitOnLastWindowClosed(False);install_ui_font(app)
        errors=[]
        def hook(typ,value,tb):errors.append(typ.__name__);sys.__excepthook__(typ,value,tb)
        sys.excepthook=hook
        table=new_table(6,4,width=1000,height=620);table.update(x=70,y=70)
        table=merge_cells(table,0,0,0,3);table=set_cell_html(table,0,0,'<p><b>BOLETIM ESCOLAR</b></p>')
        table=format_cells(table,0,0,0,3,{'fill_color':'#24576b','font_color':'#ffffff','align':'center'})
        for r,values in enumerate((('Disciplina','1º período','2º período','Resultado'),
                                   ('Português','{portugues_1}','{portugues_2}','{portugues_resultado}'),
                                   ('Matemática','{matematica_1}','{matematica_2}','{matematica_resultado}'),
                                   ('Ciências','{ciencias_1}','{ciencias_2}','{ciencias_resultado}'),
                                   ('História','{historia_1}','{historia_2}','{historia_resultado}')),1):
            for c,value in enumerate(values):table=set_cell_html(table,r,c,'<p>'+value+'</p>')
        table=format_cells(table,1,0,5,3,{'font_size':8})
        table=format_cells(table,2,0,2,0,{'font_family':'DejaVu Sans'})
        source=add_model_table(normalize_model_document({'canvas_size':{'w':1140,'h':800}}),table)
        settings=QSettings(directory+'/locale.ini',QSettings.Format.IniFormat)
        captures=[]
        for locale in ('pt_BR','en_US','es_ES'):
            settings.setValue('language/locale',locale);initialize_i18n(app,settings)
            w=EditorWindow()
            try:
                w._load_document_into_scene(source);w.resize(1440,1000);w.show()
                item=next(i for i in w.scene.items() if isinstance(i,TableItem))
                item.setSelected(True);item.select_cell(1,0);item.select_cell(2,3,extend=True)
                for theme in ('dark','light'):
                    theme_manager().select(theme)
                    w._text_section.header.setChecked(True);w._table_section.header.setChecked(True)
                    app.processEvents();QTest.qWait(60)
                    for zoom in (.5,1.5):
                        w.view.resetTransform();w.view.scale(zoom,zoom);w.view.centerOn(item);app.processEvents()
                        name=f'{locale}-{theme}-zoom-{zoom}.png'
                        assert w.grab().save(str(args.output/name))
                        captures.append(name)
                    assert w.table_panel.grab().save(str(args.output/f'panel-{locale}-{theme}.png'))
                    if locale=='pt_BR':
                        help_window=HelpDialog(w);help_window.open_topic('TBL-14');help_window.show();app.processEvents()
                        assert help_window.grab().save(str(args.output/f'help-{theme}.png'))
                        help_window.close();help_window.deleteLater();app.processEvents()
            finally:
                w._finish_page_interaction();w._recovered_unsaved=False
                w._last_saved_state=w.get_current_scene_state();w._last_saved_document_state=w._capture_document_history_state()
                w.close();app.processEvents()
                if isValid(w):w.deleteLater()
                QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        assert not errors,errors
        metadata={'backend':app.platformName(),'scale':os.environ.get('QT_SCALE_FACTOR','1'),
                  'ui_font':app.font().key(),'document_fonts':{family:QFontInfo(QFont(family)).family()
                   for family in (DOCUMENT_FONT_FAMILY,'DejaVu Sans')},'zoom':[.5,1.5],
                  'languages':['pt_BR','en_US','es_ES'],'themes':['dark','light'],
                  'editor_captures':captures,'callback_errors':errors}
        (args.output/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
        print('Capturas completas: idiomas, temas, zooms e ajuda; sem erros de callbacks.')


if __name__=='__main__':main()
