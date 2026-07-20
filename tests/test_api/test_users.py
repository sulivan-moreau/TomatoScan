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
import uuid
from unittest.mock import patch

from PIL import Image

# Chemins de mock — identiques à test_history.py/test_predict.py pour la cohérence
_PREDIRE = "tomatoscan.api.routes.predict.model_service.predire"
_DISPONIBLE = "tomatoscan.api.routes.predict.model_service.modele_disponible"

NOM_ADMIN = os.getenv("ADMIN_USERNAME", "admin_test")
MOT_DE_PASSE_ADMIN = os.getenv("ADMIN_PASSWORD", "motdepasse_test_123")


def _creer_image_jpg() -> bytes:
    """Crée une image JPEG valide en mémoire pour les tests."""
    image = Image.new("RGB", (100, 100), color=(80, 160, 40))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


async def _token_admin(client) -> str:
    """Authentifie l'admin de test et retourne un token JWT valide."""
    reponse = await client.post(
        "/auth/token", json={"username": NOM_ADMIN, "password": MOT_DE_PASSE_ADMIN}
    )
    assert reponse.status_code == 200, (
        f"Échec d'authentification admin : {reponse.text}"
    )
    return reponse.json()["access_token"]


async def _creer_agriculteur(
    client, token_admin: str, username: str, password: str = "motdepasse_agri_123"
) -> dict:
    """Crée un compte agriculteur via l'API et retourne le corps de la réponse."""
    reponse = await client.post(
        "/users",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"username": username, "password": password},
    )
    assert reponse.status_code == 201, f"Échec de création : {reponse.text}"
    return reponse.json()


async def _token_agriculteur(
    client, username: str, password: str = "motdepasse_agri_123"
) -> str:
    """Authentifie un compte agriculteur et retourne son token JWT."""
    reponse = await client.post(
        "/auth/token", json={"username": username, "password": password}
    )
    assert reponse.status_code == 200, (
        f"Échec d'authentification agriculteur : {reponse.text}"
    )
    return reponse.json()["access_token"]


async def test_agriculteur_recoit_403_sur_toutes_les_routes_users(client):
    """Un compte agriculteur ne doit avoir accès à aucune route /users."""
    token_admin = await _token_admin(client)
    # Username unique par exécution (uuid4) : le test reste isolé même contre une base
    # persistante réutilisée d'un run à l'autre (pas de collision « username déjà pris »).
    nom_agri = f"agriculteur_403_{uuid.uuid4().hex[:8]}"
    await _creer_agriculteur(client, token_admin, nom_agri)
    token_agri = await _token_agriculteur(client, nom_agri)
    entetes = {"Authorization": f"Bearer {token_agri}"}

    assert (await client.get("/users", headers=entetes)).status_code == 403
    reponse_post = await client.post(
        "/users", headers=entetes, json={"username": "x", "password": "y"}
    )
    assert reponse_post.status_code == 403
    # UUID syntaxiquement valide mais inexistant : le rôle est vérifié avant toute
    # recherche en BDD, donc peu importe qu'il corresponde à un compte réel.
    reponse_delete = await client.delete(f"/users/{uuid.uuid4()}", headers=entetes)
    assert reponse_delete.status_code == 403


async def test_admin_peut_lister_creer_et_supprimer_des_utilisateurs(client):
    """Cycle complet admin : création, présence dans la liste, suppression."""
    token_admin = await _token_admin(client)
    entetes = {"Authorization": f"Bearer {token_admin}"}

    # Username unique par exécution (uuid4) : évite toute collision si un run
    # précédent s'est interrompu avant la suppression sur une base persistante.
    nom_agri = f"agriculteur_cycle_complet_{uuid.uuid4().hex[:8]}"
    utilisateur = await _creer_agriculteur(client, token_admin, nom_agri)
    assert utilisateur["role"] == "agriculteur"
    assert "hashed_password" not in utilisateur
    assert "password" not in utilisateur

    reponse_liste = await client.get("/users", headers=entetes)
    assert reponse_liste.status_code == 200
    usernames = [u["username"] for u in reponse_liste.json()]
    assert nom_agri in usernames

    reponse_suppression = await client.delete(
        f"/users/{utilisateur['id']}", headers=entetes
    )
    assert reponse_suppression.status_code == 204

    # L'utilisateur supprimé ne doit plus apparaître dans la liste
    reponse_apres = await client.get("/users", headers=entetes)
    usernames_apres = [u["username"] for u in reponse_apres.json()]
    assert nom_agri not in usernames_apres


