import math
import re
from uuid import uuid4
from pathlib import Path
from PySide6.QtWidgets import (QGraphicsLineItem, QGraphicsRectItem, QGraphicsTextItem,
                               QGraphicsItem, QInputDialog, QLineEdit, QGraphicsPixmapItem,
                               QStyle, QStyleOptionGraphicsItem)
from PySide6.QtCore import Qt, QPointF, QRectF, QSize, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import (QPen, QBrush, QColor, QFont, QTextCursor,
                           QTextBlockFormat, QPixmap, QPainterPathStroker, QTextCharFormat,
                           QImageReader, QPainterPath, QPainter,
                           QImageIOHandler)
from core.html_utils import normalize_text_decoration, sanitize_text_html
from core.text_layout import line_reference_ink_bounds, variables_in_html
from core.text_state import TextState

DPI = 300

def mm_to_px(mm):
    return (mm * DPI) / 25.4

def px_to_mm(px):
    return (px * 25.4) / DPI

def _reader_logical_size(reader, raw_size):
    transform = reader.transformation()
    if transform & QImageIOHandler.Transformation.TransformationRotate90:
        return QSize(raw_size.height(), raw_size.width())
    return QSize(raw_size.width(), raw_size.height())

def _load_proxy_pixmap(path):
    """
    Carrega a imagem gerando um proxy leve na RAM se o lado maior ultrapassar 2048px.
    Retorna: (pixmap, logical_w, logical_h, proxy_scale)
    """
    if not path:
        pix = QPixmap(1000, 1000)
        pix.fill(Qt.GlobalColor.transparent)
        return pix, 1000.0, 1000.0, 1.0

    reader = QImageReader(path)
    reader.setAutoTransform(True)
    raw_size = reader.size()
    
    if raw_size.isEmpty():
        img = reader.read() if reader.canRead() else None
        pix = QPixmap.fromImage(img) if img is not None and not img.isNull() else QPixmap(path)
        return pix, float(pix.width()), float(pix.height()), 1.0

    logical_size = _reader_logical_size(reader, raw_size)
    logical_w = float(logical_size.width())
    logical_h = float(logical_size.height())
    
    MAX_SIDE = 2048.0
    longest_side = max(logical_w, logical_h)
    
    if longest_side <= MAX_SIDE:
        img = reader.read() if reader.canRead() else None
        pix = QPixmap.fromImage(img) if img is not None and not img.isNull() else QPixmap(path)
        if not pix.isNull():
            logical_w = float(pix.width())
            logical_h = float(pix.height())
        return pix, logical_w, logical_h, 1.0
        
    proxy_scale = MAX_SIDE / longest_side
    new_w = int(raw_size.width() * proxy_scale)
    new_h = int(raw_size.height() * proxy_scale)
    
    reader.setScaledSize(QSize(new_w, new_h))
    img = reader.read()
    pix = QPixmap.fromImage(img) if not img.isNull() else QPixmap(path)
    
    return pix, logical_w, logical_h, proxy_scale


