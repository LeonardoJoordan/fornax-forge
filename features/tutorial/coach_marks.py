"""Destaques reutilizáveis para os tutoriais interativos."""

from __future__ import annotations

import math
from html import escape

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QRegion
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.themes import theme_color, themed_style
from core.dialog_buttons import ACCEPT_STYLE
from core.resources import navigation_icon_path
from core.theme_icons import themed_svg_icon


class Spotlight(QWidget):
    """Desenha somente um pulso ao redor do controle orientado."""

    def __init__(self, host: QWidget):
        super().__init__(host)
        self._host = host
        self._target_rect = QRect()
        self._phase = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.hide()
        self._pulse = QTimer(self)
        self._pulse.setInterval(35)
        self._pulse.timeout.connect(self._advance_pulse)

    def set_target_rect(self, rect: QRect):
        self._target_rect = QRect(rect)
        if self._target_rect.isValid():
            # A máscara cobre o alvo e seu contorno. A camada continua
            # transparente para o mouse, portanto o controle real permanece
            # diretamente clicável durante a orientação.
            outer = QRegion(self._target_rect.adjusted(-7, -7, 7, 7))
            self.setMask(outer)
        else:
            self.setMask(QRegion())
        self.update()

    def start(self):
        self.setGeometry(self._host.rect())
        self.set_target_rect(self._target_rect)
        self.show()
        self.raise_()
        self._pulse.start()

    def stop(self):
        self._pulse.stop()
        self.hide()

    def _advance_pulse(self):
        self._phase = (self._phase + 0.13) % (math.pi * 2)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._target_rect.isValid():
            pulse = (math.sin(self._phase) + 1.0) / 2.0
            color = QColor(theme_color("accent"))
            fill = QColor(color)
            fill.setAlpha(38 + int(55 * pulse))
            painter.setBrush(fill)
            color.setAlpha(175 + int(80 * pulse))
            painter.setPen(QPen(color, 3.0 + pulse * 2.0))
            painter.drawRoundedRect(self._target_rect, 8, 8)


