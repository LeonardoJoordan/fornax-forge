"""Consulta dos estados de origem e atual de um modelo."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from core.font_utils import is_font_available, system_font_families
from core.i18n import tr
from core.dialog_buttons import style_dialog_button_box
from core.themes import theme_color


def _display_timestamp(value) -> str:
    if not value:
        return tr("Não informado")
    try:
        return datetime.fromisoformat(str(value)).astimezone().strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return str(value)


def _source_label(source: str) -> str:
    return {
        "imported": tr("Importado"),
        "created": tr("Criado neste aplicativo"),
        "legacy": tr("Modelo anterior a este registro"),
        "current": tr("Estado atual"),
    }.get(source, source or tr("Não informado"))


class ModelInfoDialog(QDialog):
    def __init__(self, origin: dict, current: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Informações do modelo"))
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._snapshot_widget(origin), tr("Origem"))
        tabs.addTab(self._snapshot_widget(current), tr("Atual"))
        layout.addWidget(tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        style_dialog_button_box(buttons)
        layout.addWidget(buttons)

    def _snapshot_widget(self, snapshot: dict) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        form = QFormLayout()
        form.addRow(tr("Registro:"), QLabel(_source_label(str(snapshot.get("source", "")))))
        form.addRow(tr("Data:"), QLabel(_display_timestamp(snapshot.get("captured_at"))))
        form.addRow(tr("Nome:"), QLabel(str(snapshot.get("name") or tr("Não informado"))))
        width = snapshot.get("width_mm")
        height = snapshot.get("height_mm")
        dimensions = tr("Não informado")
        if width is not None and height is not None:
            dimensions = f"{float(width):.2f} × {float(height):.2f} mm"
        form.addRow(tr("Dimensões:"), QLabel(dimensions))
        form.addRow(tr("Páginas:"), QLabel(str(snapshot.get("page_count", 0))))
        layout.addLayout(form)

        fonts_tree = QTreeWidget()
        fonts_tree.setHeaderLabels([tr("Página"), tr("Caixa de texto"), tr("Fontes")])
        fonts_tree.setRootIsDecorated(False)
        available = system_font_families()
        danger = QColor(theme_color("danger"))
        for entry in snapshot.get("text_boxes", []):
            fonts = entry.get("fonts", [])
            display = []
            has_missing = False
            for family in fonts:
                missing = not is_font_available(family, available)
                display.append(tr("{fonte} (ausente)").format(fonte=family) if missing else family)
                has_missing = has_missing or missing
            item = QTreeWidgetItem([
                str(entry.get("page", "")),
                str(entry.get("name", "")),
                ", ".join(display) if display else tr("Não informada"),
            ])
            if has_missing:
                item.setForeground(2, danger)
            fonts_tree.addTopLevelItem(item)
        fonts_tree.header().setStretchLastSection(True)
        fonts_tree.setMinimumHeight(180)
        layout.addWidget(QLabel(tr("FONTES POR CAIXA DE TEXTO")))
        layout.addWidget(fonts_tree, 1)

        assets = snapshot.get("assets", [])
        assets_tree = QTreeWidget()
        assets_tree.setHeaderLabels([tr("Página"), tr("Asset")])
        assets_tree.setRootIsDecorated(False)
        for entry in assets:
            assets_tree.addTopLevelItem(QTreeWidgetItem([
                str(entry.get("page", "")), str(entry.get("name", "")),
            ]))
        assets_tree.header().setStretchLastSection(True)
        assets_tree.setMinimumHeight(110)
        layout.addWidget(QLabel(tr("ASSETS")))
        layout.addWidget(assets_tree)
        return widget
