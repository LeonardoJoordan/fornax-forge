import unicodedata
import re

def slugify_model_name(name: str) -> str:
    """
    Converte "Cartão Aniversário" -> "cartao_aniversario"
    - remove acentos (normalização unicode)
    - troca espaços/hífens por "_"
    - mantém só [a-z0-9_]
    """
    s = (name or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"[^a-z0-9_]+", "", s)
    return s or "modelo"