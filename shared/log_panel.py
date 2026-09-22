from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit
from PySide6.QtCore import Qt
from core.diagnostic_logs import append_diagnostic_log, clear_diagnostic_log

class LogPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Log")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(180)
        layout.addWidget(self.text, 1)

    def clear(self):
        self.text.clear()
        try:
            clear_diagnostic_log("app.log")
        except OSError:
            pass

    def append(self, msg: str):
        self.text.append(msg)
        
        try:
            append_diagnostic_log("app.log", msg)
        except OSError:
            pass  # Falha silenciosa para não quebrar a UI se o disco estiver bloqueado/cheio.
