from PySide6.QtGui import QTextDocument
from core.text_safety import (
    text_html_has_unsupported_resources, sanitize_text_html, normalize_text_decoration,
)


class TextOnlyDocument(QTextDocument):
    """Documento rico que nunca resolve recursos externos.

    As caixas do FORNAX guardam texto formatado. Elementos gráficos pertencem
    às camadas de imagem e, portanto, nenhum recurso solicitado pelo HTML deve
    chegar ao sistema de arquivos ou à rede.
    """

    def loadResource(self, resource_type, name):  # noqa: N802 - API do Qt
        return None
