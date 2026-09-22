from core.themes import themed_style, theme_color, theme_manager
import time
from PySide6.QtWidgets import QLabel, QApplication, QWidget
from PySide6.QtCore import Qt, QTimer, QObject, QEvent, QPoint
from PySide6.QtGui import QCursor

class CustomTooltipManager(QObject):
    _instance = None

    @classmethod
    def install(cls, delay_ms=1500):
        if cls._instance is None:
            cls._instance = cls(delay_ms)
            app = QApplication.instance()
            if app:
                app.installEventFilter(cls._instance)

    def __init__(self, delay_ms=1500):
        super().__init__()
        self.delay_ms = delay_ms
        self.last_hidden_time = 0 
        
        self.tooltip_label = QLabel()
        # Mantemos apenas as flags essenciais para flutuar sobre o editor
        self.tooltip_label.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        # REMOVIDO: WA_TranslucentBackground e X11Bypass (causadores da invisibilidade no Linux)
        self.tooltip_label.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        self.tooltip_label.setTextFormat(Qt.TextFormat.RichText)

        
        # AJUSTE VISUAL: Fundo sólido (sem rgba) para garantir a renderização
        themed_style(self.tooltip_label, """
            QLabel {
                background-color: @panel@; /* Fundo cinza escuro sólido */
                color: @text@;            /* Texto claro e legível */
                border: 1px solid @border_strong@; /* Borda visível */
                border-radius: 4px;        /* Arredondamento menor para evitar cantos pretos no Linux */
                padding: 8px 12px;
                font-family: 'Inter 18pt', sans-serif;
                font-size: 13px;
            }
        """)
        
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(self.delay_ms)
        self.timer.timeout.connect(self.show_tooltip)
        
        self.current_widget = None

    def eventFilter(self, obj, event):
        if not isinstance(obj, QWidget):
            return False

        event_type = event.type()

        if event_type == QEvent.Type.Enter:
            tip = obj.toolTip()
            if tip:
                self.current_widget = obj
                
                # LÓGICA DE VARREDURA CONTÍNUA:
                # Se o último tooltip sumiu há menos de 400ms, mostra este IMEDIATAMENTE
                if (time.time() - self.last_hidden_time) < 0.4:
                    self.timer.stop()
                    self.show_tooltip()
                else:
                    self.timer.start()
        
        elif event_type in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress, QEvent.Type.WindowDeactivate):
            if self.tooltip_label.isVisible():
                self.last_hidden_time = time.time() # Marca o tempo que sumiu
            self.hide_tooltip()
        
        elif event_type == QEvent.Type.ToolTip:
            return True # Bloqueia o tooltip nativo do sistema

        return super().eventFilter(obj, event)

    def show_tooltip(self):
        if not self.current_widget:
            return
            
        text = self.current_widget.toolTip()
        if not text:
            return

        # --- INÍCIO DA MÁGICA ADAPTATIVA ---
        # 1. Tira as amarras da caixa e a quebra de linha para descobrir o tamanho real do texto
        self.tooltip_label.setMinimumWidth(0)
        self.tooltip_label.setMaximumWidth(16777215) # Valor máximo padrão (infinito) do Qt
        self.tooltip_label.setWordWrap(False)
        
        self.tooltip_label.setText(text)
        self.tooltip_label.adjustSize() # A caixa estica tudo em uma única linha

        max_width = 600 # AQUI VOCÊ DEFINE SEU LIMITE MÁXIMO IDEAL (ex: 600px)

        # 2. Se o texto em uma linha for maior que o limite...
        if self.tooltip_label.width() > max_width:
            self.tooltip_label.setWordWrap(True)         # Liga a quebra de texto
            self.tooltip_label.setFixedWidth(max_width)  # Trava a largura no seu limite
            self.tooltip_label.adjustSize()              # Deixa a caixa crescer apenas para baixo
        # --- FIM DA MÁGICA ---
        
        # Posicionamento
        cursor_pos = QCursor.pos()
        screen = QApplication.screenAt(cursor_pos)
        screen_rect = screen.geometry() if screen else None
        
        # Offset de 20px para não ficar colado no cursor
        x = cursor_pos.x() + 20
        y = cursor_pos.y() + 20
        
        # Garante que não sai da tela
        if screen_rect:
            if x + self.tooltip_label.width() > screen_rect.right():
                x = cursor_pos.x() - self.tooltip_label.width() - 10
            if y + self.tooltip_label.height() > screen_rect.bottom():
                y = cursor_pos.y() - self.tooltip_label.height() - 10
                
        self.tooltip_label.move(x, y)
        self.tooltip_label.show()

    def hide_tooltip(self):
        self.timer.stop()
        self.tooltip_label.hide()
        self.current_widget = None
