"""Texto sintético rico, com acentos, fontes mistas e offsets UTF-16."""
from core.model_document import normalize_model_document


def rich_sample(long=False):
    paragraph = ('<p><span style="font-family:DejaVu Sans;font-size:16pt">Ação ágil 😀 </span>'
                 '<b>{nome}</b><i> — função e dedicação </i>'
                 '<span style="font-family:DejaVu Serif;font-size:24pt">Çgj</span>'
                 '<span style="font-size:11pt"> 𝄞 equipe e organização.</span></p>')
    return paragraph * (30 if long else 1)


def text_document(count=1, long=False):
    boxes = []
    for i in range(count):
        boxes.append(dict(layer_id=i+1, object_id=f'text:{i+1}', custom_name=f'Texto {i+1}',
                          x=20+(i%5)*220, y=20+(i//5)*140, w=200 if count>4 else 1000,
                          h=120 if count>4 else 1800, html=rich_sample(long), rich_text_version=1,
                          font_family='DejaVu Sans',font_size=16,vertical_align='center',align='center',
                          line_height=.95,indent_px=5))
    return normalize_model_document(dict(canvas_size=dict(w=1200,h=max(2000, count//5*140+160)),
        target_w_mm=101.6,target_h_mm=max(2000,count//5*140+160)*25.4/300,
        boxes=boxes,layer_order=[b['object_id'] for b in boxes],editable_background_initialized=True))
