"""Avisos sem conteúdo dos registros; usa os sinais/logs existentes de geração."""
from core.i18n import tr


def table_warning_messages(warnings, source_row=None):
    messages = []
    for warning in warnings:
        context = (tr('Bloco {bloco}, cartão {cartao}').format(bloco=warning['block'],cartao=warning['slot'])
                   if 'block' in warning else
                   tr('Registro {registro}').format(registro=source_row+1) if source_row is not None else '')
        page = {'front':tr('frente'),'back':tr('verso'),'organogram':tr('organograma')}.get(warning.get('page_id'),'')
        messages.append(tr('⚠ Texto excede a célula {linha},{coluna} da tabela “{tabela}” ({pagina}). {contexto}').format(
            linha=warning['row'],coluna=warning['column'],tabela=warning['table_name'],pagina=page,contexto=context))
    return list(dict.fromkeys(messages))
