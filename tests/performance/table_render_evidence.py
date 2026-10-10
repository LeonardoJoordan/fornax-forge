"""Dados e exportação sintéticos da etapa 03; não altera modelos da biblioteca."""
from PySide6.QtCore import QSizeF,QMarginsF
from PySide6.QtGui import QPdfWriter,QPageSize,QPainter
from core.table_model import new_table,set_cell_html,format_cells,merge_cells
from core.model_document import add_model_table,persistent_model_document


def specimen_table():
    table=new_table(4,4,width=1440,height=800,name='Quadro de informações')
    table.update(x=30,y=30)
    table['style']['font_size']=9.5
    table=merge_cells(table,0,0,0,3)
    table=set_cell_html(table,0,0,'<p><b>FORNAX · QUADRO DE INFORMAÇÕES</b></p>')
    table=format_cells(table,0,0,0,3,{'fill_color':'#203746','font_color':'#ffffff',
                      'font_size':14,'align':'center','vertical_align':'center'})
    table=set_cell_html(table,1,0,'<p><b>{nome}</b></p><p><i>Participante</i></p>')
    table=set_cell_html(table,1,1,'<p>Primeira linha<br>Segunda linha</p>')
    table=set_cell_html(table,1,2,'<p>Centralizado</p>')
    table=format_cells(table,1,2,1,2,{'align':'center','vertical_align':'center'})
    table=set_cell_html(table,1,3,'<p><u>À direita / base</u></p>')
    table=format_cells(table,1,3,1,3,{'align':'right','vertical_align':'bottom'})
    table=set_cell_html(table,2,0,'<p>Nota: {nota}</p><p>|Detalhe: {detalhe}|</p>')
    table=set_cell_html(table,2,1,'<p>SEM_QUEBRA_'+'X'*50+'</p>')
    table=format_cells(table,2,1,2,1,{'wrap':False,'fill_color':'#fff1dc','font_color':'#805b29'})
    table=merge_cells(table,2,2,3,3)
    table=set_cell_html(table,2,2,'<p><b>Área mesclada 2 × 2</b></p><p>Textos e contornos próprios.</p>')
    table=format_cells(table,2,2,3,3,{'fill_color':'#e1ecf1','align':'center','vertical_align':'center'})
    table=set_cell_html(table,3,0,'<p>'+'<br>'.join(f'Linha {i}' for i in range(1,9))+'</p>')
    table=set_cell_html(table,3,1,'<p><b>Ênfase</b> e <i>itálico</i><br>Ação, ç, Ω, 𝄞</p>')
    return table


def document(table=None):
    base=persistent_model_document(dict(canvas_size={'w':1500,'h':860},target_w_mm=127,
                  target_h_mm=860*25.4/300,boxes=[],images=[],signatures=[],shapes=[],placeholders=[]))
    return add_model_table(base,table or specimen_table())


def vector_pdf(renderer,path,values=None,resolution=96):
    writer=QPdfWriter(str(path))
    writer.setResolution(resolution)
    canvas=renderer.tpl['canvas_size']
    writer.setPageSize(QPageSize(QSizeF(canvas['w']*25.4/300,canvas['h']*25.4/300),
        QPageSize.Unit.Millimeter,'',QPageSize.SizeMatchPolicy.ExactMatch))
    writer.setPageMargins(QMarginsF(0,0,0,0))
    painter=QPainter(writer)
    if not painter.isActive():raise OSError('Não abriu PDF sintético')
    try:
        # Unidades físicas, como no PDF do organograma. O writer quantiza a
        # página em pontos/pixels: ajustar pela altura inteira comprime o
        # desenho, embora o texto deva conservar suas medidas em milímetros.
        painter.scale(resolution/300,resolution/300)
        renderer.paint_card(painter,values,values)
    finally:painter.end()
    del writer
