# Tests de l'authentification JWT — endpoint POST /auth/token et protection de /predict
import os

# Identifiants définis dans tests/conftest.py — lus depuis l'environnement
NOM_ADMIN = os.getenv("ADMIN_USERNAME", "admin_test")
MOT_DE_PASSE_ADMIN = os.getenv("ADMIN_PASSWORD", "motdepasse_test_123")


async def _obtenir_token_valide(client) -> str:
    """Effectue une connexion réelle et retourne le token JWT."""
    reponse = await client.post(
        "/auth/token",
        json={"username": NOM_ADMIN, "password": MOT_DE_PASSE_ADMIN},
    )
    return reponse.json()["access_token"]


async def test_login_valide(client):
    """Connexion avec bons identifiants — attend status 200 et un token Bearer."""
    reponse = await client.post(
        "/auth/token",
        json={"username": NOM_ADMIN, "password": MOT_DE_PASSE_ADMIN},
    )
    assert reponse.status_code == 200
    corps = reponse.json()
    assert "access_token" in corps
    assert corps["token_type"] == "bearer"
    assert len(corps["access_token"]) > 10


async def test_login_invalide(client):
    """Connexion avec mauvais mot de passe — attend status 401."""
    reponse = await client.post(
        "/auth/token",
        json={"username": NOM_ADMIN, "password": "mauvais_mot_de_passe"},
    )
    assert reponse.status_code == 401


async def test_predict_sans_token(client):
    """Appel à /predict sans token — attend status 401."""
    reponse = await client.post(
        "/predict",
        files={"fichier": ("photo.jpg", b"\xff\xd8\xff", "image/jpeg")},
    )
    assert reponse.status_code == 401


async def test_predict_token_invalide(client):
    """Appel à /predict avec un token forgé — attend status 401."""
    reponse = await client.post(
        "/predict",
        headers={"Authorization": "Bearer token_bidon_invalide_xyz"},
        files={"fichier": ("photo.jpg", b"\xff\xd8\xff", "image/jpeg")},
    )
    assert reponse.status_code == 401