async def test_creation_avec_username_deja_pris_retourne_409(client):
    """Créer deux comptes avec le même username doit échouer sur le second."""
    token_admin = await _token_admin(client)
    # Username unique par exécution (uuid4) : c'est la SECONDE création avec ce nom
    # qui doit renvoyer 409, pas la première parce qu'un run précédent l'aurait déjà pris.
    nom_double = f"agriculteur_doublon_{uuid.uuid4().hex[:8]}"
    await _creer_agriculteur(client, token_admin, nom_double)

    reponse = await client.post(
        "/users",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"username": nom_double, "password": "autre_mdp"},
    )
    assert reponse.status_code == 409


async def test_creation_avec_mot_de_passe_trop_court_retourne_422(client):
    """Un mot de passe de moins de 8 caractères doit être rejeté par la validation
    Pydantic (UserCreate.password, min_length=8) avant toute écriture en BDD."""
    token_admin = await _token_admin(client)

    reponse = await client.post(
        "/users",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"username": "agriculteur_mdp_court", "password": "abc123"},
    )
    assert reponse.status_code == 422

    # Le compte ne doit pas avoir été créé malgré la tentative
    reponse_liste = await client.get(
        "/users", headers={"Authorization": f"Bearer {token_admin}"}
    )
    usernames = [u["username"] for u in reponse_liste.json()]
    assert "agriculteur_mdp_court" not in usernames


async def test_admin_ne_peut_pas_se_supprimer_lui_meme(client):
    """DELETE /users/{id} sur le compte admin bootstrap doit retourner 400."""
    token_admin = await _token_admin(client)
    entetes = {"Authorization": f"Bearer {token_admin}"}

    reponse_liste = await client.get("/users", headers=entetes)
    mon_id = next(u["id"] for u in reponse_liste.json() if u["username"] == NOM_ADMIN)

    reponse = await client.delete(f"/users/{mon_id}", headers=entetes)
    assert reponse.status_code == 400
    assert "bootstrap" in reponse.json()["detail"].lower()


@patch(_PREDIRE, return_value=("Tomato_healthy", 0.99))
@patch(_DISPONIBLE, return_value=True)
async def test_suppression_bloquee_si_utilisateur_a_des_predictions(
    mock_dispo, mock_predire, client
):
    """DELETE /users/{id} doit retourner 409 si l'utilisateur a des prédictions enregistrées,
    et l'utilisateur ne doit pas être supprimé de la base dans ce cas."""
    token_admin = await _token_admin(client)
    # Username unique par exécution (uuid4) : le compte doit exister pour ce run précis,
    # sans dépendre de l'état laissé par une exécution antérieure sur une base persistante.
    nom_agri = f"agriculteur_avec_predictions_{uuid.uuid4().hex[:8]}"
    utilisateur = await _creer_agriculteur(client, token_admin, nom_agri)
    token_agri = await _token_agriculteur(client, nom_agri)

    # L'agriculteur soumet une prédiction (modèle mocké — aucun checkpoint requis)
    reponse_predict = await client.post(
        "/predict",
        headers={"Authorization": f"Bearer {token_agri}"},
        files={
            "fichier": (
                "feuille_avant_suppression.jpg",
                _creer_image_jpg(),
                "image/jpeg",
            )
        },
    )
    assert reponse_predict.status_code == 200, reponse_predict.text

    # La suppression doit être refusée tant que des prédictions sont liées à ce compte
    entetes_admin = {"Authorization": f"Bearer {token_admin}"}
    reponse_suppression = await client.delete(
        f"/users/{utilisateur['id']}", headers=entetes_admin
    )
    assert reponse_suppression.status_code == 409
    assert "prédiction" in reponse_suppression.json()["detail"].lower()

    # L'utilisateur doit toujours exister en base après la tentative refusée
    reponse_liste = await client.get("/users", headers=entetes_admin)
    usernames = [u["username"] for u in reponse_liste.json()]
    assert nom_agri in usernames
