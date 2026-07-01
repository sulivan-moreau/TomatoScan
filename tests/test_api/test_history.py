"""Tests de l'endpoint GET /predictions/history (Issue #32).

Vérifie :
- Accès sans token → 401
- Accès avec token valide → 200 + liste vide (aucune prédiction initiale)
"""

import os

import pytest
from fastapi.testclient import TestClient

from tomatoscan.api.main import app

NOM_ADMIN = os.getenv("ADMIN_USERNAME", "admin_test")
MOT_DE_PASSE_ADMIN = os.getenv("ADMIN_PASSWORD", "motdepasse_test_123")

client = TestClient(app)


def _obtenir_token_valide() -> str:
    """Authentifie l'admin de test et retourne un token JWT valide."""
    reponse = client.post(
        "/auth/token",
        json={"username": NOM_ADMIN, "password": MOT_DE_PASSE_ADMIN},
    )
    assert reponse.status_code == 200, f"Échec d'authentification : {reponse.text}"
    return reponse.json()["access_token"]


def test_history_sans_token():
    """GET /predictions/history sans token d'authentification doit retourner 401."""
    reponse = client.get("/predictions/history")
    assert reponse.status_code == 401


def test_history_avec_token():
    """GET /predictions/history avec un token valide doit retourner 200 et une liste vide."""
    token = _obtenir_token_valide()
    reponse = client.get(
        "/predictions/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reponse.status_code == 200
    corps = reponse.json()
    assert isinstance(corps, list)
    # Aucune prédiction n'a été soumise — la liste doit être vide
    assert len(corps) == 0
