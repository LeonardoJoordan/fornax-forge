"""Fonte incorporada da interface e padrão dos novos textos do documento."""

import logging

from PySide6.QtGui import QFont, QFontDatabase, QFontInfo
from PySide6.QtWidgets import QApplication

from core.resources import PROJECT_ROOT


UI_FONT_FAMILY = "Inter 18pt"
DOCUMENT_FONT_FAMILY = UI_FONT_FAMILY
UI_FONT_SIZE = 9


def resolve_font_family(family: str | None) -> str:
    """Direciona os nomes da Inter ao nome real dos arquivos incorporados."""
    name = str(family or '').strip()
    if not name or name.casefold() in ('inter', UI_FONT_FAMILY.casefold()):
        return DOCUMENT_FONT_FAMILY
    return name


def install_ui_font(app: QApplication) -> str:
    font_dir = PROJECT_ROOT / "assets" / "fonts" / "ui"
    # As fontes variáveis eram expostas pelo Qt somente como Regular e Italic
    # em algumas plataformas. As variantes estáticas garantem que pesos como
    # Bold e ExtraBold sejam resolvidos para os desenhos reais da família.
    files = tuple(sorted(font_dir.glob("Inter_18pt-*.ttf")))
    logger = logging.getLogger(__name__)
    families = []
    for path in files:
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            families.extend(QFontDatabase.applicationFontFamilies(font_id))
        else:
            logger.warning('Não foi possível carregar a fonte incorporada: %s', path)

    if UI_FONT_FAMILY not in families:
        logger.error('A fonte incorporada %s não foi registrada em %s. Famílias carregadas: %s',
                     UI_FONT_FAMILY, font_dir, families)
        return ''
    # O alias também atende controles Qt que recebam HTML externo. Nos documentos
    # resolvemos a família explicitamente para não preferir outra Inter instalada.
    QFont.insertSubstitution('Inter', UI_FONT_FAMILY)
    # Não herdar tamanho, peso ou estilo da fonte preferida do sistema operacional.
    font = QFont(UI_FONT_FAMILY, UI_FONT_SIZE, QFont.Weight.Normal, False)
    font.setStyleName('')
    app.setFont(font)
    actual = QFontInfo(app.font()).family()
    if actual != UI_FONT_FAMILY:
        logger.error('Fonte efetiva da interface: %s; esperada: %s', actual, UI_FONT_FAMILY)
    return UI_FONT_FAMILY
