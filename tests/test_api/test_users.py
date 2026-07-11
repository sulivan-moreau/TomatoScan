"""Tests des routes GET/POST/DELETE /users — gestion des comptes agriculteur.

Vérifie :
- Un agriculteur reçoit 403 sur toutes les routes /users
- Un admin peut lister, créer et supprimer des utilisateurs
- La création avec un username déjà pris retourne 409
- Un admin ne peut pas se supprimer lui-même (400)
- La suppression est bloquée si l'utilisateur a des prédictions enregistrées (409)
"""

import io
import os
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from tomatoscan.api.main import app

# Chemins de mock — identiques à test_history.py/test_predict.py pour la cohérence
_PREDIRE = "tomatoscan.api.routes.predict.model_service.predire"
_DISPONIBLE = "tomatoscan.api.routes.predict.model_service.modele_disponible"

client = TestClient(app)

NOM_ADMIN = os.getenv("ADMIN_USERNAME", "admin_test")
MOT_DE_PASSE_ADMIN = os.getenv("ADMIN_PASSWORD", "motdepasse_test_123")


def _creer_image_jpg() -> bytes:
    """Crée une image JPEG valide en mémoire pour les tests."""
    image = Image.new("RGB", (100, 100), color=(80, 160, 40))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _token_admin() -> str:
    """Authentifie l'admin de test et retourne un token JWT valide."""
    reponse = client.post(
        "/auth/token", json={"username": NOM_ADMIN, "password": MOT_DE_PASSE_ADMIN}
    )
    assert reponse.status_code == 200, f"Échec d'authentification admin : {reponse.text}"
    return reponse.json()["access_token"]


def _creer_agriculteur(
    token_admin: str, username: str, password: str = "motdepasse_agri_123"
) -> dict:
    """Crée un compte agriculteur via l'API et retourne le corps de la réponse."""
    reponse = client.post(
        "/users",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"username": username, "password": password},
    )
    assert reponse.status_code == 201, f"Échec de création : {reponse.text}"
    return reponse.json()


def _token_agriculteur(username: str, password: str = "motdepasse_agri_123") -> str:
    """Authentifie un compte agriculteur et retourne son token JWT."""
    reponse = client.post("/auth/token", json={"username": username, "password": password})
    assert reponse.status_code == 200, f"Échec d'authentification agriculteur : {reponse.text}"
    return reponse.json()["access_token"]


def test_agriculteur_recoit_403_sur_toutes_les_routes_users():
    """Un compte agriculteur ne doit avoir accès à aucune route /users."""
    token_admin = _token_admin()
    _creer_agriculteur(token_admin, "agriculteur_403")
    token_agri = _token_agriculteur("agriculteur_403")
    entetes = {"Authorization": f"Bearer {token_agri}"}

    assert client.get("/users", headers=entetes).status_code == 403
    reponse_post = client.post(
        "/users", headers=entetes, json={"username": "x", "password": "y"}
    )
    assert reponse_post.status_code == 403
    assert client.delete("/users/1", headers=entetes).status_code == 403


def test_admin_peut_lister_creer_et_supprimer_des_utilisateurs():
    """Cycle complet admin : création, présence dans la liste, suppression."""
    token_admin = _token_admin()
    entetes = {"Authorization": f"Bearer {token_admin}"}

    utilisateur = _creer_agriculteur(token_admin, "agriculteur_cycle_complet")
    assert utilisateur["role"] == "agriculteur"
    assert "hashed_password" not in utilisateur
    assert "password" not in utilisateur

    reponse_liste = client.get("/users", headers=entetes)
    assert reponse_liste.status_code == 200
    usernames = [u["username"] for u in reponse_liste.json()]
    assert "agriculteur_cycle_complet" in usernames

    reponse_suppression = client.delete(f"/users/{utilisateur['id']}", headers=entetes)
    assert reponse_suppression.status_code == 204

    # L'utilisateur supprimé ne doit plus apparaître dans la liste
    usernames_apres = [u["username"] for u in client.get("/users", headers=entetes).json()]
    assert "agriculteur_cycle_complet" not in usernames_apres


def test_creation_avec_username_deja_pris_retourne_409():
    """Créer deux comptes avec le même username doit échouer sur le second."""
    token_admin = _token_admin()
    _creer_agriculteur(token_admin, "agriculteur_doublon")

    reponse = client.post(
        "/users",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"username": "agriculteur_doublon", "password": "autre_mdp"},
    )
    assert reponse.status_code == 409


def test_admin_ne_peut_pas_se_supprimer_lui_meme():
    """DELETE /users/{id} sur son propre compte admin doit retourner 400."""
    token_admin = _token_admin()
    entetes = {"Authorization": f"Bearer {token_admin}"}

    mon_id = next(
        u["id"] for u in client.get("/users", headers=entetes).json() if u["username"] == NOM_ADMIN
    )

    reponse = client.delete(f"/users/{mon_id}", headers=entetes)
    assert reponse.status_code == 400


@patch(_PREDIRE, return_value=("Tomato_healthy", 0.99))
@patch(_DISPONIBLE, return_value=True)
def test_suppression_bloquee_si_utilisateur_a_des_predictions(mock_dispo, mock_predire):
    """DELETE /users/{id} doit retourner 409 si l'utilisateur a des prédictions enregistrées,
    et l'utilisateur ne doit pas être supprimé de la base dans ce cas."""
    token_admin = _token_admin()
    utilisateur = _creer_agriculteur(token_admin, "agriculteur_avec_predictions")
    token_agri = _token_agriculteur("agriculteur_avec_predictions")

    # L'agriculteur soumet une prédiction (modèle mocké — aucun checkpoint requis)
    reponse_predict = client.post(
        "/predict",
        headers={"Authorization": f"Bearer {token_agri}"},
        files={"fichier": ("feuille_avant_suppression.jpg", _creer_image_jpg(), "image/jpeg")},
    )
    assert reponse_predict.status_code == 200, reponse_predict.text

    # La suppression doit être refusée tant que des prédictions sont liées à ce compte
    entetes_admin = {"Authorization": f"Bearer {token_admin}"}
    reponse_suppression = client.delete(
        f"/users/{utilisateur['id']}", headers=entetes_admin
    )
    assert reponse_suppression.status_code == 409
    assert "prédiction" in reponse_suppression.json()["detail"].lower()

    # L'utilisateur doit toujours exister en base après la tentative refusée
    usernames = [u["username"] for u in client.get("/users", headers=entetes_admin).json()]
    assert "agriculteur_avec_predictions" in usernames
