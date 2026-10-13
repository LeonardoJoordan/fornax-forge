"""Sombra externa de texto, compartilhada por canvas e geração.

Somente QImage/QPainter: sem QPixmap, widgets ou cenas nos workers. A máscara
tem orçamento próprio; textos gigantes reduzem apenas a resolução da sombra,
preservando o texto original. Nenhuma imagem ou texto é gravado em disco.
"""
import hashlib
import math

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QImage, QPainter, QTextCursor, QTextCharFormat, QBrush, QPen

from core.image_memory_cache import ImageMemoryCache
from core.i18n import tr
from core.performance import EXPORT_DPI

SHADOW_CACHE_BYTES = 16 * 1024 * 1024
MAX_MASK_PIXELS = 1_000_000
MAX_MASK_SIDE = 4096
DEFAULT_SHADOW = dict(enabled=False, color='#000000', opacity=.5,
                      angle=45., distance=.25 * EXPORT_DPI / 25.4,
                      blur=.25 * EXPORT_DPI / 25.4)


def normalize_shadow(value):
    value = value if isinstance(value, dict) else {}
    result = dict(DEFAULT_SHADOW)
    result['enabled'] = value.get('enabled') is True
    color = QColor(str(value.get('color', result['color'])))
    if color.isValid():
        result['color'] = color.name()
    for key, limit in (('opacity', 1.), ('angle', 360.), ('distance', 240.), ('blur', 120.)):
        number = value.get(key, result[key])
        if type(number) in (float, int) and math.isfinite(number):
            result[key] = min(limit, max(0., float(number)))
    return result


def active_shadow(data):
    value = data.get('shadow')
    return isinstance(value, dict) and value.get('enabled') is True


def shadow_bounds(doc, shadow):
    # A mesma folga vertical do item de texto atual cobre ascendentes,
    # descendentes e itálicos. O conteúdo horizontal mantém o recorte da caixa.
    size = doc.size()
    blur = shadow['blur']
    source = QRectF(0, -200, max(1., doc.textWidth()), max(1., size.height()) + 400)
    angle = math.radians(shadow['angle'])
    offset = QPointF(math.cos(angle) * shadow['distance'], math.sin(angle) * shadow['distance'])
    return source.adjusted(-blur-2, -blur-2, blur+2, blur+2).translated(offset), source, offset


def new_shadow_cache():
    return ImageMemoryCache(SHADOW_CACHE_BYTES)


def _image(width, height):
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    if image.isNull():
        raise MemoryError(tr('Não foi possível reservar memória para a sombra do texto.'))
    image.setDotsPerMeterX(3780)
    image.setDotsPerMeterY(3780)
    image.fill(Qt.GlobalColor.transparent)
    return image


def _blur(image, radius):
    """Filtro gaussiano separável em operações nativas do QPainter.

    Para raios grandes, a máscara já chega reduzida; no máximo 17 amostras
    por eixo. Composition_Plus soma a cobertura, sem escurecer por sobreposição.
    """
    if radius < .25:
        return image
    support = max(1, math.ceil(radius))
    sigma = max(.5, radius / 3)
    weights = [math.exp(-offset * offset / (2 * sigma * sigma))
               for offset in range(-support, support + 1)]
    total = sum(weights)
    for horizontal in (True, False):
        target = _image(image.width(), image.height())
        painter = QPainter(target)
        try:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            for offset, weight in zip(range(-support, support + 1), weights):
                painter.setOpacity(weight / total)
                painter.drawImage(offset if horizontal else 0, 0 if horizontal else offset, image)
        finally:
            painter.end()
        image = target
    return image


def paint_text_shadow(painter, doc, data, cache=None):
    if not active_shadow(data):
        return
    shadow = normalize_shadow(data['shadow'])
    if shadow['opacity'] <= 0 or doc.isEmpty():
        return
    bounds, source, offset = shadow_bounds(doc, shadow)
    # Limita buffers temporários inclusive em documentos de vários metros.
    scale = min(1., 8. / max(8., shadow['blur']),
                math.sqrt(MAX_MASK_PIXELS / (bounds.width() * bounds.height())),
                MAX_MASK_SIDE / max(bounds.width(), bounds.height()))
    width, height = max(1, int(bounds.width() * scale)), max(1, int(bounds.height() * scale))
    key = hashlib.sha256((doc.toHtml() + repr((doc.defaultFont().toString(),
        doc.textWidth(), doc.defaultTextOption().alignment().value,
        shadow['color'], shadow['blur'], width, height))).encode('utf-8')).digest()
    image = cache.get(key) if cache is not None else None
    if image is None:
        image = _image(width, height)
        mask_doc = doc.clone()
        cursor = QTextCursor(mask_doc)
        cursor.select(QTextCursor.SelectionType.Document)
        fmt = QTextCharFormat()
        fmt.setForeground(QBrush(Qt.GlobalColor.white))
        fmt.setBackground(QBrush(Qt.BrushStyle.NoBrush))
        fmt.setTextOutline(QPen(Qt.PenStyle.NoPen))
        cursor.mergeCharFormat(fmt)
        mask_painter = QPainter(image)
        try:
            mask_painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            mask_painter.scale(width / bounds.width(), height / bounds.height())
            mask_painter.translate(-bounds.x() + offset.x(), -bounds.y() + offset.y())
            mask_painter.setClipRect(source)
            mask_doc.drawContents(mask_painter)
        finally:
            mask_painter.end()
        image = _blur(image, shadow['blur'] * scale)
        tint = QPainter(image)
        try:
            tint.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            tint.fillRect(image.rect(), QColor(shadow['color']))
        finally:
            tint.end()
        if cache is not None:
            cache[key] = image
    painter.save()
    try:
        painter.setOpacity(painter.opacity() * shadow['opacity'])
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(bounds, image)
    finally:
        painter.restore()
