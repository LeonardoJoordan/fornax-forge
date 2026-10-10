"""Capturas locais de um boletim sintético; não lê modelos pessoais."""
import argparse
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--docking', action='store_true', help='Capturar também as quatro posições e os destinos da barra.')
    args = parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    with TemporaryDirectory(prefix='fornax-table-visual-') as directory:
        for key,subdir in (('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache')):
            os.environ[key] = directory+'/'+subdir
        from PySide6.QtCore import QCoreApplication,QEvent
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from core.ui_font import install_ui_font
        from core.themes import theme_manager
        from core.table_model import new_table,merge_cells,set_cell_html,format_cells
        from core.model_document import normalize_model_document,add_model_table
        from features.editor.editor_window import EditorWindow
        from features.editor.table_item import TableItem
        app = QApplication([]);app.setQuitOnLastWindowClosed(False);install_ui_font(app)
        errors = []
        def hook(typ,value,tb):
            errors.append(str(value));sys.__excepthook__(typ,value,tb)
        sys.excepthook = hook
        table = new_table(6,4,width=1000,height=620)
        table.update(x=70,y=70)
        table = format_cells(table,0,0,5,3,{'font_size':10})
        table = merge_cells(table,0,0,0,3)
        table = set_cell_html(table,0,0,'<p><b>BOLETIM ESCOLAR</b></p>')
        table = format_cells(table,0,0,0,3,{'fill_color':'#24576b','font_color':'#ffffff','align':'center'})
        for r,values in enumerate((('Disciplina','1º período','2º período','Resultado'),
                                  ('Português','{nota_1}','{nota_2}','{resultado}'),
                                  ('Matemática','{nota_3}','{nota_4}','{resultado}'),
                                  ('Ciências','{nota_5}','{nota_6}','{resultado}'),
                                  ('História','{nota_7}','{nota_8}','{resultado}')),1):
            for c,value in enumerate(values):table = set_cell_html(table,r,c,'<p>'+value+'</p>')
        source = add_model_table(normalize_model_document({'canvas_size':{'w':1140,'h':800}}),table)
        window = EditorWindow()
        try:
            window._load_document_into_scene(source);window.resize(1440,1000);window.show()
            root = next(i for i in window.scene.items() if isinstance(i,TableItem))
            root.setSelected(True);root.select_cell(1,0);root.select_cell(2,3,extend=True)
            for theme in ('dark','light'):
                theme_manager().select(theme)
                window._text_section.header.setChecked(True);window._table_section.header.setChecked(True)
                app.processEvents();QTest.qWait(220);window._zoom_to_fit();app.processEvents()
                window.grab().save(str(args.output/('editor-'+theme+'.png')))
                window.table_panel.grab().save(str(args.output/('painel-tabela-'+theme+'.png')))
                if args.docking:
                    bar = window.table_controller.floating_bar
                    for side in ('top', 'left', 'right', 'bottom'):
                        bar.dock_side = side
                        bar.reposition()
                        for _ in range(4):app.processEvents()
                        window.grab().save(str(args.output/('barra-'+side+'-'+theme+'.png')))
                        bar.toggle_collapsed()
                        for _ in range(4):app.processEvents()
                        window.grab().save(str(args.output/('barra-recolhida-'+side+'-'+theme+'.png')))
                        bar.toggle_collapsed()
                    bar.dock_side = 'top';bar.reposition()
                    bar.begin_dock_drag(bar.grip.mapToGlobal(bar.grip.rect().center()))
                    for _ in range(4):app.processEvents()
                    window.grab().save(str(args.output/('destinos-'+theme+'.png')))
                    bar.end_dock_drag(restore_focus=False)
                    bar.toggle_collapsed()
                    bar.begin_dock_drag(bar.grip.mapToGlobal(bar.grip.rect().center()))
                    for _ in range(4):app.processEvents()
                    window.grab().save(str(args.output/('destinos-recolhida-'+theme+'.png')))
                    bar.end_dock_drag(restore_focus=False)
                    bar.toggle_collapsed()
                    # Tabela menor que as ferramentas: os destaques devem encolher.
                    window.view.scale(.4, .4)
                    window.view.centerOn(root.sceneBoundingRect().center())
                    for _ in range(4):app.processEvents()
                    bar.reposition()
                    for collapsed in (False, True):
                        if bar.collapsed != collapsed:
                            bar.toggle_collapsed()
                        bar.begin_dock_drag(bar.grip.mapToGlobal(bar.grip.rect().center()))
                        for _ in range(4):app.processEvents()
                        state = 'recolhida' if collapsed else 'aberta'
                        window.grab().save(str(args.output/('destinos-tabela-pequena-'+state+'-'+theme+'.png')))
                        bar.end_dock_drag(restore_focus=False)
                    bar.toggle_collapsed()
                    window._zoom_to_fit()
                    for _ in range(4):app.processEvents()
                    for side in ('top', 'left', 'right', 'bottom'):
                        bar.dock_side = side;bar.reposition()
                        for axis in ('align', 'vertical_align'):
                            bar.popup(bar.buttons[axis], bar.alignment_menus[axis])
                            for _ in range(4):app.processEvents()
                            menu = next(m for m in bar.menus if m.isVisible())
                            menu.grab().save(str(args.output/('alinhamento-'+axis+'-'+side+'-'+theme+'.png')))
                            menu.close()
        finally:
            window._finish_page_interaction();window._recovered_unsaved=False
            window._last_saved_state=window.get_current_scene_state()
            window._last_saved_document_state=window._capture_document_history_state()
            window.close();window.deleteLater();app.processEvents()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        if errors:raise AssertionError(errors)
        print('Capturas dos temas dark/light salvas; sem erros de callbacks.')


if __name__ == '__main__':main()
