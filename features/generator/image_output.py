"""Formatos raster compartilhados pelos cartões, folhas e ladrilhos."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from core.i18n import tr
from .png_output import save_png


JPEG_QUALITY = {"JPEG": 95}
EXPORT_MODES = frozenset(("png", "jpeg", "pdf_item", "pdf_grouped"))


def export_choices():
    return (
        ("PNG", "png", tr("Uma imagem PNG para cada item.")),
        ("JPEG", "jpeg", ""),
        ("PDF", "pdf_item", tr("Um arquivo PDF separado para cada item.")),
        (tr("PDF Agrupado"), "pdf_grouped", tr("Todos os itens reunidos em um único arquivo PDF.")),
    )


def restored_export_mode(data):
    mode = data.get("last_export_mode")
    # Modelos salvos com as duas opções anteriores passam para o JPEG único.
    if mode in ("jpeg_fine", "jpeg_fast"):
        return "jpeg"
    if mode in EXPORT_MODES:
        return mode
    export_format = data.get("last_export_format", "PNG")
    if export_format in ("JPEG", "JPEG_FINE", "JPEG_FAST"):
        return "jpeg"
    if export_format == "PNG":
        return "png"
    return "pdf_grouped" if data.get("last_single_pdf", False) else "pdf_item"


def raster_format(mode):
    value = (mode or "").upper()
    return value if value == "PNG" or value in JPEG_QUALITY else None


def image_extension(export_format):
    if export_format.upper() == "PNG":
        return "png"
    if export_format.upper() in JPEG_QUALITY:
        return "jpg"
    raise ValueError(f"Formato de imagem desconhecido: {export_format}")


def save_image(image, path, export_format, *, intermediate_png=False):
    """JPEG usa o mesmo bitmap renderizado, composto sobre branco se houver alfa."""
    export_format = export_format.upper()
    if export_format == "PNG":
        return save_png(image, path, intermediate=intermediate_png)
    quality = JPEG_QUALITY[export_format]
    if image.hasAlphaChannel():
        opaque = QImage(image.size(), QImage.Format.Format_RGB32)
        if opaque.isNull():
            raise MemoryError(tr("Não foi possível reservar memória para o JPEG."))
        opaque.fill(Qt.GlobalColor.white)
        painter = QPainter(opaque)
        try:
            painter.drawImage(0, 0, image)
        finally:
            painter.end()
        opaque.setDotsPerMeterX(image.dotsPerMeterX())
        opaque.setDotsPerMeterY(image.dotsPerMeterY())
        image = opaque
    return image.save(str(path), "JPEG", quality)
