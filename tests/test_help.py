"""Ajuda offline: catálogo distribuído, busca e navegação real pela janela."""

import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QSettings, Qt, QUrl
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow

from core.help_catalog import HelpCatalog, HelpTopic, help_catalog, read_catalog
from core.resources import HELP_DIR, PROJECT_ROOT
from core.themes import theme_manager
from features.help.help_dialog import HelpDialog, add_help_action
from scripts.release_tools import selected_files


class HelpCatalogTest(unittest.TestCase):
    def test_catalog_matches_inventory_and_is_packaged(self):
        catalog = help_catalog()
        inventory = (PROJECT_ROOT / "docs/INVENTARIO_AJUDA_EDITOR.md").read_text()
        expected = set(re.findall(r"^- \[[ x]\] ([A-Z]+-\d+) — ", inventory, re.M))
        self.assertEqual(set(catalog.by_id), expected - {"REV-01", "REV-02"})
        self.assertEqual(len(catalog.topics), 402)
        packaged = set(selected_files())
        self.assertIn(HELP_DIR / "pt_BR/catalog.json", packaged)
        entries = json.loads((HELP_DIR / "pt_BR/catalog.json").read_text())["topics"]
        public_entries = [entry for entry in entries if entry.get("status") != "review"]
        self.assertEqual(len(public_entries), 402)
        for entry in public_entries:
            self.assertEqual(entry["status"], "published", entry["id"])
            self.assertTrue(entry.get("file"), entry["id"])
            self.assertIn(f"- [x] {entry['id']} — ", inventory)
        for entry in entries:
            if entry.get("file"):
                self.assertIn(HELP_DIR / "pt_BR" / entry["file"], packaged)
                self.assertTrue(catalog.by_id[entry["id"]].markdown.strip())
        for topic in catalog.topics:
            for identifier in re.findall(r"\]\(help:([^)]+)\)", topic.markdown):
                self.assertIn(identifier, catalog.by_id)

    def test_search_ignores_case_accents_and_accepts_related_terms(self):
        catalog = help_catalog()
        self.assertEqual(catalog.search("MÁSCARA"), catalog.search("mascara"))
        self.assertTrue(any(topic.id == "MAS-09" for topic in catalog.search("cortar foto")))
        self.assertTrue(any(topic.id == "TRA-12" for topic in catalog.search("transparencia")))
        self.assertEqual(catalog.search("Editar máscara")[0].id, "MAS-09")
        self.assertEqual(catalog.search("mascara")[0].category, "editor-12")
        self.assertEqual(catalog.search("texto inexistente xyz987"), ())
        self.assertEqual(len(catalog.search()), 402)

    def test_search_combines_terms_and_category_with_title_priority(self):
        catalog = HelpCatalog({"a": "Objetos", "b": "Máscaras"}, (
            HelpTopic("1", "Fotografia", "b", ("editar máscara",)),
            HelpTopic("2", "Editar máscara", "b"),
            HelpTopic("3", "Outro objeto", "a", markdown="Editar máscara"),
        ))
        self.assertEqual([t.id for t in catalog.search("editar mascara")], ["2", "1", "3"])
        self.assertEqual([t.id for t in catalog.search("editar", "a")], ["3"])
        self.assertEqual(catalog.search("editar xyz"), ())

    def test_markdown_is_loaded_once_and_searches_body(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "mascara.md").write_text("## Exemplo\n**Enquadramento** da imagem.")
            (root / "catalog.json").write_text(json.dumps({
                "version": 1, "categories": [{"id": "a", "title": "Imagens"}],
                "topics": [{"id": "1", "title": "Máscara", "category": "a",
                            "file": "mascara.md"}],
            }))
            catalog = read_catalog(root / "catalog.json")
            with patch.object(Path, "read_text", side_effect=AssertionError("Leitura durante busca")):
                self.assertEqual(catalog.search("enquadramento")[0].id, "1")
                self.assertIn("**Enquadramento**", catalog.by_id["1"].markdown)

    def test_duplicate_ids_unknown_category_and_escaping_article_are_rejected(self):
        with self.assertRaises(ValueError):
            HelpCatalog({"a": "A"}, (HelpTopic("1", "A", "a"), HelpTopic("1", "B", "a")))
        with self.assertRaises(ValueError):
            HelpCatalog({"a": "A"}, (HelpTopic("1", "B", "b"),))
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "catalog.json"
            path.write_text(json.dumps({"version": 1,
                "categories": [{"id": "a", "title": "A"}],
                "topics": [{"id": "1", "title": "A", "category": "a", "file": "../outside.md"}],
            }))
            with self.assertRaises(ValueError):
                read_catalog(path)

    def test_missing_language_falls_back_to_portuguese(self):
        self.assertEqual(help_catalog("en_US").topics, help_catalog("pt_BR").topics)


class HelpDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.parent = QMainWindow()
        def cleanup():
            self.parent.close()
            self.parent.deleteLater()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()
        self.addCleanup(cleanup)

    def dialog(self, **kwargs):
        dialog = HelpDialog(self.parent, **kwargs)
        dialog.show()
        dialog.activateWindow()
        dialog.search.setFocus()
        self.app.processEvents()
        return dialog

    def visible_ids(self, dialog):
        return [dialog.results.topLevelItem(row).child(child).data(0, Qt.ItemDataRole.UserRole)
                for row in range(dialog.results.topLevelItemCount())
                for child in range(dialog.results.topLevelItem(row).childCount())]

    def test_search_selects_item_by_keyboard_and_shows_article(self):
        dialog = self.dialog()
        self.assertEqual(len(self.visible_ids(dialog)), 402)
        self.assertEqual(dialog.results.topLevelItemCount(), 22)
        QTest.keyClicks(dialog.search, "editar mascara")
        self.assertEqual(dialog.article_title.text(), "Editar máscara.")
        self.assertIn("Editar máscara abre um modo temporário", dialog.content.toPlainText())
        self.assertNotIn("Descrição ainda não disponível.", dialog.content.toPlainText())
        self.assertEqual(dialog.article_category.text(), "Máscaras de imagem")
        QTest.keyClick(dialog.search, Qt.Key.Key_Return)
        self.assertTrue(dialog.isVisible())
        self.assertTrue(dialog.results.hasFocus())
        QTest.keyClick(dialog.results, Qt.Key.Key_Down)
        selected_id = dialog.results.currentItem().data(0, Qt.ItemDataRole.UserRole)
        self.assertEqual(dialog.article_title.text(), dialog.catalog.by_id[selected_id].title)

    def test_category_filter_no_results_and_clear_search(self):
        dialog = self.dialog()
        dialog.category_filter.setCurrentIndex(dialog.category_filter.findData("editor-12"))
        self.assertEqual(len(self.visible_ids(dialog)), 16)
        dialog.search.setText("xyz987")
        self.assertEqual(self.visible_ids(dialog), [])
        self.assertEqual(dialog.article_title.text(), "Nenhum tópico encontrado")
        self.assertNotIn("Descrição ainda", dialog.content.toPlainText())
        dialog.search.clear()
        self.assertEqual(len(self.visible_ids(dialog)), 16)
        dialog.category_filter.setCurrentIndex(0)
        self.assertEqual(len(self.visible_ids(dialog)), 402)

    def test_category_name_and_arrow_toggle_once_and_keep_open_article(self):
        dialog = self.dialog()
        tree = dialog.results
        group = tree.topLevelItem(0)

        def click_group(*, arrow=False):
            rectangle = tree.visualItemRect(group)
            position = QPoint(rectangle.left() - tree.indentation() // 2 if arrow
                              else rectangle.left() + 50, rectangle.center().y())
            QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=position)
            self.app.processEvents()

        self.assertFalse(group.isExpanded())
        click_group()
        self.assertTrue(group.isExpanded())
        # Selecionar um artigo ainda abre seu conteúdo normalmente.
        child = group.child(0)
        QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton,
                         pos=tree.visualItemRect(child).center())
        title, article = dialog.article_title.text(), dialog.content.toPlainText()
        self.assertEqual(title, dialog.catalog.by_id["INI-01"].title)
        for arrow in (False, True, True, False):
            before = group.isExpanded()
            click_group(arrow=arrow)
            self.assertEqual(group.isExpanded(), not before)
            self.assertEqual(dialog.article_title.text(), title)
            self.assertEqual(dialog.content.toPlainText(), article)

        dialog.search.setText("Convite institucional")
        group = tree.topLevelItem(0)
        self.assertTrue(group.isExpanded())
        self.assertEqual(dialog.article_title.text(), dialog.catalog.by_id["INI-12"].title)
        click_group()
        self.assertFalse(group.isExpanded())
        self.assertEqual(dialog.article_title.text(), dialog.catalog.by_id["INI-12"].title)

    def test_first_article_renders_and_related_link_opens_existing_topic(self):
        dialog = self.dialog()
        dialog.search.setText("ponto de partida")
        self.assertEqual(self.visible_ids(dialog)[0], "INI-01")
        self.assertIn("Arquivo → Novo modelo", dialog.content.toPlainText())
        self.assertNotIn("Descrição ainda não disponível", dialog.content.toPlainText())
        self.assertIn('href="help:INI-02"', dialog.content.toHtml())
        dialog.content.anchorClicked.emit(QUrl("help:INI-02"))
        self.assertEqual(dialog.article_title.text(), "Começar em branco.")
        self.assertIn("148 × 105 mm", dialog.content.toPlainText())
        self.assertNotIn("Descrição ainda não disponível", dialog.content.toPlainText())

    def test_available_articles_open_with_sections_and_working_links(self):
        dialog = self.dialog()
        headings = ["O que é", "Para que serve", "Como usar", "Exemplo de uso",
                    "Dica de uso", "Particularidades e limites", "Veja também"]
        for topic in dialog.catalog.topics:
            self.assertTrue(topic.markdown.strip(), topic.id)
            identifier = topic.id
            with self.subTest(topic=identifier):
                dialog.open_topic(identifier)
                self.assertEqual(dialog.article_title.text(), dialog.catalog.by_id[identifier].title)
                document = dialog.content.document()
                sections = []
                block = document.begin()
                while block.isValid():
                    if block.blockFormat().headingLevel():
                        sections.append(block.text())
                        # Mede o espaço efetivamente reservado entre o título
                        # e o bloco anterior no layout, além de conferir texto.
                        previous = block.previous()
                        if previous.isValid():
                            layout = document.documentLayout()
                            gap = (layout.blockBoundingRect(block).top()
                                   - layout.blockBoundingRect(previous).bottom())
                            self.assertGreaterEqual(gap, 18)
                    block = block.next()
                self.assertEqual(sections, headings)
                self.assertNotIn("Descrição ainda não disponível", dialog.content.toPlainText())
                self.assertIn('href="help:', dialog.content.toHtml())

    def test_markdown_rendering_and_internal_link_navigation(self):
        catalog = HelpCatalog({"a": "Imagens"}, (
            HelpTopic("1", "Máscara", "a", markdown="## Exemplo\n**Foto**\n\n[Imagem](help:2)"),
            HelpTopic("2", "Imagem variável", "a"),
        ))
        dialog = self.dialog(catalog=catalog)
        dialog.open_topic("1")
        self.assertIn("Exemplo", dialog.content.toPlainText())
        self.assertIn("font-weight", dialog.content.toHtml())
        dialog.content.anchorClicked.emit(QUrl("help:2"))
        self.assertEqual(dialog.article_title.text(), "Imagem variável")
        self.assertEqual(dialog.content.toPlainText(), "Descrição ainda não disponível.")

    def test_menu_order_f1_and_reopen_preserve_search_without_modal_dialog(self):
        menu = self.parent.menuBar().addMenu("Ajuda")
        menu.addAction("Tutorial interativo…")
        action = add_help_action(menu, self.parent)
        self.assertEqual([a.text() for a in menu.actions()],
                         ["Tutorial interativo…", "Central de ajuda…"])
        self.assertEqual(action.shortcut().toString(), "F1")
        self.parent.show()
        action.trigger()
        dialog = self.parent._help_dialog
        self.assertTrue(dialog.isVisible())
        self.assertFalse(dialog.isModal())
        dialog.search.setText("máscara")
        dialog.close()
        self.parent.activateWindow()
        self.app.processEvents()
        QTest.keyClick(self.parent, Qt.Key.Key_F1)
        self.app.processEvents()
        self.assertIs(self.parent._help_dialog, dialog)
        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.search.text(), "máscara")

    def test_both_themes_update_dialog_and_keep_topics(self):
        manager = theme_manager()
        previous = manager.theme_id, manager.current
        self.addCleanup(lambda: manager.select(previous[0], previous[1]))
        dialog = self.dialog()
        dialog.search.setText("máscara")
        styles = []
        for theme in ("dark", "light"):
            manager.select(theme)
            self.app.processEvents()
            styles.append(dialog.styleSheet())
            self.assertIn(manager.color("field"), dialog.styleSheet())
            self.assertTrue(self.visible_ids(dialog))
        self.assertNotEqual(*styles)

    def test_real_workspace_menu_opens_help_below_tutorial(self):
        from features.workspace.main_window import MainWindow
        manager = theme_manager()
        previous = manager.theme_id, manager.current
        self.addCleanup(lambda: manager.select(previous[0], previous[1]))
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.enterContext(patch("core.paths._data_home", return_value=root / "data"))
        settings = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)
        self.enterContext(patch("features.workspace.main_window.get_app_settings", return_value=settings))
        # Métodos de QObject precisam manter funções reais no teste: MagicMock
        # interfere na inspeção de slots do PySide ao conectar os sinais.
        self.enterContext(patch.object(MainWindow, "_ensure_starter_pack", lambda self: None))
        self.enterContext(patch.object(MainWindow, "_reload_models_from_disk", lambda self, **kwargs: None))
        window = MainWindow()
        def cleanup():
            window._preview_refresh_timer.stop()
            window._session_maintenance_timer.stop()
            window._fornax_sessions.close()
            window._external_models_dir.cleanup()
            window.deleteLater()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()
        self.addCleanup(cleanup)
        self.assertEqual(window._tutorial_menu.actions()[0].text(), "Tutorial interativo…")
        self.assertIs(window._tutorial_menu.actions()[1], window._help_action)
        window._help_action.trigger()
        self.assertTrue(window._help_dialog.isVisible())
        window._help_dialog.search.setText("editar mascara")
        self.assertEqual(window._help_dialog.article_title.text(), "Editar máscara.")


if __name__ == "__main__":
    unittest.main()
