"""Nome de apresentação; independente dos identificadores de instalação/dados."""

APP_DISPLAY_NAME = "FORNAX Forge"


def application_window_title(context: str) -> str:
    """O nome ao final também evita o sufixo duplicado acrescentado pelo Qt."""
    return f"{context} — {APP_DISPLAY_NAME}"
