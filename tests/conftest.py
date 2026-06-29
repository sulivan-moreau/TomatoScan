# Configuration partagée pour tous les tests — chargée par pytest avant les fichiers de tests.
# Les variables d'environnement doivent être définies AVANT l'import de l'application
# pour que load_dotenv() ne les écrase pas (override=False par défaut).
import os

import pytest

os.environ.setdefault("SECRET_KEY", "cle_secrete_test_uniquement")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("ADMIN_USERNAME", "admin_test")
os.environ.setdefault("ADMIN_PASSWORD", "motdepasse_test_123")
# SQLite en mémoire pour les tests — évite de nécessiter PostgreSQL
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture(autouse=True)
def reinitialiser_limiteur():
    """Remet à zéro le compteur du rate limiter avant chaque test pour éviter l'accumulation."""
    try:
        from tomatoscan.api.core.limiter import limiteur
        limiteur._storage.reset()
    except Exception:
        # Le module n'est pas encore chargé au premier démarrage — ignoré
        pass
    yield
