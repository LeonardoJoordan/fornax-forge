"""Identificadores visíveis das colunas funcionais da planilha."""
from PySide6.QtCore import Qt

from core.i18n import tr

QUANTITY_HEADER = "Cópias"
SIGNATURE_HEADER = "Ass."
SIGNATURE_ID_ROLE = Qt.ItemDataRole.UserRole + 101
BLOCK_DESTINATION_ROLE = Qt.ItemDataRole.UserRole + 102


def is_block_header(header):
    return header is not None and bool(header.data(BLOCK_DESTINATION_ROLE))


def quantity_header_label():
    # Literal mantido aqui para que o lupdate inclua o cabeçalho no catálogo.
    return tr("Cópias")


def is_quantity_header(value):
    return value in (QUANTITY_HEADER, quantity_header_label())


def signature_id_from_header(header):
    if header is None:
        return None
    value = header.data(SIGNATURE_ID_ROLE)
    return value.strip() if isinstance(value, str) and value.strip() else None


def is_signature_header(header):
    return bool(
        signature_id_from_header(header)
        or (header is not None and header.text() == SIGNATURE_HEADER)
    )


def table_column_key(header):
    """Chave estável para restaurar células mesmo após renomear uma assinatura."""
    if is_block_header(header):
        from core.organogram import BLOCK_DESTINATION_KEY
        return BLOCK_DESTINATION_KEY
    signature_id = signature_id_from_header(header)
    return f"__signature__:{signature_id}" if signature_id else header.text()
