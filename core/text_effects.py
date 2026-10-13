"""Sombras externas compartilhadas por canvas e geração.

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
                      blur=.25 * EXPORT_DPI / 25.4, spread=0.)


def normalize_shadow(value):
    value = value if isinstance(value, dict) else {}
    result = dict(DEFAULT_SHADOW)
    result['enabled'] = value.get('enabled') is True
    color = QColor(str(value.get('color', result['color'])))
    if color.isValid():
        result['color'] = color.name()
    for key, limit in (('opacity', 1.), ('angle', 360.), ('distance', 240.), ('blur', 120.), ('spread', 120.)):
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
    margin = shadow['blur'] + shadow.get('spread', 0.) + 2
    source = QRectF(0, -200, max(1., doc.textWidth()), max(1., size.height()) + 400)
    angle = math.radians(shadow['angle'])
    offset = QPointF(math.cos(angle) * shadow['distance'], math.sin(angle) * shadow['distance'])
    return source.adjusted(-margin, -margin, margin, margin).translated(offset), source, offset


def new_shadow_cache():
    return ImageMemoryCache(SHADOW_CACHE_BYTES)


def object_shadow_bounds(source, shadow):
    source = QRectF(source)
    if not active_shadow({'shadow': shadow}):
        return source
    shadow = normalize_shadow(shadow)
    angle = math.radians(shadow['angle'])
    offset = QPointF(math.cos(angle) * shadow['distance'], math.sin(angle) * shadow['distance'])
    margin = shadow['blur'] + shadow['spread'] + 2
    return source.united(source.adjusted(-margin, -margin, margin, margin).translated(offset))


def paint_object_shadow(painter, source, data, draw_source, source_key, cache=None):
    """Sombra da cobertura alpha do objeto; overlays da UI nunca entram nela."""
    if not active_shadow(data) or source.isEmpty():
        return
    shadow = normalize_shadow(data['shadow'])
    if shadow['opacity'] <= 0:
        return
    angle = math.radians(shadow['angle'])
    offset = QPointF(math.cos(angle) * shadow['distance'], math.sin(angle) * shadow['distance'])
    margin = shadow['blur'] + shadow['spread'] + 2
    bounds = source.adjusted(-margin, -margin, margin, margin)
    scale = min(1., 8. / max(8., shadow['blur'], shadow['spread']),
                math.sqrt(MAX_MASK_PIXELS / (bounds.width() * bounds.height())),
                MAX_MASK_SIDE / max(bounds.width(), bounds.height()))
    width, height = max(1, int(bounds.width() * scale)), max(1, int(bounds.height() * scale))
    key = hashlib.sha256(repr(('object', source_key, source.getRect(), shadow['blur'], shadow['spread'],
                              shadow['color'], width, height)).encode('utf-8')).digest()
    image = cache.get(key) if cache is not None else None
    if image is None:
        image = _image(width, height)
        mask_painter = QPainter(image)
        try:
            mask_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            mask_painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            mask_painter.scale(width / bounds.width(), height / bounds.height())
            mask_painter.translate(-bounds.x(), -bounds.y())
            draw_source(mask_painter)
        finally:
            mask_painter.end()
        image = _spread_mask(image, shadow['spread'] * scale)
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
        painter.drawImage(bounds.translated(offset), image)
    finally:
        painter.restore()


def paint_image_shadow(painter, image, bounds, shadow, cache=None):
    paint_object_shadow(painter, bounds, {'shadow': shadow},
                        lambda target: target.drawImage(bounds, image, QRectF(image.rect())),
                        ('image', image.cacheKey()), cache)


def _image(width, height, image_format=QImage.Format.Format_ARGB32_Premultiplied):
    image = QImage(width, height, image_format)
    if image.isNull():
        raise MemoryError(tr('Não foi possível reservar memória para a sombra do objeto.'))
    image.setDotsPerMeterX(3780)
    image.setDotsPerMeterY(3780)
    image.fill(Qt.GlobalColor.transparent)
    return image


def _maximum_horizontal(image, radius):
    """Máximo da cobertura por eixo, em passos logarítmicos nativos."""
    covered = 0
    while covered < radius:
        step = min(2 * covered + 1, radius - covered)
        target = _image(image.width(), image.height(), QImage.Format.Format_RGB32)
        painter = QPainter(target)
        try:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Lighten)
            for offset in (-step, 0, step):
                painter.drawImage(offset, 0, image)
        finally:
            painter.end()
        image = target
        covered += step
    return image


def _dilate_disk(image, radius):
    if radius == 0:
        return image
    rows = {}
    for y in range(-radius, radius + 1):
        extent = math.isqrt(radius * radius - y * y)
        rows.setdefault(extent, []).append(y)
    target = _image(image.width(), image.height(), QImage.Format.Format_RGB32)
    painter = QPainter(target)
    try:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Lighten)
        for extent, offsets in rows.items():
            # Não reter uma imagem por linha/raio: só um filtro de cada vez.
            expanded = _maximum_horizontal(image, extent)
            for y in offsets:
                painter.drawImage(0, y, expanded)
            del expanded
    finally:
        painter.end()
    return target


def _spread_mask(image, radius):
    """Dilatação circular do alpha, preservando a transparência do conteúdo.

    Lighten calcula o máximo em uma cópia RGB opaca da cobertura alpha.
    Sobrepor máscaras transparentes com SourceOver engrossaria também sua
    opacidade. O raio chega limitado a 8 px; frações interpolam os dois discos.
    """
    if radius <= 0:
        return image
    alpha = image.convertToFormat(QImage.Format.Format_Alpha8)
    if alpha.isNull():
        raise MemoryError(tr('Não foi possível reservar memória para a sombra do objeto.'))
    view = QImage(alpha.constBits(), alpha.width(), alpha.height(), alpha.bytesPerLine(),
                  QImage.Format.Format_Grayscale8)
    gray = view.convertToFormat(QImage.Format.Format_RGB32)
    del view, alpha
    if gray.isNull():
        raise MemoryError(tr('Não foi possível reservar memória para a sombra do objeto.'))
    lower = math.floor(radius)
    fraction = radius - lower
    grown = _dilate_disk(gray, lower)
    if fraction > 1e-6:
        upper = _dilate_disk(gray, lower + 1)
        mixed = _image(gray.width(), gray.height(), QImage.Format.Format_RGB32)
        painter = QPainter(mixed)
        try:
            painter.drawImage(0, 0, grown)
            # SourceOver de imagens opacas interpola os canais sem saturar
            # primeiro a soma, como ocorreria com Plus e opacidade global.
            painter.setOpacity(fraction)
            painter.drawImage(0, 0, upper)
        finally:
            painter.end()
        grown = mixed
        del upper, mixed
    result = grown.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    if result.isNull():
        raise MemoryError(tr('Não foi possível reservar memória para a sombra do objeto.'))
    result.setAlphaChannel(grown)
    return result


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
    scale = min(1., 8. / max(8., shadow['blur'], shadow['spread']),
                math.sqrt(MAX_MASK_PIXELS / (bounds.width() * bounds.height())),
                MAX_MASK_SIDE / max(bounds.width(), bounds.height()))
    width, height = max(1, int(bounds.width() * scale)), max(1, int(bounds.height() * scale))
    key = hashlib.sha256((doc.toHtml() + repr((doc.defaultFont().toString(),
        doc.textWidth(), doc.defaultTextOption().alignment().value,
        shadow['color'], shadow['blur'], shadow['spread'], width, height))).encode('utf-8')).digest()
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
        image = _spread_mask(image, shadow['spread'] * scale)
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
