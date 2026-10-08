"""Catálogo local da ajuda; pesquisa em memória, independente da interface."""

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata

from core.resources import HELP_DIR


def search_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(re.findall(r"\w+", "".join(
        char for char in decomposed if not unicodedata.combining(char))))


@dataclass(frozen=True)
class HelpTopic:
    id: str
    title: str
    category: str
    keywords: tuple[str, ...] = ()
    markdown: str = ""


class HelpCatalog:
    def __init__(self, categories, topics):
        self.categories = dict(categories)
        self.topics = tuple(topics)
        self.by_id = {topic.id: topic for topic in self.topics}
        if len(self.by_id) != len(self.topics):
            raise ValueError("Identificador de ajuda repetido")
        self._search = {}
        for topic in self.topics:
            if topic.category not in self.categories:
                raise ValueError("Categoria de ajuda desconhecida")
            self._search[topic.id] = (
                search_text(topic.title),
                search_text(" ".join(topic.keywords)),
                search_text(self.categories[topic.category]),
                search_text(topic.markdown),
            )

    def search(self, query="", category=None):
        normalized = search_text(query)
        terms = normalized.split()
        ranked = []
        for order, topic in enumerate(self.topics):
            if category and topic.category != category:
                continue
            title, keywords, category_text, body = self._search[topic.id]
            fields = (title, keywords, category_text, body)
            if not all(any(term in field for field in fields) for term in terms):
                continue
            score = sum(30 if term in title else 20 if term in keywords
                        else 5 if term in category_text else 1 for term in terms)
            if normalized and normalized == title:
                score += 100
            elif normalized and normalized in title:
                score += 40
            if normalized and normalized in category_text:
                score += 10
            ranked.append((-score, order, topic))
        return tuple(entry[2] for entry in sorted(ranked, key=lambda entry: entry[:2]))


def read_catalog(path: Path) -> HelpCatalog:
    """Carrega metadados e artigos uma vez; nunca consulta o inventário em execução."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise ValueError("Versão de catálogo de ajuda inválida")
    categories = {}
    for category in data["categories"]:
        if category["id"] in categories:
            raise ValueError("Categoria de ajuda repetida")
        categories[category["id"]] = category["title"]
    topics = []
    all_ids = set()
    for entry in data["topics"]:
        identifier = entry["id"]
        if identifier in all_ids:
            raise ValueError("Identificador de ajuda repetido")
        all_ids.add(identifier)
        if entry.get("status") == "review":
            continue
        markdown = ""
        if entry.get("file"):
            article = (path.parent / entry["file"]).resolve()
            if not article.is_relative_to(path.parent.resolve()) or article.suffix != ".md":
                raise ValueError("Arquivo de ajuda fora do catálogo")
            markdown = article.read_text(encoding="utf-8")
        topics.append(HelpTopic(identifier, entry["title"], entry["category"],
                                tuple(entry.get("keywords", [])), markdown))
    return HelpCatalog(categories, topics)


@lru_cache(maxsize=4)
def help_catalog(locale="pt_BR") -> HelpCatalog:
    # O conteúdo inicial está em português; a interface usa o idioma do aplicativo.
    safe_locale = locale if re.fullmatch(r"[a-z]{2}(?:_[A-Z]{2})?", locale) else "pt_BR"
    path = HELP_DIR / safe_locale / "catalog.json"
    if not path.is_file():
        path = HELP_DIR / "pt_BR" / "catalog.json"
    return read_catalog(path)
