"""Um exemplo público no primeiro uso, sem recriá-lo após exclusão."""
from PySide6.QtCore import QIODevice, QSaveFile

from core.file_transactions import file_lock
from core.fornax_container import save_public_fornax
from core.starter_templates import starter_catalog, model_from_starter


def ensure_initial_library(models_dir):
    marker = models_dir.parent / '.library-initialized'
    with file_lock(models_dir.parent / '.library-init.lock'):
        if marker.exists():
            return False
        created = False
        # Bibliotecas anteriores já pertencem ao usuário. Não inserir exemplos.
        if not any(models_dir.iterdir()):
            template = next((item for item in starter_catalog('model')
                             if item.id == 'personnel'), None)
            if template is None:
                raise ValueError('Modelo inicial ausente do catálogo de exemplos.')
            document, provider = model_from_starter(template)
            document['name'] = template.title
            save_public_fornax(document, models_dir / 'cartao_de_aniversario_de_pessoal.fornax',
                               asset_provider=provider)
            created = True
        record = QSaveFile(str(marker))
        if not record.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(record.errorString())
        if record.write(b'1\n') != 2 or not record.commit():
            raise OSError(record.errorString())
        return created
