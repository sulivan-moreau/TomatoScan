# Tests de l'endpoint /health
from fastapi.testclient import TestClient

from tomatoscan.api.main import app

client = TestClient(app)

def test_health_status_200():
    """Vérifie que /health retourne un statut HTTP 200."""
    reponse = client.get("/health")
    assert reponse.status_code == 200


def test_health_body():
    """Vérifie que /health retourne {"status": "ok"}."""
    reponse = client.get("/health")
    assert reponse.json() == {"status": "ok"}


def test_app_demarre_sans_erreur():
    """Vérifie que l'application démarre et répond correctement (lifespan inclus)."""
    with TestClient(app) as client_lifespan:
        reponse = client_lifespan.get("/health")
        assert reponse.status_code == 200
