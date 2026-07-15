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
# SQLite asynchrone (aiosqlite) en mémoire par défaut — rapide, aucun service externe
# requis pour un `pytest` local. La CI (voir .github/workflows/ci-app.yml) exporte à la
# place un DATABASE_URL pointant sur un vrai service PostgreSQL ; ce setdefault() ne
# l'écrase pas (déjà présent dans l'environnement), donc les tests tournent alors
# réellement contre asyncpg/PostgreSQL, pas contre ce substitut SQLite.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

# Imports APRÈS les variables d'environnement pour que l'app les lise au démarrage
from tomatoscan.api.main import app  # noqa: E402
from tomatoscan.database.bootstrap import bootstrap_admin  # noqa: E402
from tomatoscan.database.connexion import Base, obtenir_session  # noqa: E402

# Moteur de test — construit sur DATABASE_URL (SQLite en local par défaut, PostgreSQL
# réel en CI) plutôt qu'un dialecte figé, pour que le service PostgreSQL de la CI soit
# effectivement utilisé par les tests, et non contourné par un moteur SQLite en dur.
_DATABASE_URL_TEST = os.environ["DATABASE_URL"]

if _DATABASE_URL_TEST.startswith("sqlite"):
    # StaticPool force toutes les sessions à partager la même connexion physique :
    # les tables créées par create_all() restent visibles pour toutes les sessions de
    # test. Sans StaticPool, sqlite:///:memory: crée une nouvelle BDD vide par connexion.
    # check_same_thread=False est un paramètre pysqlite/aiosqlite — n'existe pas côté
    # asyncpg, donc ce branchement reste réservé à SQLite.
    _moteur_test = create_async_engine(
        _DATABASE_URL_TEST,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    # PostgreSQL réel (CI) : connexion serveur classique — StaticPool est inutile
    # (le serveur persiste déjà les données entre connexions, contrairement à
    # sqlite:///:memory:) et connect_args ci-dessus n'est pas compris par asyncpg.
    _moteur_test = create_async_engine(_DATABASE_URL_TEST)

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
