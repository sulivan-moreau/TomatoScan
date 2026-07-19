# Tests de l'endpoint /health
from tomatoscan.api.main import app


async def test_health_repond_200_avec_le_bon_corps(client):
    """Vérifie que /health retourne un statut 200 et {"status": "ok"}."""
    reponse = await client.get("/health")
    assert reponse.status_code == 200
    assert reponse.json() == {"status": "ok"}


async def test_app_demarre_sans_erreur():
    """Vérifie que l'application démarre et répond correctement (lifespan inclus).

    ASGITransport (utilisé par le fixture `client`) ne déclenche pas le protocole
    ASGI lifespan — on invoque donc directement le lifespan_context de l'app, comme
    le ferait un vrai serveur ASGI (uvicorn) au démarrage, pour vérifier que
    Base.metadata.create_all (run_sync) et bootstrap_admin (async) s'exécutent
    sans erreur avec le moteur async.
    """
    async with app.router.lifespan_context(app):
        pass
