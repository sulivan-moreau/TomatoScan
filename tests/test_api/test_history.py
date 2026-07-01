"""Tests de l'endpoint GET /predictions/history (Issue #32).

Vérifie :
- Accès sans token → 401
- Accès avec token valide → 200 + liste vide (aucune prédiction initiale)
- Après une prédiction → la prédiction apparaît dans l'historique
"""

import io
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from tomatoscan.api.main import app

NOM_ADMIN = os.getenv("ADMIN_USERNAME", "admin_test")
MOT_DE_PASSE_ADMIN = os.getenv("ADMIN_PASSWORD", "motdepasse_test_123")

# Chemins de mock — identiques à test_predict.py pour la cohérence
_PREDIRE = "tomatoscan.api.routes.predict.model_service.predire"
_DISPONIBLE = "tomatoscan.api.routes.predict.model_service.modele_disponible"

client = TestClient(app)


def _obtenir_token_valide() -> str:
    """Authentifie l'admin de test et retourne un token JWT valide."""
    reponse = client.post(
        "/auth/token",
        json={"username": NOM_ADMIN, "password": MOT_DE_PASSE_ADMIN},
    )
    assert reponse.status_code == 200, f"Échec d'authentification : {reponse.text}"
    return reponse.json()["access_token"]


def _creer_image_jpg() -> bytes:
    """Crée une image JPEG valide en mémoire pour les tests."""
    image = Image.new("RGB", (100, 100), color=(80, 160, 40))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


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


@patch(_PREDIRE, return_value=("Tomato_healthy", 0.99))
@patch(_DISPONIBLE, return_value=True)
def test_history_apres_prediction(mock_dispo, mock_predire):
    """Vérifie que GET /predictions/history retourne la prédiction sauvegardée après un POST /predict.

    Teste le chemin complet : prédiction → sauvegarde BDD → récupération historique.
    Couvre les lignes de history.py qui interrogent réellement la BDD (utilisateur + requête).
    """
    token = _obtenir_token_valide()

    # Soumission d'une prédiction via POST /predict (modèle mocké — aucun checkpoint requis)
    reponse_predict = client.post(
        "/predict",
        headers={"Authorization": f"Bearer {token}"},
        files={"fichier": ("feuille_historique.jpg", _creer_image_jpg(), "image/jpeg")},
    )
    assert reponse_predict.status_code == 200

    # Vérification que la prédiction apparaît dans l'historique
    reponse_historique = client.get(
        "/predictions/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reponse_historique.status_code == 200
    corps = reponse_historique.json()
    assert isinstance(corps, list)
    assert len(corps) >= 1

    # Vérification des champs de la prédiction la plus récente (tri décroissant)
    derniere = corps[0]
    assert derniere["nom_fichier"] == "feuille_historique.jpg"
    assert derniere["classe_predite"] == "Tomato_healthy"
    assert isinstance(derniere["confiance"], float)
    assert "created_at" in derniere
    assert "id" in derniere