class TutorialCard(QFrame):
    backRequested = Signal()
    nextRequested = Signal()
    skipRequested = Signal()

    def __init__(self, host: QWidget):
        super().__init__(host)
        self._host = host
        self._drag_offset = None
        self._manually_positioned = False
        self.setObjectName("tutorialCard")
        self.setMinimumSize(540, 215)
        self.setMaximumWidth(680)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(9)
        self.progress = QLabel()
        self.progress.setObjectName("tutorialProgress")
        self.progress.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.title = QLabel()
        self.title.setObjectName("tutorialTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.action = QLabel()
        self.action.setObjectName("tutorialAction")
        self.action.setWordWrap(True)
        self.action.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body = QLabel()
        self.body.setObjectName("tutorialBody")
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.link = QLabel()
        self.link.setObjectName("tutorialLink")
        self.link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.link.setOpenExternalLinks(True)
        self.link.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        for label in (self.progress, self.title, self.action, self.body):
            label.installEventFilter(self)
        layout.addWidget(self.progress)
        layout.addWidget(self.title)
        layout.addStretch(1)
        layout.addWidget(self.action)
        layout.addWidget(self.body)
        layout.addWidget(self.link)
        layout.addStretch(1)

        buttons = QGridLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setHorizontalSpacing(8)
        buttons.setColumnStretch(1, 1)
        buttons.setColumnStretch(3, 1)
        self.skip = QPushButton(tr("Pular tutorial"))
        self.back = QPushButton(tr("Voltar"))
        self.next = QPushButton(tr("Continuar"))
        self.next.setObjectName("primary")
        self.skip.clicked.connect(self.skipRequested)
        self.back.clicked.connect(self.backRequested)
        self.next.clicked.connect(self.nextRequested)

        # O espaço dos três controles permanece estável mesmo quando uma
        # ação é ocultada. Assim o botão principal nunca sai do centro.
        for button in (self.back, self.next, self.skip):
            policy = button.sizePolicy()
            policy.setRetainSizeWhenHidden(True)
            button.setSizePolicy(policy)

        buttons.addWidget(self.back, 0, 0, Qt.AlignmentFlag.AlignLeft)
        buttons.addWidget(self.next, 0, 2, Qt.AlignmentFlag.AlignHCenter)
        buttons.addWidget(self.skip, 0, 4, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(buttons)

        themed_style(self, """
            QFrame#tutorialCard {
                background: @panel@; border: 1px solid @accent@;
                border-radius: 10px;
            }
            QLabel#tutorialProgress { color: @accent@; font-size: 10px; font-weight: 600; }
            QLabel#tutorialTitle { color: @text@; font-size: 15px; font-weight: 700; }
            QLabel#tutorialAction { color: @accent@; font-size: 13px; font-weight: 700; }
            QLabel#tutorialBody { color: @text@; font-size: 12px; }
            QLabel#tutorialLink { color: @accent@; font-size: 12px; }
        """)
        themed_style(self.next, ACCEPT_STYLE)
        secondary_style = """
            QPushButton {
                background: @button@; color: @text@; border: 1px solid @border@;
                border-radius: 5px; padding: 0 8px; text-align: center;
                font-size: 10px; font-weight: 400;
            }
            QPushButton:hover { background: @hover@; border-color: @border_strong@; }
            QPushButton:pressed { background: @selection@; border-color: @accent@; }
        """
        themed_style(self.skip, secondary_style)
        themed_style(self.back, secondary_style)
        self.back.setIcon(themed_svg_icon(navigation_icon_path('chevron-back')))
        self.skip.setIcon(themed_svg_icon(navigation_icon_path('chevron-right')))
        self.back.setIconSize(QRect(0, 0, 12, 12).size())
        self.skip.setIconSize(QRect(0, 0, 12, 12).size())
        self.skip.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.size_buttons()

    def reset_manual_position(self):
        self._manually_positioned = False
        self._drag_offset = None

    def _begin_drag(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        self._manually_positioned = True
        return True

    def _drag(self, event):
        if self._drag_offset is None or not event.buttons() & Qt.MouseButton.LeftButton:
            return False
        desired_global = event.globalPosition().toPoint() - self._drag_offset
        desired = self._host.mapFromGlobal(desired_global)
        margin = 8
        desired.setX(max(margin, min(desired.x(), self._host.width() - self.width() - margin)))
        desired.setY(max(margin, min(desired.y(), self._host.height() - self.height() - margin)))
        self.move(desired)
        return True

    def _end_drag(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._drag_offset is None:
            return False
        self._drag_offset = None
        return True

    def mousePressEvent(self, event):
        if self._begin_drag(event):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag(event):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._end_drag(event):
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def eventFilter(self, watched, event):
        if watched in (self.progress, self.title, self.action, self.body):
            if event.type() == QEvent.Type.MouseButtonPress and self._begin_drag(event):
                return True
            if event.type() == QEvent.Type.MouseMove and self._drag(event):
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and self._end_drag(event):
                return True
        return super().eventFilter(watched, event)

    def size_buttons(self):
        secondary_width = max(88, self.skip.sizeHint().width(), self.back.sizeHint().width())
        for button in (self.skip, self.back):
            button.setFixedSize(secondary_width, 24)
        self.next.setFixedSize(max(110, self.next.sizeHint().width()), 30)

    def set_important(self, important):
        border = "@warning@" if important else "@accent@"
        if important:
            self.setMinimumSize(720, 560)
            self.setMaximumWidth(820)
            self.body.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        else:
            self.setMinimumSize(540, 215)
            self.setMaximumWidth(680)
            self.body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        themed_style(self, f"""
            QFrame#tutorialCard {{
                background: @panel@; border: 2px solid {border}; border-radius: 10px;
            }}
            QLabel#tutorialProgress {{ color: {border}; font-size: 10px; font-weight: 600; }}
            QLabel#tutorialTitle {{ color: @text@; font-size: {'20px' if important else '17px'}; font-weight: 700; }}
            QLabel#tutorialAction {{ color: {border}; font-size: {'16px' if important else '13px'}; font-weight: 700; }}
            QLabel#tutorialBody {{ color: @text@; font-size: {'15px' if important else '12px'}; }}
            QLabel#tutorialLink {{ color: {border}; font-size: {'14px' if important else '12px'}; }}
        """)


class CoachMark(QObject):
    """Controla o destaque e o cartão de uma etapa em uma janela."""

    def __init__(self, host: QWidget):
        super().__init__(host)
        self.host = host
        self.target = None
        self.target_rect_provider = None
        self.highlight_target = True
        self.spotlight = Spotlight(host)
        self.card = TutorialCard(host)
        self.card.hide()
        host.installEventFilter(self)

    def show_step(
        self,
        *,
        target: QWidget | None,
        title: str,
        body: str,
        action_text: str = "",
        current: int,
        total: int,
        can_go_back: bool,
        next_text: str,
        wait_for_action: bool = False,
        target_rect_provider=None,
        important: bool = False,
        preserve_card_position: bool = False,
        link_text: str = "",
        link_url: str = "",
        highlight_target: bool = True,
    ):
        if self.target is not None:
            self.target.removeEventFilter(self)
        self.target = target
        self.target_rect_provider = target_rect_provider
        self.highlight_target = highlight_target
        if target is not None:
            target.installEventFilter(self)
        self.card.progress.setText(tr("ETAPA {atual} DE {total}").format(atual=current, total=total))
        self.card.title.setText(title)
        self.card.action.setText(action_text)
        self.card.action.setVisible(bool(action_text))
        self.card.body.setText(body)
        self.card.link.setVisible(bool(link_text and link_url))
        if link_text and link_url:
            self.card.link.setText(
                f'<a style="color:{theme_color("accent")}" href="{escape(link_url, quote=True)}">'
                f'{escape(link_text)}</a>'
            )
        self.card.back.setVisible(can_go_back)
        self.card.next.setVisible(not wait_for_action)
        self.card.next.setText(next_text)
        self.card.set_important(important)
        # A reaplicação do tema pode recalcular métricas nativas; fixe as
        # dimensões somente depois dela.
        self.card.size_buttons()
        if preserve_card_position and self.card.isVisible():
            self.card._manually_positioned = True
        else:
            self.card.reset_manual_position()
        self.spotlight.start()
        self.card.adjustSize()
        self.card.show()
        self.reposition()
        self.card.raise_()

    def reposition(self):
        self.spotlight.setGeometry(self.host.rect())
        target_rect = QRect()
        if self.target_rect_provider is not None:
            try:
                provided = self.target_rect_provider()
                if provided is not None:
                    target_rect = QRect(provided)
            except (RuntimeError, TypeError):
                target_rect = QRect()
        elif self.target is not None and self.target.isVisible():
            top_left = self.target.mapTo(self.host, QPoint(0, 0))
            target_rect = QRect(top_left, self.target.size()).adjusted(-7, -7, 7, 7)
        self.spotlight.set_target_rect(target_rect if self.highlight_target else QRect())

        if self.card._manually_positioned:
            x = max(8, min(self.card.x(), self.host.width() - self.card.width() - 8))
            y = max(8, min(self.card.y(), self.host.height() - self.card.height() - 8))
            self.card.move(x, y)
            return

        margin = 18
        target_gap = 30
        # O tamanho real inclui os mínimos do cartão; sizeHint() pode ser
        # menor e posicioná-lo sobre o próprio alvo em telas mais apertadas.
        card_size = self.card.size()
        if target_rect.isValid():
            right_x = target_rect.right() + target_gap
            left_x = target_rect.left() - card_size.width() - target_gap
            bottom_y = target_rect.bottom() + target_gap
            top_y = target_rect.top() - card_size.height() - target_gap
            if right_x + card_size.width() <= self.host.width() - margin:
                x, y = right_x, target_rect.center().y() - card_size.height() // 2
            elif left_x >= margin:
                x, y = left_x, target_rect.center().y() - card_size.height() // 2
            elif bottom_y + card_size.height() <= self.host.height() - margin:
                x, y = target_rect.center().x() - card_size.width() // 2, bottom_y
            elif top_y >= margin:
                x, y = target_rect.center().x() - card_size.width() // 2, top_y
            else:
                x, y = target_rect.center().x() - card_size.width() // 2, margin
            x = max(margin, min(x, self.host.width() - card_size.width() - margin))
            y = max(margin, min(y, self.host.height() - card_size.height() - margin))
        else:
            x = max(margin, (self.host.width() - card_size.width()) // 2)
            y = max(margin, (self.host.height() - card_size.height()) // 2)
        self.card.move(x, y)

    def close(self):
        if self.target is not None:
            self.target.removeEventFilter(self)
            self.target = None
        self.target_rect_provider = None
        self.host.removeEventFilter(self)
        self.spotlight.stop()
        self.spotlight.deleteLater()
        self.card.hide()
        self.card.deleteLater()
        self.deleteLater()

    def eventFilter(self, watched, event):
        if event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
            QEvent.Type.Show,
            QEvent.Type.LayoutRequest,
        ):
            QTimer.singleShot(0, self.reposition)
        return False
