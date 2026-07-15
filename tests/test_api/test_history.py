"""Tests de l'endpoint GET /predictions/history (Issue #32).

Vérifie :
- Accès sans token → 401
- Accès avec token valide → 200 + liste vide (aucune prédiction initiale)
- Après une prédiction → la prédiction apparaît dans l'historique
"""

import io
import os
from unittest.mock import patch

from PIL import Image

NOM_ADMIN = os.getenv("ADMIN_USERNAME", "admin_test")
MOT_DE_PASSE_ADMIN = os.getenv("ADMIN_PASSWORD", "motdepasse_test_123")

# Chemins de mock — identiques à test_predict.py pour la cohérence
_PREDIRE = "tomatoscan.api.routes.predict.model_service.predire"
_DISPONIBLE = "tomatoscan.api.routes.predict.model_service.modele_disponible"


async def _obtenir_token_valide(client) -> str:
    """Authentifie l'admin de test et retourne un token JWT valide."""
    reponse = await client.post(
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


async def test_history_sans_token(client):
    """GET /predictions/history sans token d'authentification doit retourner 401."""
    reponse = await client.get("/predictions/history")
    assert reponse.status_code == 401


async def test_history_avec_token(client):
    """GET /predictions/history avec un token valide doit retourner 200 et une liste vide."""
    token = await _obtenir_token_valide(client)
    reponse = await client.get(
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
async def test_history_apres_prediction(mock_dispo, mock_predire, client):
    """Vérifie que GET /predictions/history retourne la prédiction sauvegardée après un POST /predict.

    Teste le chemin complet : prédiction → sauvegarde BDD → récupération historique.
    Couvre les lignes de history.py qui interrogent réellement la BDD (utilisateur + requête).
    """
    token = await _obtenir_token_valide(client)

    # Soumission d'une prédiction via POST /predict (modèle mocké — aucun checkpoint requis)
    reponse_predict = await client.post(
        "/predict",
        headers={"Authorization": f"Bearer {token}"},
        files={"fichier": ("feuille_historique.jpg", _creer_image_jpg(), "image/jpeg")},
    )
    assert reponse_predict.status_code == 200

    # Vérification que la prédiction apparaît dans l'historique
    reponse_historique = await client.get(
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


@patch(_PREDIRE, return_value=("Tomato_healthy", 0.99))
@patch(_DISPONIBLE, return_value=True)
async def test_history_filtree_par_role(mock_dispo, mock_predire, client):
    """Un agriculteur ne voit que ses prédictions, un admin voit celles de tous les utilisateurs."""
    token_admin = await _obtenir_token_valide(client)

    # Création d'un compte agriculteur dédié à ce test (via la route admin)
    reponse_creation = await client.post(
        "/users",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={
            "username": "agriculteur_historique",
            "password": "motdepasse_agri_456",
        },
    )
    assert reponse_creation.status_code == 201, reponse_creation.text

    reponse_login_agri = await client.post(
        "/auth/token",
        json={"username": "agriculteur_historique", "password": "motdepasse_agri_456"},
    )
    assert reponse_login_agri.status_code == 200
    token_agri = reponse_login_agri.json()["access_token"]

    # L'agriculteur soumet une prédiction
    reponse_predict = await client.post(
        "/predict",
        headers={"Authorization": f"Bearer {token_agri}"},
        files={"fichier": ("feuille_agri.jpg", _creer_image_jpg(), "image/jpeg")},
    )
    assert reponse_predict.status_code == 200

    # L'agriculteur ne voit que sa propre prédiction (compte flambant neuf)
    reponse_historique_agri = await client.get(
        "/predictions/history", headers={"Authorization": f"Bearer {token_agri}"}
    )
    historique_agri = reponse_historique_agri.json()
    assert len(historique_agri) == 1
    assert historique_agri[0]["nom_fichier"] == "feuille_agri.jpg"

    # L'admin voit l'historique complet, y compris la prédiction de l'agriculteur
    reponse_historique_admin = await client.get(
        "/predictions/history", headers={"Authorization": f"Bearer {token_admin}"}
    )
    historique_admin = reponse_historique_admin.json()
    fichiers_admin = [entree["nom_fichier"] for entree in historique_admin]
    assert "feuille_agri.jpg" in fichiers_admin
