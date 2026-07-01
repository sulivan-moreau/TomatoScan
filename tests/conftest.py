# Configuration partagée pour tous les tests — chargée par pytest avant les fichiers de tests.
# Les variables d'environnement doivent être définies AVANT l'import de l'application
# pour que load_dotenv() ne les écrase pas (override=False par défaut).
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "cle_secrete_test_uniquement")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("ADMIN_USERNAME", "admin_test")
os.environ.setdefault("ADMIN_PASSWORD", "motdepasse_test_123")
# SQLite en mémoire pour les tests — évite de nécessiter PostgreSQL
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# Imports APRÈS les variables d'environnement pour que l'app les lise au démarrage
from tomatoscan.api.main import app  # noqa: E402
from tomatoscan.database.connexion import Base, obtenir_session  # noqa: E402

# Moteur SQLite en mémoire avec StaticPool.
# StaticPool force toutes les sessions à partager la même connexion physique :
# les tables créées par create_all() restent visibles pour toutes les sessions de test.
# Sans StaticPool, sqlite:///:memory: crée une nouvelle BDD vide par connexion.
_moteur_test = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(_moteur_test)

_SessionTest = sessionmaker(bind=_moteur_test, autocommit=False, autoflush=False)


def _obtenir_session_test():
    """Session de test injectée via dependency_overrides — partage la même connexion StaticPool."""
    session = _SessionTest()
    try:
        yield session
    finally:
        session.close()


# Override global : toutes les routes utilisant obtenir_session() reçoivent la session de test
app.dependency_overrides[obtenir_session] = _obtenir_session_test


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