def _load_proxy_pixmap_bytes(data):
    """Decodifica um asset autorizado sem materializá-lo no sistema de arquivos."""
    encoded = QByteArray(bytes(data or b""))
    buffer = QBuffer(encoded)
    if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
        return _load_proxy_pixmap(None)
    reader = QImageReader(buffer)
    reader.setAutoTransform(True)
    raw_size = reader.size()
    image = reader.read()
    if image.isNull():
        return _load_proxy_pixmap(None)
    logical = _reader_logical_size(reader, raw_size) if raw_size.isValid() else image.size()
    logical_w = float(logical.width() or image.width())
    logical_h = float(logical.height() or image.height())
    longest = max(logical_w, logical_h)
    proxy_scale = min(1.0, 2048.0 / longest) if longest > 0 else 1.0
    if proxy_scale < 1.0:
        image = image.scaled(
            max(1, round(logical_w * proxy_scale)),
            max(1, round(logical_h * proxy_scale)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return QPixmap.fromImage(image), logical_w, logical_h, proxy_scale


def _rotated_point(position, origin, angle, point):
    rad = math.radians(angle)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    dx = point.x() - origin.x()
    dy = point.y() - origin.y()
    return QPointF(
        position.x() + origin.x() + (dx * cos_a - dy * sin_a),
        position.y() + origin.y() + (dx * sin_a + dy * cos_a),
    )


def _rotated_vector(point, angle):
    rad = math.radians(angle)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    return QPointF(
        point.x() * cos_a - point.y() * sin_a,
        point.x() * sin_a + point.y() * cos_a,
    )


def _unrotated_vector(point, angle):
    return _rotated_vector(point, -angle)


def _item_pos_for_local_scene_point(item, local_point, scene_point):
    # ``setPos`` sempre recebe coordenadas do pai. Para itens de nível raiz,
    # esse sistema coincide com a cena; imagens dentro de máscaras, porém,
    # usam o sistema local da forma. Converter o ponto fixo antes do cálculo
    # evita que a posição da forma seja somada novamente no primeiro resize.
    parent = item.parentItem()
    target_point = (
        parent.mapFromScene(scene_point)
        if parent is not None
        else QPointF(scene_point)
    )
    origin = item.transformOriginPoint()
    local_from_origin = QPointF(local_point.x() - origin.x(), local_point.y() - origin.y())
    rotated_from_origin = _rotated_vector(local_from_origin, item.rotation())
    return QPointF(
        target_point.x() - origin.x() - rotated_from_origin.x(),
        target_point.y() - origin.y() - rotated_from_origin.y(),
    )


def _document_rect(scene):
    rect = getattr(scene, "_document_rect", None)
    if rect is not None:
        return QRectF(rect)
    return scene.sceneRect()


def _paint_with_document_fade(item, painter, draw_content, outside_opacity=0.25):
    """Pinta conteúdo fora da página atenuado, sem afetar filhos/alças.

    A opacidade do painter já inclui a opacidade própria e a dos pais do item;
    multiplicá-la mantém o comportamento cumulativo esperado.
    """
    scene = item.scene()
    if scene is None:
        draw_content()
        return

    document = _document_rect(scene)
    scene_bounds = item.sceneBoundingRect()
    if document.contains(scene_bounds):
        draw_content()
        return
    if not document.intersects(scene_bounds):
        painter.save()
        painter.setOpacity(painter.opacity() * outside_opacity)
        draw_content()
        painter.restore()
        return

    document_path = QPainterPath()
    document_path.addRect(document)
    local_document = item.mapFromScene(document_path)

    outside = QPainterPath()
    outside.addRect(item.boundingRect())
    outside = outside.subtracted(local_document)

    painter.save()
    painter.setClipPath(outside, Qt.ClipOperation.IntersectClip)
    painter.setOpacity(painter.opacity() * outside_opacity)
    draw_content()
    painter.restore()

    painter.save()
    painter.setClipPath(local_document, Qt.ClipOperation.IntersectClip)
    draw_content()
    painter.restore()


def _paint_with_mask_edit_fade(item, painter, draw_content, outside_opacity=0.25):
    """Exibe o excedente da imagem somente durante a edição da máscara."""
    parent = item.parentItem()
    if not isinstance(parent, RectangleItem) or not getattr(parent, '_mask_editing', False):
        draw_content()
        return
    mask_path = item.mapFromItem(parent, parent.drawing_path())
    outside = QPainterPath()
    outside.addRect(item.boundingRect())
    outside = outside.subtracted(mask_path)

    painter.save()
    painter.setClipPath(outside, Qt.ClipOperation.IntersectClip)
    painter.setOpacity(painter.opacity() * outside_opacity)
    draw_content()
    painter.restore()

    painter.save()
    painter.setClipPath(mask_path, Qt.ClipOperation.IntersectClip)
    draw_content()
    painter.restore()


def _paint_with_mask_clip(item, painter, draw_content):
    parent = item.parentItem()
    if not isinstance(parent, RectangleItem):
        draw_content()
        return
    painter.save()
    painter.setClipPath(item.mapFromItem(parent, parent.drawing_path()),
                        Qt.ClipOperation.IntersectClip)
    draw_content()
    painter.restore()


def _snap_targets(scene):
    vertical_targets = []
    horizontal_targets = []

    rect = _document_rect(scene)
    if not rect.isEmpty():
        vertical_targets.extend((rect.left(), rect.right()))
        horizontal_targets.extend((rect.top(), rect.bottom()))

    for item in scene.items():
        if isinstance(item, Guideline):
            if item.is_vertical:
                vertical_targets.append(item.x())
            else:
                horizontal_targets.append(item.y())

    return vertical_targets, horizontal_targets

def _get_dynamic_snap_distance(scene):
    if not scene: 
        return 15.0
    
    rect = _document_rect(scene)
    media_lados = (rect.width() + rect.height()) / 2.0
    base_dist = max(5.0, media_lados * 0.008)
    
    zoom = 1.0
    if scene.views():
        zoom = max(0.001, scene.views()[0].transform().m11())
        
    return base_dist / math.sqrt(zoom)


def _queue_selection_frame_refresh(item):
    scene = item.scene()
    if not scene or not scene.views():
        return
    window = scene.views()[0].window()
    if hasattr(window, '_queue_selection_frame_refresh'):
        window._queue_selection_frame_refresh()


def _snap_position_to_guides(item, new_pos, w, h):
    scene = item.scene()
    if not scene:
        return new_pos

    sel = scene.selectedItems()
    leader = next((i for i in sel if getattr(i, '_is_mouse_dragging', False)), None)
    
    # Validação rigorosa: Só atua se houver arrastre e o estado coletivo estiver inicializado
    if not leader or not hasattr(scene, '_drag_start_positions') or item not in scene._drag_start_positions:
        return new_pos

    start_pos = scene._drag_start_positions[item]
    abs_delta = new_pos - start_pos

    # Hit de Cache: Garante que todos os itens leiam o exato mesmo vetor matemático no quadro atual
    cached_delta = getattr(scene, '_group_raw_delta', None)
    if cached_delta and abs(cached_delta.x() - abs_delta.x()) < 0.001 and abs(cached_delta.y() - abs_delta.y()) < 0.001:
        return new_pos + QPointF(getattr(scene, '_group_snap_dx', 0), getattr(scene, '_group_snap_dy', 0))

    dynamic_snap = _get_dynamic_snap_distance(scene)
    vertical_targets, horizontal_targets = _snap_targets(scene)

    best_dx = 0
    best_dy = 0
    min_dist_x = dynamic_snap
    min_dist_y = dynamic_snap

    # Batch Scan: Analisa todos os itens selecionados contra as guias simultaneamente
    for sel_item in sel:
        if sel_item not in scene._drag_start_positions:
            continue
            
        if hasattr(sel_item, 'rect'):
            iw, ih = sel_item.rect().width(), sel_item.rect().height()
        elif hasattr(sel_item, 'pixmap'):
            iw, ih = sel_item.pixmap().width(), sel_item.pixmap().height()
        else:
            continue
            
        cand_pos = scene._drag_start_positions[sel_item] + abs_delta

        local_points = [QPointF(0, 0), QPointF(iw, 0), QPointF(iw, ih), QPointF(0, ih)]
        parent = sel_item.parentItem()
        if parent is None:
            current_anchor = sel_item.pos()
            candidate_anchor = cand_pos
        else:
            # A posição de um item mascarado está no sistema local da forma,
            # enquanto guias e limites do documento usam coordenadas da cena.
            current_anchor = parent.mapToScene(sel_item.pos())
            candidate_anchor = parent.mapToScene(cand_pos)
        scene_shift = candidate_anchor - current_anchor
        scene_points = [sel_item.mapToScene(point) + scene_shift for point in local_points]
        center = sel_item.mapToScene(QPointF(iw / 2, ih / 2)) + scene_shift

        xs = [p.x() for p in scene_points]
        ys = [p.y() for p in scene_points]
        x_candidates = [min(xs), center.x(), max(xs)]
        y_candidates = [min(ys), center.y(), max(ys)]

        for target_x in vertical_targets:
            for x in x_candidates:
                dist = abs(x - target_x)
                if dist < min_dist_x:
                    min_dist_x = dist
                    best_dx = target_x - x

        for target_y in horizontal_targets:
            for y in y_candidates:
                dist = abs(y - target_y)
                if dist < min_dist_y:
                    min_dist_y = dist
                    best_dy = target_y - y

    # Atualiza o cache do quadro
    scene._group_raw_delta = abs_delta
    scene._group_snap_dx = best_dx
    scene._group_snap_dy = best_dy

    scene_correction = QPointF(best_dx, best_dy)
    parent = item.parentItem()
    if parent is not None:
        inverse, invertible = parent.sceneTransform().inverted()
        if invertible:
            scene_correction = inverse.map(scene_correction) - inverse.map(QPointF(0, 0))
    return new_pos + scene_correction


class ResizeHandle(QGraphicsRectItem):
    MIN_WIDTH = 40
    MIN_HEIGHT = 30

    def __init__(self, parent, name, x_dir, y_dir, cursor):
        # Começamos com um tamanho padrão, mas ele será atualizado dinamicamente
        super().__init__(-6, -6, 12, 12, parent)
        self.name = name
        self.x_dir = x_dir
        self.y_dir = y_dir
        from core.themes import theme_color
        self.setBrush(QBrush(QColor(theme_color('handle'))))
        self.setPen(QPen(Qt.GlobalColor.white, 2))
        self.setAcceptHoverEvents(True)
        self.setCursor(cursor)
        self.setZValue(1000)
        self._is_resizing = False
        self._anchor_scene = None
        self._initial_w = 1.0
        self._initial_h = 1.0
        self.initial_ratio = 1.0

    def _anchor_local_point(self, w, h):
        if self.x_dir < 0:
            anchor_x = w
        elif self.x_dir > 0:
            anchor_x = 0
        else:
            anchor_x = w / 2

        if self.y_dir < 0:
            anchor_y = h
        elif self.y_dir > 0:
            anchor_y = 0
        else:
            anchor_y = h / 2

        return QPointF(anchor_x, anchor_y)

    def _resize_from_local_delta(self, local_delta):
        ratio = self.initial_ratio if self.initial_ratio > 0 else 1.0
        keep_proportion = self._keep_proportion()

        if self.x_dir and self.y_dir:
            raw_w = local_delta.x() * self.x_dir
            raw_h = local_delta.y() * self.y_dir
            if keep_proportion:
                diagonal = QPointF(1.0, 1.0 / ratio)
                diagonal_len_sq = diagonal.x() ** 2 + diagonal.y() ** 2
                projected_w = (
                    (raw_w * diagonal.x() + raw_h * diagonal.y())
                    / diagonal_len_sq
                )
                min_w = max(self.MIN_WIDTH, self.MIN_HEIGHT * ratio)
                new_w = max(min_w, projected_w)
                new_h = new_w / ratio
            else:
                new_w = max(self.MIN_WIDTH, raw_w)
                new_h = max(self.MIN_HEIGHT, raw_h)

        elif self.x_dir:
            raw_w = local_delta.x() * self.x_dir
            if keep_proportion:
                min_w = max(self.MIN_WIDTH, self.MIN_HEIGHT * ratio)
                new_w = max(min_w, raw_w)
                new_h = new_w / ratio
            else:
                new_w = max(self.MIN_WIDTH, raw_w)
                new_h = self._initial_h

        elif self.y_dir:
            raw_h = local_delta.y() * self.y_dir
            if keep_proportion:
                min_h = max(self.MIN_HEIGHT, self.MIN_WIDTH / ratio)
                new_h = max(min_h, raw_h)
                new_w = new_h * ratio
            else:
                new_w = self._initial_w
                new_h = max(self.MIN_HEIGHT, raw_h)

        else:
            new_w = self._initial_w
            new_h = self._initial_h

        return new_w, new_h

    def _active_point_factors(self):
        if self.x_dir and self.y_dir:
            fx = 1.0 if self.x_dir > 0 else 0.0
            fy = 1.0 if self.y_dir > 0 else 0.0
            return [(fx, fy)]

        if self.x_dir:
            fx = 1.0 if self.x_dir > 0 else 0.0
            return [(fx, 0.5)]

        if self.y_dir:
            fy = 1.0 if self.y_dir > 0 else 0.0
            return [(0.5, fy)]

        return []

    def _scene_point_from_factors(self, parent, anchor_scene, w, h, fx, fy):
        anchor_local = self._anchor_local_point(w, h)
        local_point = QPointF(w * fx, h * fy)
        local_delta = QPointF(
            local_point.x() - anchor_local.x(),
            local_point.y() - anchor_local.y(),
        )
        rotated_delta = _rotated_vector(local_delta, parent.rotation())
        return QPointF(
            anchor_scene.x() + rotated_delta.x(),
            anchor_scene.y() + rotated_delta.y(),
        )

    def _size_for_control(self, control_axis, control_value, base_w, base_h):
        ratio = self.initial_ratio if self.initial_ratio > 0 else 1.0
        keep_proportion = self._keep_proportion()

        if keep_proportion:
            if control_axis == "w":
                min_w = max(self.MIN_WIDTH, self.MIN_HEIGHT * ratio)
                w = max(min_w, control_value)
                return w, w / ratio

            min_h = max(self.MIN_HEIGHT, self.MIN_WIDTH / ratio)
            h = max(min_h, control_value)
            return h * ratio, h

        if control_axis == "w":
            return max(self.MIN_WIDTH, control_value), base_h
        return base_w, max(self.MIN_HEIGHT, control_value)

    def _control_axis_for_snap(self, is_vertical_guide):
        if self.x_dir and self.y_dir:
            return "w" if is_vertical_guide else "h"
        if self.x_dir:
            return "w"
        if self.y_dir:
            return "h"
        return None

    def _solve_snap_size(self, parent, anchor_scene, base_w, base_h, factors, target, coord_axis, control_axis):
        fx, fy = factors
        base_point = self._scene_point_from_factors(parent, anchor_scene, base_w, base_h, fx, fy)
        base_coord = base_point.x() if coord_axis == "x" else base_point.y()
        base_control = base_w if control_axis == "w" else base_h
        epsilon = max(1.0, abs(base_control) * 0.001)

        test_w, test_h = self._size_for_control(control_axis, base_control + epsilon, base_w, base_h)
        test_point = self._scene_point_from_factors(parent, anchor_scene, test_w, test_h, fx, fy)
        test_coord = test_point.x() if coord_axis == "x" else test_point.y()
        coefficient = (test_coord - base_coord) / epsilon
        if abs(coefficient) < 1e-6:
            return None

        snapped_control = base_control + (target - base_coord) / coefficient
        snapped_w, snapped_h = self._size_for_control(control_axis, snapped_control, base_w, base_h)
        snapped_point = self._scene_point_from_factors(parent, anchor_scene, snapped_w, snapped_h, fx, fy)
        snapped_coord = snapped_point.x() if coord_axis == "x" else snapped_point.y()
        final_distance = abs(snapped_coord - target)

        return {
            "axis": control_axis,
            "w": snapped_w,
            "h": snapped_h,
            "final_distance": final_distance,
        }

    def _solve_corner_snap_size(self, parent, anchor_scene, base_w, base_h, width_option, height_option):
        if not (self.x_dir and self.y_dir):
            return None

        factors = width_option["factors"]
        if factors != height_option["factors"]:
            return None

        base_point = self._scene_point_from_factors(parent, anchor_scene, base_w, base_h, *factors)
        epsilon_w = max(1.0, abs(base_w) * 0.001)
        epsilon_h = max(1.0, abs(base_h) * 0.001)

        point_w = self._scene_point_from_factors(
            parent,
            anchor_scene,
            base_w + epsilon_w,
            base_h,
            *factors,
        )
        point_h = self._scene_point_from_factors(
            parent,
            anchor_scene,
            base_w,
            base_h + epsilon_h,
            *factors,
        )

        dx_dw = (point_w.x() - base_point.x()) / epsilon_w
        dx_dh = (point_h.x() - base_point.x()) / epsilon_h
        dy_dw = (point_w.y() - base_point.y()) / epsilon_w
        dy_dh = (point_h.y() - base_point.y()) / epsilon_h
        determinant = dx_dw * dy_dh - dx_dh * dy_dw
        if abs(determinant) < 1e-6:
            return None

        target_x = width_option["target"]
        target_y = height_option["target"]
        rhs_x = target_x - base_point.x()
        rhs_y = target_y - base_point.y()

        delta_w = (rhs_x * dy_dh - dx_dh * rhs_y) / determinant
        delta_h = (dx_dw * rhs_y - rhs_x * dy_dw) / determinant
        snapped_w = max(self.MIN_WIDTH, base_w + delta_w)
        snapped_h = max(self.MIN_HEIGHT, base_h + delta_h)

        snapped_point = self._scene_point_from_factors(
            parent,
            anchor_scene,
            snapped_w,
            snapped_h,
            *factors,
        )
        
        snap_distance = _get_dynamic_snap_distance(parent.scene())
        if abs(snapped_point.x() - target_x) >= snap_distance:
            return None
        if abs(snapped_point.y() - target_y) >= snap_distance:
            return None

        return snapped_w, snapped_h

    def _snap_size_to_guides(self, parent, anchor_scene, w, h):
        scene = parent.scene()
        if not scene:
            return w, h

        snap_distance = _get_dynamic_snap_distance(scene)
        keep_proportion = self._keep_proportion()
        active_points = self._active_point_factors()
        best = None
        best_w = None
        best_h = None

        vertical_targets, horizontal_targets = _snap_targets(scene)
        targets = [(True, target) for target in vertical_targets]
        targets.extend((False, target) for target in horizontal_targets)

        for is_vertical, target in targets:
            coord_axis = "x" if is_vertical else "y"
            control_axis = self._control_axis_for_snap(is_vertical)
            if control_axis is None:
                continue

            for factors in active_points:
                scene_point = self._scene_point_from_factors(parent, anchor_scene, w, h, *factors)
                coord = scene_point.x() if coord_axis == "x" else scene_point.y()
                distance = abs(coord - target)
                if distance >= snap_distance:
                    continue

                solved = self._solve_snap_size(
                    parent,
                    anchor_scene,
                    w,
                    h,
                    factors,
                    target,
                    coord_axis,
                    control_axis,
                )
                if not solved or solved["final_distance"] >= snap_distance:
                    continue

                option = {
                    "distance": distance,
                    "factors": factors,
                    "target": target,
                    "coord_axis": coord_axis,
                    **solved,
                }
                if keep_proportion:
                    if best is None or option["distance"] < best["distance"]:
                        best = option
                elif control_axis == "w":
                    if best_w is None or option["distance"] < best_w["distance"]:
                        best_w = option
                elif best_h is None or option["distance"] < best_h["distance"]:
                    best_h = option

        if keep_proportion:
            if best:
                return best["w"], best["h"]
            return w, h

        if best_w and best_h:
            solved_corner = self._solve_corner_snap_size(parent, anchor_scene, w, h, best_w, best_h)
            if solved_corner:
                return solved_corner

        snapped_w = best_w["w"] if best_w else w
        snapped_h = best_h["h"] if best_h else h
        return snapped_w, snapped_h
    
    def update_handle_size(self):
        scene = self.scene()
        if not scene:
            return
            
        # Usamos a nossa inteligência de magnetismo para definir o tamanho da "pegada"
        size = _get_dynamic_snap_distance(scene)
        # Limitamos para a alça não ficar bizarramente gigante ou invisível
        handle_size = max(8.0, min(25.0, size))
        half = handle_size / 2.0
        
        self.setRect(-half, -half, handle_size, handle_size)

    def _keep_proportion(self):
        parent = self.parentItem()
        group_id = getattr(parent, 'group_id', None)
        grouped = False
        scene = parent.scene() if parent is not None else None
        if group_id is not None and scene is not None:
            members = [
                item for item in scene.items()
                if getattr(item, 'group_id', None) == group_id
                and item.parentItem() is None
                and not getattr(item, 'is_document_background', False)
                and item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            ]
            selected = set(scene.selectedItems())
            grouped = len(members) >= 2 and all(item in selected for item in members)
        return (
            grouped
            or getattr(parent, 'keep_proportion', True)
            or getattr(self, '_shift_proportion', False)
        )

    def paint(self, painter, option, widget=None):
        self.update_handle_size()
        super().paint(painter, option, widget)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_resizing = True
            parent = self.parentItem()
            if parent:
                self._shift_proportion = False
                self._initial_w, self._initial_h = _item_size(parent)
                self.initial_ratio = self._initial_w / self._initial_h if self._initial_h > 0 else 1.0
                anchor_local = self._anchor_local_point(self._initial_w, self._initial_h)
                self._anchor_scene = parent.mapToScene(anchor_local)
                if getattr(parent, 'shape_type', '') == 'line':
                    self._anchor_scene = parent.mapToScene(QPointF(self._initial_w if self.x_dir < 0 else 0, self._initial_h/2))
                scene = parent.scene()
                if scene and scene.views():
                    window = scene.views()[0].window()
                    if hasattr(window, 'begin_group_resize'):
                        window.begin_group_resize(
                            parent, self._anchor_scene, self._initial_w, self._initial_h
                        )
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_resizing:
            parent = self.parentItem()
            if parent:
                self._shift_proportion = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier) and isinstance(parent, RectangleItem)
                anchor_scene = self._anchor_scene or parent.mapToScene(
                    self._anchor_local_point(self._initial_w, self._initial_h)
                )
                scene_delta = QPointF(
                    event.scenePos().x() - anchor_scene.x(),
                    event.scenePos().y() - anchor_scene.y(),
                )
                if getattr(parent, 'shape_type', '') == 'line':
                    length = max(1, math.hypot(scene_delta.x(), scene_delta.y()))
                    angle = math.atan2(scene_delta.y(), scene_delta.x())
                    window = None
                    if parent.scene() and parent.scene().views():
                        window = parent.scene().views()[0].window()
                    group_session = getattr(window, '_group_resize_session', None)
                    if group_session and group_session.get('leader') is parent:
                        fixed_rotation = float(group_session['rotation'])
                        angle = math.radians(
                            fixed_rotation - (180 if self.x_dir < 0 else 0)
                        )
                        direction = QPointF(math.cos(angle), math.sin(angle))
                        length = max(
                            1,
                            scene_delta.x() * direction.x()
                            + scene_delta.y() * direction.y(),
                        )
                    if self._shift_proportion:
                        angle = round(angle / (math.pi / 4)) * math.pi / 4
                    endpoint = anchor_scene + QPointF(length * math.cos(angle), length * math.sin(angle))
                    center = (anchor_scene + endpoint) / 2
                    parent.resize_custom(length, self._initial_h)
                    parent.setRotation(math.degrees(angle) + (180 if self.x_dir < 0 else 0))
                    parent._resizing_from_handle = True
                    try:
                        parent.setPos(center.x()-length/2, center.y()-self._initial_h/2)
                    finally:
                        parent._resizing_from_handle = False
                    if window is not None and hasattr(window, 'update_group_resize'):
                        window.update_group_resize(parent, length, self._initial_h)
                    event.accept()
                    return
                local_delta = _unrotated_vector(scene_delta, parent.rotation())
                new_w, new_h = self._resize_from_local_delta(local_delta)
                new_w, new_h = self._snap_size_to_guides(parent, anchor_scene, new_w, new_h)

                if hasattr(parent, 'resize_from_handle'):
                    parent.resize_from_handle(new_w, new_h)
                    new_anchor_local = self._anchor_local_point(new_w, new_h)
                    new_pos = _item_pos_for_local_scene_point(parent, new_anchor_local, anchor_scene)
                    parent._resizing_from_handle = True
                    try:
                        parent.setPos(new_pos)
                    finally:
                        parent._resizing_from_handle = False
                    if parent.scene() and parent.scene().views():
                        window = parent.scene().views()[0].window()
                        if hasattr(window, 'update_group_resize'):
                            window.update_group_resize(parent, new_w, new_h)
                
                if parent.scene():
                    parent.scene().update() 
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._is_resizing:
            self._is_resizing = False
            self._shift_proportion = False
            self._anchor_scene = None
            # Gatilho do Undo/Redo
            if self.scene() and self.scene().views():
                win = self.scene().views()[0].window()
                if hasattr(win, 'save_snapshot'):
                    win.save_snapshot()
                if hasattr(win, 'end_group_resize'):
                    win.end_group_resize()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class SelectionResizeHandle(QGraphicsRectItem):
    """Alça da moldura temporária criada por uma seleção múltipla."""

    def __init__(self, frame, x_dir, y_dir, cursor):
        super().__init__(-6, -6, 12, 12, frame)
        from core.themes import theme_color
        self.x_dir = x_dir
        self.y_dir = y_dir
        self._frame = frame
        self._active = False
        self.setBrush(QBrush(QColor("#ffffff")))
        self.setPen(QPen(QColor(theme_color('canvas_selection')), 2))
        self.setCursor(cursor)
        self.setZValue(2)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        rect = QRectF(self._frame.rect())
        anchor_x = rect.right() if self.x_dir < 0 else rect.left() if self.x_dir > 0 else rect.center().x()
        anchor_y = rect.bottom() if self.y_dir < 0 else rect.top() if self.y_dir > 0 else rect.center().y()
        self._anchor = QPointF(anchor_x, anchor_y)
        self._initial_rect = rect
        self._pointer_offset = event.scenePos() - self.scenePos()
        self._active = self._frame.window.begin_multi_selection_resize(
            self._anchor, rect
        )
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._active:
            super().mouseMoveEvent(event)
            return
        delta = event.scenePos() - self._pointer_offset - self._anchor
        width = max(self._initial_rect.width(), 0.001)
        height = max(self._initial_rect.height(), 0.001)
        if self.x_dir and self.y_dir:
            base = QPointF(width * self.x_dir, height * self.y_dir)
            scale = (delta.x() * base.x() + delta.y() * base.y()) / (
                base.x() ** 2 + base.y() ** 2
            )
        elif self.x_dir:
            scale = (delta.x() * self.x_dir) / width
        else:
            scale = (delta.y() * self.y_dir) / height
        self._frame.window.update_multi_selection_resize(max(0.02, scale))
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._active:
            self._active = False
            self._frame.window.end_multi_selection_resize()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class SelectionTransformFrame(QGraphicsRectItem):
    """Moldura única da seleção múltipla, sem entrar no modelo salvo."""

    HANDLE_SPECS = (
        (-1, -1, Qt.CursorShape.SizeFDiagCursor),
        (0, -1, Qt.CursorShape.SizeVerCursor),
        (1, -1, Qt.CursorShape.SizeBDiagCursor),
        (1, 0, Qt.CursorShape.SizeHorCursor),
        (1, 1, Qt.CursorShape.SizeFDiagCursor),
        (0, 1, Qt.CursorShape.SizeVerCursor),
        (-1, 1, Qt.CursorShape.SizeBDiagCursor),
        (-1, 0, Qt.CursorShape.SizeHorCursor),
    )

    def __init__(self, window):
        super().__init__()
        from core.themes import theme_color
        self.window = window
        self._is_selection_overlay = True
        pen = QPen(QColor(theme_color('canvas_selection')), 1.5, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(Qt.BrushStyle.NoBrush)
        self.setZValue(10_000_000)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.handles = [
            SelectionResizeHandle(self, x_dir, y_dir, cursor)
            for x_dir, y_dir, cursor in self.HANDLE_SPECS
        ]
        self.hide()

    def update_bounds(self, bounds):
        bounds = QRectF(bounds)
        if self.rect() != bounds:
            self.setRect(bounds)
        left, right = bounds.left(), bounds.right()
        top, bottom = bounds.top(), bounds.bottom()
        cx, cy = bounds.center().x(), bounds.center().y()
        positions = (
            QPointF(left, top), QPointF(cx, top), QPointF(right, top),
            QPointF(right, cy), QPointF(right, bottom), QPointF(cx, bottom),
            QPointF(left, bottom), QPointF(left, cy),
        )
        for handle, position in zip(self.handles, positions):
            handle.setPos(position)


RESIZE_HANDLE_SPECS = (
    ("top_left", -1, -1, Qt.CursorShape.SizeFDiagCursor),
    ("top", 0, -1, Qt.CursorShape.SizeVerCursor),
    ("top_right", 1, -1, Qt.CursorShape.SizeBDiagCursor),
    ("right", 1, 0, Qt.CursorShape.SizeHorCursor),
    ("bottom_right", 1, 1, Qt.CursorShape.SizeFDiagCursor),
    ("bottom", 0, 1, Qt.CursorShape.SizeVerCursor),
    ("bottom_left", -1, 1, Qt.CursorShape.SizeBDiagCursor),
    ("left", -1, 0, Qt.CursorShape.SizeHorCursor),
)


def _item_size(item):
    if hasattr(item, 'rect'):
        rect = item.rect()
    else:
        rect = item.pixmap().rect()
    return float(rect.width()), float(rect.height())


def _handle_position(name, w, h):
    positions = {
        "top_left": QPointF(0, 0),
        "top": QPointF(w / 2, 0),
        "top_right": QPointF(w, 0),
        "right": QPointF(w, h / 2),
        "bottom_right": QPointF(w, h),
        "bottom": QPointF(w / 2, h),
        "bottom_left": QPointF(0, h),
        "left": QPointF(0, h / 2),
    }
    return positions[name]


def _init_resize_handles(item):
    item.resize_handles = {}
    for name, x_dir, y_dir, cursor in RESIZE_HANDLE_SPECS:
        handle = ResizeHandle(item, name, x_dir, y_dir, cursor)
        handle.hide()
        item.resize_handles[name] = handle
    item.handle_br = item.resize_handles["bottom_right"]
    _update_resize_handles(item)


def _update_resize_handles(item):
    if not hasattr(item, 'resize_handles'):
        return
    w, h = _item_size(item)
    for name, handle in item.resize_handles.items():
        handle.update_handle_size()
        handle.setPos(_handle_position(name, w, h))


def _set_resize_handles_visible(item, visible):
    if not hasattr(item, 'resize_handles'):
        return
    scene = item.scene()
    if visible and scene:
        roots = {
            selected.parentItem()
            if isinstance(selected.parentItem(), RectangleItem)
            else selected
            for selected in scene.selectedItems()
            if hasattr(selected, 'resize_handles')
        }
        if len(roots) >= 2:
            visible = False
    for handle in item.resize_handles.values():
        handle.setVisible(visible)


class Guideline(QGraphicsLineItem):
    def __init__(self, position_px, is_vertical=True):
        super().__init__()
        self.is_vertical = is_vertical
        self._is_mouse_dragging = False
        
        if is_vertical:
            self.setLine(0, -20000, 0, 40000)
            self.setPos(position_px, 0)
        else:
            self.setLine(-20000, 0, 40000, 0)
            self.setPos(0, position_px)

        from core.themes import theme_color
        pen = QPen(QColor(theme_color('guide')), 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        self.setPen(pen)

        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable | 
                      QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setZValue(10)

    def shape(self):
        path = super().shape()
        stroker = QPainterPathStroker()
        
        hitbox_width = 15.0
        if self.scene():
            # Aproveitamos a nossa inteligência de zoom/escala para a espessura do clique
            hitbox_width = _get_dynamic_snap_distance(self.scene())
            # Limitamos para não ficar nem impossível de clicar, nem cobrir a tela toda
            hitbox_width = max(10.0, min(40.0, hitbox_width))
            
        stroker.setWidth(hitbox_width) 
        return stroker.createStroke(path)
    
    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)
    
    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            new_pos = value
            
            if self.is_vertical:
                x = new_pos.x()
                if self._is_mouse_dragging:
                    rect = _document_rect(self.scene())
                    snap_dist = _get_dynamic_snap_distance(self.scene())
                    candidates = [0, rect.width() / 2, rect.width()]
                    for c in candidates:
                        if abs(x - c) < snap_dist:
                            x = c
                            break
                return QPointF(x, 0)
            else:
                y = new_pos.y()
                if self._is_mouse_dragging:
                    rect = _document_rect(self.scene())
                    snap_dist = _get_dynamic_snap_distance(self.scene())
                    candidates = [0, rect.height() / 2, rect.height()]
                    for c in candidates:
                        if abs(y - c) < snap_dist:
                            y = c
                            break
                return QPointF(0, y)
            
        # --- Feedback visual: Muda apenas a cor quando selecionada ---
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            is_selected = bool(value)
            from core.themes import theme_color
            color = theme_color('warning' if is_selected else 'guide')
            
            pen = QPen(QColor(color), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self.setPen(pen)
                
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_mouse_dragging = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_mouse_dragging = False
        super().mouseReleaseEvent(event)
        # Salva snapshot após mover a guia, igual aos outros itens
        scene = self.scene()
        if scene and scene.views():
            win = scene.views()[0].window()
            rulers = getattr(win, 'ruler_workspace', None)
            if (event.button() == Qt.MouseButton.LeftButton and rulers
                    and self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable):
                ruler = rulers.left if self.is_vertical else rulers.top
                if ruler.rect().contains(ruler.mapFromGlobal(event.screenPos())):
                    scene.removeItem(self)
            if hasattr(win, 'save_snapshot'):
                win.save_snapshot()


class ImageItem(QGraphicsPixmapItem):
    SNAP_DISTANCE = 15

    def __init__(self, pixmap_path=None, parent=None, *, pixmap_data=None, asset_reference=None):
        pixmap, logical_w, logical_h, proxy_scale = (
            _load_proxy_pixmap_bytes(pixmap_data)
            if pixmap_data is not None else _load_proxy_pixmap(pixmap_path)
        )
            
        super().__init__(pixmap)
        self._original_path = asset_reference or pixmap_path or ""
        self._logical_w = logical_w
        self._logical_h = logical_h
        self._current_w = logical_w
        self._current_h = logical_h
        self._proxy_scale = proxy_scale
        
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self._proxy_pixmap = pixmap
        self.setZValue(1)
        
        self.keep_proportion = True
        self.has_link = False
        self.link_key = ""
        self.mask_shape_id = None
        self.mask_order = 0
        _init_resize_handles(self)
        self.update_center()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            parent = self.parentItem()
            mask_allows_edit = not isinstance(parent, RectangleItem) or bool(
                getattr(parent, '_mask_editing', False)
            )
            can_resize = mask_allows_edit and self.isSelected() and bool(
                self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            )
            _set_resize_handles_visible(self, can_resize)

        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            new_pos = value
            w, h = self._current_w, self._current_h
            return _snap_position_to_guides(self, new_pos, w, h)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            _queue_selection_frame_refresh(self)
        return super().itemChange(change, value)

    def rect(self):
        return QRectF(0, 0, self._current_w, self._current_h)
        
    def boundingRect(self):
        return self.rect()

    def shape(self):
        path = QPainterPath()
        path.addRect(self.rect())
        parent = self.parentItem()
        if isinstance(parent, RectangleItem) and not getattr(parent, '_mask_editing', False):
            path = path.intersected(self.mapFromItem(parent, parent.drawing_path()))
        return path

    def contains(self, point):
        return self.shape().contains(point)
        
    def paint(self, painter, option, widget=None):
        def draw_content():
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(self.rect(), self.pixmap(), QRectF(self.pixmap().rect()))
        parent = self.parentItem()
        if isinstance(parent, RectangleItem) and getattr(parent, '_mask_editing', False):
            _paint_with_mask_edit_fade(
                self, painter,
                lambda: _paint_with_document_fade(self, painter, draw_content),
            )
        elif isinstance(parent, RectangleItem):
            _paint_with_mask_clip(
                self, painter,
                lambda: _paint_with_document_fade(self, painter, draw_content),
            )
        else:
            _paint_with_document_fade(self, painter, draw_content)

    def update_center(self):
        r = self.rect()
        self.setTransformOriginPoint(r.width() / 2, r.height() / 2)

    def resize_by_longest_side(self, size_px):
        w = self._logical_w
        h = self._logical_h
        if w > h:
            new_w = size_px
            new_h = (h * size_px) / w
        else:
            new_h = size_px
            new_w = (w * size_px) / h
        self.resize_custom(new_w, new_h)

    def resize_custom(self, w, h):
        if w <= 0 or h <= 0: return
        self.prepareGeometryChange()
        self._current_w = w
        self._current_h = h
        if hasattr(self, 'handle_br'):
            _update_resize_handles(self)
        self.update_center()

    def resize_from_handle(self, w, h):
        self.resize_custom(w, h)

    def hide_resize_handles(self):
        _set_resize_handles_visible(self, False)

    def mousePressEvent(self, event):
        scene = self.scene()
        pre_selected = scene.selectedItems() if scene else []

        super().mousePressEvent(event)

        if event.button() == Qt.MouseButton.LeftButton:
            self._is_mouse_dragging = True
            if scene:
                post_selected = scene.selectedItems()
                drag_items = pre_selected if self in pre_selected else post_selected
                if self not in drag_items:
                    drag_items.append(self)
                scene._drag_start_positions = {i: i.pos() for i in drag_items}
                scene._group_raw_delta = None

    def mouseReleaseEvent(self, event):
        self._is_mouse_dragging = False
        scene = self.scene()
        has_moved = False
        if scene and hasattr(scene, '_drag_start_positions'):
            start_pos = scene._drag_start_positions.get(self)
            if start_pos is not None and start_pos != self.pos():
                has_moved = True
            scene._group_raw_delta = None
        
        super().mouseReleaseEvent(event)
        
        if has_moved and scene and scene.views():
            win = scene.views()[0].window()
            if hasattr(win, 'save_snapshot'):
                win.save_snapshot()

class RectangleItem(ImageItem):
    """Retângulo vetorial editável com as alças dos demais objetos."""
    def __init__(self, width, height, color='#ffffff'):
        super().__init__(None)
        self.fill_color = color
        self.shape_type = 'rectangle'
        self.line_body = True
        self.outline_enabled = False
        self.outline_color = '#000000'
        self.outline_width = mm_to_px(0.2)
        self.outline_position = 'inside'
        self.outline_join = 'miter'
        self.corner_radius = 0.0
        self.corner_radii = {
            'top_left': 0.0, 'top_right': 0.0,
            'bottom_right': 0.0, 'bottom_left': 0.0,
        }
        self.corner_radii_linked = True
        self.fill_opacity = 1.0
        self.outline_opacity = 1.0
        self.custom_name = 'Plano de fundo'
        self.keep_proportion = False
        self._mask_editing = False
        self._mask_overlay = None
        self.mask_group_id = None
        self.dynamic_image_field = ""
        self.dynamic_image_fit = "cover"
        self.resize_custom(width, height)

    def masked_images(self):
        return sorted(
            (
                child for child in self.childItems()
                if isinstance(child, ImageItem) and not isinstance(child, RectangleItem)
            ),
            key=lambda child: getattr(child, 'mask_order', 0),
        )

    def refresh_mask_structure(self):
        children = self.masked_images()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, False)
        if not self._mask_editing:
            # Fora do modo de enquadramento, a imagem é conteúdo da máscara:
            # pode ser selecionada pela lista de camadas, mas não intercepta
            # cliques nem pode ser arrastada diretamente sobre o canvas.
            for child in children:
                child.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                child.hide_resize_handles()
        if children:
            if self._mask_overlay is None:
                self._mask_overlay = MaskOutlineOverlay(self)
            self._mask_overlay.setVisible(bool(self.outline_enabled))
            self._mask_overlay.update()
        elif self._mask_overlay is not None:
            self._mask_overlay.setVisible(False)
        self.update()

    def paint(self, painter, option, widget=None):
        if getattr(self, 'is_document_background', False):
            painter.setClipRect(self.rect())
        from core.object_style import paint_shape_path
        def draw_content():
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            paint_shape_path(painter, self.drawing_path(), self.style_data())
        if getattr(self, 'is_document_background', False):
            draw_content()
        else:
            _paint_with_document_fade(self, painter, draw_content)

    def style_data(self):
        return {key: getattr(self, key) for key in (
            'shape_type', 'line_body', 'fill_color', 'fill_opacity', 'outline_enabled',
            'outline_color', 'outline_opacity', 'outline_width',
            'outline_position', 'outline_join', 'corner_radius',
            'corner_radii', 'corner_radii_linked', 'dynamic_image_field',
            'dynamic_image_fit')}

    def drawing_path(self):
        path = QPainterPath()
        if getattr(self, 'shape_type', 'rectangle') == 'line':
            radius = min(max(0, self.corner_radius), self.rect().width() / 2, self.rect().height() / 2)
            path.addRoundedRect(self.rect(), radius, radius)
        elif getattr(self, 'shape_type', 'rectangle') in ('ellipse', 'circle'):
            path.addEllipse(self.rect())
        else:
            from core.object_style import rounded_rect_path
            radii = dict(getattr(self, 'corner_radii', {}) or {})
            radii.setdefault('all', getattr(self, 'corner_radius', 0))
            path = rounded_rect_path(self.rect(), radii)
        return path

    def contains(self, point):
        return self.shape().contains(point)

    def shape(self):
        path = self.drawing_path()
        if getattr(self, 'shape_type', '') == 'line':
            stroker = QPainterPathStroker()
            stroker.setWidth(max(self.outline_width, 10))
            return path.united(stroker.createStroke(path))
        return path

    def boundingRect(self):
        from core.object_style import outline_margin
        if not hasattr(self, 'outline_enabled') or getattr(self, 'is_document_background', False):
            return self.rect()
        margin = outline_margin(self.style_data())
        if self.shape_type == 'line':
            margin = max(5, margin)
        return self.rect().adjusted(-margin, -margin, margin, margin)

    def resize_custom(self, w, h):
        if getattr(self, 'is_document_background', False) and not getattr(self, '_syncing_document', False):
            return
        old_w = getattr(self, '_current_w', 0.0)
        old_h = getattr(self, '_current_h', 0.0)
        children = self.masked_images() if hasattr(self, '_mask_editing') else []
        if self._mask_overlay is not None:
            self._mask_overlay.prepareGeometryChange()
        super().resize_custom(w, h)
        if children and old_w > 0 and old_h > 0 and not self._mask_editing:
            scale_x = w / old_w
            scale_y = h / old_h
            for child in children:
                child.setPos(child.x() * scale_x, child.y() * scale_y)
                child.resize_custom(child.rect().width() * scale_x,
                                    child.rect().height() * scale_y)
        if self._mask_overlay is not None:
            self._mask_overlay.update()

    def itemChange(self, change, value):
        if getattr(self, 'is_document_background', False):
            if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
                return QPointF(0, 0)
            if change == QGraphicsItem.GraphicsItemChange.ItemRotationChange:
                return 0.0
            if change == QGraphicsItem.GraphicsItemChange.ItemZValueChange:
                return -100.0
            if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
                _set_resize_handles_visible(self, False)
                return value
        return super().itemChange(change, value)

    def bind_document(self, rect):
        self.is_document_background = True
        self.outline_position = 'inside'
        self._syncing_document = True
        self.resize_custom(rect.width(), rect.height())
        self._syncing_document = False
        self.setPos(0, 0)
        self.setRotation(0)
        self.setZValue(-100)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        _set_resize_handles_visible(self, False)


class MaskOutlineOverlay(QGraphicsItem):
    """Contorno não interativo desenhado acima do conteúdo de uma máscara."""

    def __init__(self, shape):
        super().__init__(shape)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setZValue(1_000_000)

    def boundingRect(self):
        parent = self.parentItem()
        return parent.boundingRect() if parent else QRectF()

    def paint(self, painter, option, widget=None):
        parent = self.parentItem()
        if not isinstance(parent, RectangleItem) or not parent.outline_enabled:
            return
        from core.object_style import paint_shape_path
        data = parent.style_data()
        data['fill_opacity'] = 0.0
        paint_shape_path(painter, parent.drawing_path(), data)


class BackgroundItem(ImageItem):
    """
    Herdando de ImageItem, o fundo atua como um PowerClip (Máscara de Corte).
    Ele ganha alças de redimensionamento e vira uma camada livre (Z-Value -100), 
    mas é renderizado estritamente dentro da área da prancheta.
    """
    def __init__(self, pixmap_path=None, parent=None, *, pixmap_data=None, asset_reference=None):
        super().__init__(
            pixmap_path, parent, pixmap_data=pixmap_data,
            asset_reference=asset_reference,
        )
        self.setZValue(-100)

    def paint(self, painter, option, widget=None):
        """MÁGICA VISUAL: Corta a pintura da imagem nas bordas exatas do documento."""
        if self.scene():
            path = QPainterPath()
            path.addRect(_document_rect(self.scene()))
            local_path = self.mapFromScene(path) # Traduz as coordenadas do documento para as da imagem
            
            # Aplica a máscara (PowerClip)
            painter.setClipPath(local_path)
            
        super().paint(painter, option, widget)

    def shape(self):
        path = QPainterPath()
        path.addRect(self.rect())
        return path
    
class SignatureItem(QGraphicsPixmapItem):
    SNAP_DISTANCE = 15

    def __init__(self, pixmap_path=None, parent=None, *, pixmap_data=None, asset_reference=None):
        pixmap, logical_w, logical_h, proxy_scale = (
            _load_proxy_pixmap_bytes(pixmap_data)
            if pixmap_data is not None else _load_proxy_pixmap(pixmap_path)
        )
        
        super().__init__(pixmap)
        self._original_path = asset_reference or pixmap_path or ""
        self._logical_w = logical_w
        self._logical_h = logical_h
        self._current_w = logical_w
        self._current_h = logical_h
        self._proxy_scale = proxy_scale
        self.signature_id = f"sig-{uuid4().hex}"
        
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self._proxy_pixmap = pixmap
        self.setZValue(201)
        
        self.keep_proportion = True
        _init_resize_handles(self)
        self.update_center()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            can_resize = self.isSelected() and bool(
                self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            )
            _set_resize_handles_visible(self, can_resize)

        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            new_pos = value
            w, h = self._current_w, self._current_h
            return _snap_position_to_guides(self, new_pos, w, h)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            _queue_selection_frame_refresh(self)
        return super().itemChange(change, value)

    def rect(self):
        return QRectF(0, 0, self._current_w, self._current_h)
        
    def boundingRect(self):
        return self.rect()

    def shape(self):
        path = QPainterPath()
        path.addRect(self.rect())
        return path

    def contains(self, point):
        return self.rect().contains(point)
        
    def paint(self, painter, option, widget=None):
        def draw_content():
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(self.rect(), self.pixmap(), QRectF(self.pixmap().rect()))
        _paint_with_document_fade(self, painter, draw_content)

    def update_center(self):
        r = self.rect()
        self.setTransformOriginPoint(r.width() / 2, r.height() / 2)

    def resize_by_longest_side(self, size_px):
        w = self._logical_w
        h = self._logical_h
        if w > h:
            new_w = size_px
            new_h = (h * size_px) / w
        else:
            new_h = size_px
            new_w = (w * size_px) / h
        self.resize_custom(new_w, new_h)

    def resize_custom(self, w, h):
        if w <= 0 or h <= 0: return
        self.prepareGeometryChange()
        self._current_w = w
        self._current_h = h
        if hasattr(self, 'handle_br'):
            _update_resize_handles(self)
        self.update_center()

    def resize_from_handle(self, w, h):
        self.resize_custom(w, h)

    def hide_resize_handles(self):
        _set_resize_handles_visible(self, False)

    def mousePressEvent(self, event):
        scene = self.scene()
        pre_selected = scene.selectedItems() if scene else []

        super().mousePressEvent(event)

        if event.button() == Qt.MouseButton.LeftButton:
            self._is_mouse_dragging = True
            if scene:
                post_selected = scene.selectedItems()
                drag_items = pre_selected if self in pre_selected else post_selected
                if self not in drag_items:
                    drag_items.append(self)
                scene._drag_start_positions = {i: i.pos() for i in drag_items}
                scene._group_raw_delta = None

    def mouseReleaseEvent(self, event):
        self._is_mouse_dragging = False
        scene = self.scene()
        has_moved = False
        if scene and hasattr(scene, '_drag_start_positions'):
            start_pos = scene._drag_start_positions.get(self)
            if start_pos is not None and start_pos != self.pos():
                has_moved = True
            scene._group_raw_delta = None
        
        super().mouseReleaseEvent(event)
        
        if has_moved and scene and scene.views():
            win = scene.views()[0].window()
            if hasattr(win, 'save_snapshot'):
                win.save_snapshot()


class BleedTextItem(QGraphicsTextItem):
    """Subclasse para evitar o corte visual de letras massivas que vazam a caixa lógica (ex: perna do j)."""
    def paint(self, painter, option, widget=None):
        # Retira somente a moldura de foco do item, preservando cursor e seleção
        # de caracteres desenhados pelo documento de texto.
        clean_option = QStyleOptionGraphicsItem(option)
        clean_option.state &= ~QStyle.StateFlag.State_HasFocus
        _paint_with_document_fade(
            self, painter,
            lambda: super(BleedTextItem, self).paint(painter, clean_option, widget),
        )

    def boundingRect(self):
        rect = super().boundingRect()
        # Expande a área de repintura em 200px para cima e para baixo. 
        # Isso afeta apenas o motor de vídeo da tela, não altera posições ou exportações.
        rect.adjust(0, -200, 0, 200)
        return rect

    def mouseDoubleClickEvent(self, event):
        if self.textInteractionFlags() & Qt.TextInteractionFlag.TextEditable:
            if self.document().documentLayout().hitTest(event.pos(), Qt.HitTestAccuracy.ExactHit) < 0 or not self.toPlainText():
                cursor = self.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.setTextCursor(cursor)
                self.setFocus()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.scene().views()[0].window().canvas_edit.finish()
            event.accept()
            return
        super().keyPressEvent(event)


class DesignerBox(QGraphicsRectItem):
    SNAP_DISTANCE = 15

    def mouseDoubleClickEvent(self, event):
        if self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable:
            self.scene().views()[0].window().canvas_edit.begin(self)
            cursor = self.text_item.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.text_item.setTextCursor(cursor)
            self.text_item.setFocus()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def __init__(self, x=0, y=0, w=300, h=60, text="Placeholder"):
        super().__init__(0, 0, w, h)
        self.setPos(x, y)
        
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable | 
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        
        self.setPen(QPen(Qt.GlobalColor.red, 2, Qt.PenStyle.DashLine))
        self.setBrush(QBrush(QColor(255, 255, 255, 50)))
        self.setZValue(101)

        self.state = TextState(html_content=text)
        
        self.text_item = BleedTextItem("", self)
        self.text_item.setDefaultTextColor(Qt.GlobalColor.black)
        
        # CORREÇÃO CRÍTICA: Zera a margem fantasma nativa do Editor para equiparar ao Gerador
        self.text_item.document().setDocumentMargin(0)
        
        self.text_item.document().contentsChanged.connect(self.recalculate_text_position)

        self.text_item.setTextWidth(w)
        self.text_item.setPos(0, 0)
        
        self.apply_state()
        self.update_center()
        
        # --- Instanciar Alças de Redimensionamento ---
        self.keep_proportion = True
        _init_resize_handles(self)

    def setRect(self, *args):
        super().setRect(*args)
        if hasattr(self, 'handle_br'):
            _update_resize_handles(self)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            can_resize = self.isSelected() and bool(
                self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            )
            _set_resize_handles_visible(self, can_resize)

        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            new_pos = value
            rect = self.rect()
            w, h = rect.width(), rect.height()
            return _snap_position_to_guides(self, new_pos, w, h)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            _queue_selection_frame_refresh(self)
        return super().itemChange(change, value)
    
    def paint(self, painter, option, widget=None):
        multi_selection = bool(
            self.scene() and getattr(self.scene(), '_multi_selection_active', False)
        )
        if self.isSelected() and not multi_selection:
            from core.themes import theme_color
            self.setPen(QPen(QColor(theme_color('canvas_selection')), 2, Qt.PenStyle.DashLine))
            self.setBrush(QBrush(QColor(0, 100, 255, 30)))
        else:
            from core.themes import theme_color
            self.setPen(QPen(QColor(theme_color('canvas_outline')), 1, Qt.PenStyle.DotLine))
            self.setBrush(QBrush(QColor(255, 255, 255, 10)))
        super().paint(painter, option, widget)

    
    def resize_from_handle(self, w, h):
        self.setRect(0, 0, w, h)
        self.recalculate_text_position()
        self.update_center()

    def hide_resize_handles(self):
        _set_resize_handles_visible(self, False)
    
    def set_alignment(self, align_str):
        self.state.align = align_str
        self.apply_state()

    def set_vertical_alignment(self, align_str):
        self.state.vertical_align = align_str
        self.apply_state()

    def set_block_format(self, indent=None, line_height=None):
        if indent is not None: self.state.indent_px = indent
        if line_height is not None: self.state.line_height = line_height
        self.apply_state()

    def get_placeholders(self):
        return variables_in_html(self.state.html_content)
    

    def apply_state(self):
        """Reconstrói todo o documento visual com base na Fonte da Verdade."""
        self.text_item.blockSignals(True)
        
        # 1. Limpeza Retroativa e Injeção de Conteúdo (conserta JSONs antigos já infectados)
        html = re.sub(r"font-family\s*:[^;\"]+;?", "", self.state.html_content)
        html = re.sub(r"font-size\s*:[^;\"]+;?", "", html)
        html = re.sub(r"color\s*:[^;\"]+;?", "", html)
        html = re.sub(r"background-color\s*:[^;\"]+;?", "", html)
        html = normalize_text_decoration(html)
        html = re.sub(r"(?i)<a\b[^>]*>", "", html)
        html = re.sub(r"(?i)</a>", "", html)
        html = re.sub(r"(?i)<h[1-6]([^>]*)>", r"<p\1>", html)
        html = re.sub(r"(?i)</h[1-6]>", "</p>", html)
        
        rich = getattr(self.state, 'rich_text_version', 0) == 1
        self.text_item.setHtml(sanitize_text_html(self.state.html_content if rich else html))
        
        # 2. Aplicar Fonte Global e Cor NATIVA (SEMPRE após o setHtml, pois ele reseta o documento)
        font = QFont(self.state.font_family, self.state.font_size)
        font.setStyleStrategy(QFont.StyleStrategy.ForceOutline)
        self.text_item.setFont(font)
        self.text_item.document().setDefaultFont(font)
        
        color = QColor(getattr(self.state, 'font_color', '#000000'))
        
        cursor_color = QTextCursor(self.text_item.document())
        cursor_color.select(QTextCursor.SelectionType.Document)
        char_fmt = QTextCharFormat()
        char_fmt.setForeground(QBrush(color))
        if not rich:
            cursor_color.mergeCharFormat(char_fmt)
        
        # 3. Aplicar Alinhamento Horizontal
        opt = self.text_item.document().defaultTextOption()
        if self.state.align == "center": opt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        elif self.state.align == "right": opt.setAlignment(Qt.AlignmentFlag.AlignRight)
        elif self.state.align == "justify": opt.setAlignment(Qt.AlignmentFlag.AlignJustify)
        else: opt.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.text_item.document().setDefaultTextOption(opt)
        
        # 4. Aplicar Margens e Entrelinhas
        cursor = QTextCursor(self.text_item.document())
        cursor.select(QTextCursor.SelectionType.Document)
        fmt = QTextBlockFormat()
        fmt.setTextIndent(self.state.indent_px)
        fmt.setLineHeight(self.state.line_height * 100.0, 1)
        cursor.mergeBlockFormat(fmt)

        # 5. Zerar margens para sistema de ancoragem livre
        root_frame = self.text_item.document().rootFrame()
        frame_fmt = root_frame.frameFormat()
        frame_fmt.setMargin(0)
        root_frame.setFrameFormat(frame_fmt)
        
        self.text_item.blockSignals(False)
        self.recalculate_text_position()

    def recalculate_text_position(self):
        self.text_item.setTextWidth(self.rect().width())
        doc = self.text_item.document()
        layout = doc.documentLayout()
        logical_h = layout.documentSize().height()
        box_h = self.rect().height()
        
        # --- CÁLCULO DA TINTA REAL (Ignorando Ascender/Descender invisível) ---
        real_top = 0
        real_bottom = logical_h
        
        first_block = doc.begin()
        if first_block.isValid():
            text_layout = first_block.layout()
            if text_layout.lineCount() > 0:
                first_line = text_layout.lineAt(0)
                text_str = first_block.text()[first_line.textStart() : first_line.textStart() + first_line.textLength()]
                if text_str.strip():
                    ink_top, _ = line_reference_ink_bounds(doc, first_block, first_line)
                    real_top = first_line.y() + first_line.ascent() + ink_top

        last_block = doc.begin()
        last_valid_block = last_block
        while last_block.isValid():
            if last_block.text().strip(): last_valid_block = last_block
            last_block = last_block.next()
            
        if last_valid_block.isValid():
            text_layout = last_valid_block.layout()
            if text_layout.lineCount() > 0:
                last_line = text_layout.lineAt(text_layout.lineCount() - 1)
                text_str = last_valid_block.text()[last_line.textStart() : last_line.textStart() + last_line.textLength()]
                if text_str.strip():
                    _, ink_bottom = line_reference_ink_bounds(doc, last_valid_block, last_line)
                    block_y = layout.blockBoundingRect(last_valid_block).y()
                    real_bottom = block_y + last_line.y() + last_line.ascent() + ink_bottom
                    
        content_h = real_bottom - real_top
        
        y = 0
        if self.state.vertical_align == "center":
            y = (box_h - content_h) / 2 - real_top
        elif self.state.vertical_align == "bottom":
            y = box_h - content_h - real_top
        else: # Top
            y = -real_top
            
        self.text_item.setPos(0, y)

    def update_center(self):
        rect = self.rect()
        self.setTransformOriginPoint(rect.center())

    def mousePressEvent(self, event):
        scene = self.scene()
        pre_selected = scene.selectedItems() if scene else []

        super().mousePressEvent(event)

        if event.button() == Qt.MouseButton.LeftButton:
            self._is_mouse_dragging = True
            if scene:
                post_selected = scene.selectedItems()
                drag_items = pre_selected if self in pre_selected else post_selected
                if self not in drag_items:
                    drag_items.append(self)
                scene._drag_start_positions = {i: i.pos() for i in drag_items}
                scene._group_raw_delta = None

    def mouseReleaseEvent(self, event):
        self._is_mouse_dragging = False
        scene = self.scene()
        has_moved = False
        if scene and hasattr(scene, '_drag_start_positions'):
            start_pos = scene._drag_start_positions.get(self)
            if start_pos is not None and start_pos != self.pos():
                has_moved = True
            scene._group_raw_delta = None
        
        super().mouseReleaseEvent(event)
        
        if has_moved and scene and scene.views():
            win = scene.views()[0].window()
            if hasattr(win, 'save_snapshot'):
                win.save_snapshot()
