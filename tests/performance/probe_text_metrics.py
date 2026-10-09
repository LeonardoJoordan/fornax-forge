"""Conta consultas nativas de fonte sem misturá-las aos tempos do benchmark."""
import json,os,sys,argparse
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtGui import QTextCursor,QFontMetrics
from PySide6.QtWidgets import QApplication
from core.ui_font import install_ui_font
from core.text_layout import build_document,text_geometry
from text_cases import rich_sample

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    app=QApplication.instance() or QApplication([]);install_ui_font(app);results={}
    for name,html,width in [('plain','<p>'+('Texto ágil. '*180)+'</p>',1000),('mixed',rich_sample(True),1000),('wide','<p>'+('Texto ágil. '*180)+'</p>',30000)]:
        counts={'cursor_font_queries':0,'font_metrics':0};data=dict(w=width,h=3000,rich_text_version=1);doc=build_document(data,html)
        class Probe:
            def __init__(self,*args):self.cursor=QTextCursor(*args)
            def setPosition(self,*args):return self.cursor.setPosition(*args)
            def charFormat(self):counts['cursor_font_queries']+=1;return self.cursor.charFormat()
        def metric(*args):counts['font_metrics']+=1;return QFontMetrics(*args)
        with patch('core.text_layout.QTextCursor',Probe),patch('core.text_layout.QFontMetrics',side_effect=metric):
            geometry=text_geometry(doc,data)
        results[name]={**counts,'geometry':geometry}
    args.output.write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results))
if __name__=='__main__':raise SystemExit(main())
