# Configuration partagée pour tous les tests — chargée par pytest avant les fichiers de tests.
# Les variables d'environnement doivent être définies AVANT l'import de l'application
# pour que load_dotenv() ne les écrase pas (override=False par défaut).
import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "cle_secrete_test_uniquement")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("ADMIN_USERNAME", "admin_test")
os.environ.setdefault("ADMIN_PASSWORD", "motdepasse_test_123")
# SQLite asynchrone (aiosqlite) en mémoire pour les tests — rapide, aucun service
# externe requis en CI. L'app cible réellement asyncpg/PostgreSQL en développement/
# préprod/prod, mais le moteur async n'a été testé ici que contre SQLite/aiosqlite,
# jamais contre un vrai PostgreSQL dans cet environnement — cette vérification reste
# à faire avant déploiement. Les requêtes SQL de ce projet restent des CRUD simples,
# sans fonctionnalité spécifique à un dialecte.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

# Imports APRÈS les variables d'environnement pour que l'app les lise au démarrage
from tomatoscan.api.main import app  # noqa: E402
from tomatoscan.database.bootstrap import bootstrap_admin  # noqa: E402
from tomatoscan.database.connexion import Base, obtenir_session  # noqa: E402

# Moteur SQLite en mémoire avec StaticPool.
# StaticPool force toutes les sessions à partager la même connexion physique :
# les tables créées par create_all() restent visibles pour toutes les sessions de test.
# Sans StaticPool, sqlite:///:memory: crée une nouvelle BDD vide par connexion.
_moteur_test = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

_SessionTest = async_sessionmaker(
    bind=_moteur_test, autocommit=False, autoflush=False, expire_on_commit=False
)


async def _obtenir_session_test() -> AsyncGenerator[AsyncSession, None]:
    """Session de test injectée via dependency_overrides — partage la même connexion StaticPool."""
    async with _SessionTest() as session:
        yield session


# Override global : toutes les routes utilisant obtenir_session() reçoivent la session de test
app.dependency_overrides[obtenir_session] = _obtenir_session_test


@pytest_asyncio.fixture(autouse=True, scope="session", loop_scope="session")
async def _preparer_bdd_test():
    """Crée les tables et le compte admin une seule fois pour toute la session de tests.

    Remplace l'ancien appel synchrone fait au niveau du module (impossible avec un
    moteur async : create_all()/bootstrap_admin() sont maintenant des coroutines,
    qui doivent tourner dans la boucle asyncio partagée par toute la session — voir
    asyncio_default_fixture_loop_scope="session" dans pyproject.toml — plutôt que
    dans une boucle séparée créée à l'import du module.
    """
    async with _moteur_test.begin() as connexion:
        await connexion.run_sync(Base.metadata.create_all)
    # Le bootstrap admin tourne normalement dans le lifespan de l'app, jamais déclenché
    # par un client de test sans context manager — on le rejoue donc ici directement
    # pour que les tests puissent se logger avec ADMIN_USERNAME/ADMIN_PASSWORD comme
    # en conditions réelles.
    async with _SessionTest() as session:
        await bootstrap_admin(session)
    yield


@pytest_asyncio.fixture(loop_scope="session")
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Client HTTP asynchrone pour appeler l'app FastAPI dans les tests, sans serveur réel.

    Remplace TestClient (synchrone) — ASGITransport pilote directement l'app ASGI
    en mémoire, comme le faisait TestClient, mais avec une API entièrement async/await.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


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
