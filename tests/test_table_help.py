"""Ajuda das tabelas: busca, cobertura e navegação pelos artigos reais."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from core.help_catalog import help_catalog
import test_help as existing


class TableHelpTest(unittest.TestCase):
    setUpClass=classmethod(existing.HelpDialogTest.setUpClass.__func__)
    setUp=existing.HelpDialogTest.setUp
    dialog=existing.HelpDialogTest.dialog
    visible_ids=existing.HelpDialogTest.visible_ids

    def test_all_table_articles_are_complete_and_searchable(self):
        catalog=help_catalog()
        ids={f'TBL-{i:02}' for i in range(1,15)}
        self.assertEqual({t.id for t in catalog.search(category='editor-24')},ids)
        for identifier in ids:
            topic=catalog.by_id[identifier]
            for heading in ('O que é','Para que serve','Como usar','Exemplo de uso','Dica de uso','Particularidades e limites','Veja também'):
                self.assertIn('## '+heading,topic.markdown)
        for query,expected in [('boletim escolar','TBL-14'),('mesclar células','TBL-04'),
                               ('overflow tabela','TBL-13'),('Google Planilhas','TBL-10')]:
            self.assertIn(expected,[t.id for t in catalog.search(query)])

    def test_elements_keeps_forms_alias_and_stable_topic(self):
        catalog=help_catalog()
        for query in ('Elementos','Formas'):
            self.assertIn('FOR-01',[t.id for t in catalog.search(query)])
        self.assertEqual(catalog.by_id['FOR-01'].title,'Menu Elementos (antigo Formas).')
        self.assertIn('Tabela',catalog.by_id['FOR-01'].markdown)

    def test_table_example_opens_and_related_links_navigate(self):
        from PySide6.QtCore import QUrl
        dialog=self.dialog();dialog.open_topic('TBL-14')
        self.assertIn('6 linhas × 4 colunas',dialog.content.toPlainText())
        self.assertIn('não executa fórmulas',help_catalog().by_id['TBL-09'].markdown)
        dialog.content.anchorClicked.emit(QUrl('help:TBL-09'))
        self.assertEqual(dialog.article_title.text(),help_catalog().by_id['TBL-09'].title)
        self.assertIn('{nota_portugues}',dialog.content.toPlainText())
        self.assertIn('planilha de dados',dialog.content.toPlainText())


if __name__=='__main__':unittest.main()
