# Tests de l'authentification JWT — endpoints POST /auth/token, POST /auth/refresh
# et protection de /predict
import os
import time
from datetime import datetime, timedelta, timezone

from jose import jwt as jose_jwt

# Identifiants définis dans tests/conftest.py — lus depuis l'environnement
NOM_ADMIN = os.getenv("ADMIN_USERNAME", "admin_test")
MOT_DE_PASSE_ADMIN = os.getenv("ADMIN_PASSWORD", "motdepasse_test_123")


def _token_signe(charge: dict) -> str:
    """Construit un JWT signé avec la SECRET_KEY de test — pour fabriquer des
    tokens expirés/altérés sans passer par creer_token_acces() (qui ne permet
    pas de choisir une expiration passée)."""
    cle_secrete = os.environ["SECRET_KEY"]
    algorithme = os.environ.get("ALGORITHM", "HS256")
    return jose_jwt.encode(charge, cle_secrete, algorithm=algorithme)


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


async def test_session_courante_avec_token(client):
    """GET /auth/me avec un token valide doit retourner l'identité et le rôle validés par le serveur."""
    token = await _obtenir_token_valide(client)
    reponse = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["username"] == NOM_ADMIN
    assert corps["role"] == "admin"


async def test_session_courante_sans_token(client):
    """GET /auth/me sans token doit retourner 401."""
    reponse = await client.get("/auth/me")
    assert reponse.status_code == 401


async def test_predict_sans_token_ou_avec_token_invalide(client):
    """Appel à /predict sans token, ou avec un token forgé — attend 401 dans
    les deux cas."""
    reponse_sans_token = await client.post(
        "/predict",
        files={"fichier": ("photo.jpg", b"\xff\xd8\xff", "image/jpeg")},
    )
    assert reponse_sans_token.status_code == 401

    reponse_token_invalide = await client.post(
        "/predict",
        headers={"Authorization": "Bearer token_bidon_invalide_xyz"},
        files={"fichier": ("photo.jpg", b"\xff\xd8\xff", "image/jpeg")},
    )
    assert reponse_token_invalide.status_code == 401


# --- POST /auth/refresh ------------------------------------------------------


async def test_refresh_token_valide_retourne_un_nouveau_token(client):
    """Un token valide renouvelé via /auth/refresh retourne un nouveau token
    portant les mêmes claims (sub, role) et une expiration plus lointaine."""
    token_initial = await _obtenir_token_valide(client)

    time.sleep(1)  # "exp" a une précision à la seconde — garantit une valeur différente

    reponse = await client.post(
        "/auth/refresh", headers={"Authorization": f"Bearer {token_initial}"}
    )
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["token_type"] == "bearer"
    nouveau_token = corps["access_token"]
    assert nouveau_token != token_initial

    charge_initiale = jose_jwt.get_unverified_claims(token_initial)
    charge_nouvelle = jose_jwt.get_unverified_claims(nouveau_token)
    assert charge_nouvelle["sub"] == charge_initiale["sub"] == NOM_ADMIN
    assert charge_nouvelle["role"] == charge_initiale["role"] == "admin"
    assert charge_nouvelle["exp"] > charge_initiale["exp"]


async def test_refresh_sans_token(client):
    """POST /auth/refresh sans token — attend status 401."""
    reponse = await client.post("/auth/refresh")
    assert reponse.status_code == 401


async def test_refresh_token_expire(client):
    """Un token déjà expiré ne peut pas être renouvelé — attend status 401."""
    token_expire = _token_signe(
        {
            "sub": NOM_ADMIN,
            "role": "admin",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
        }
    )
    reponse = await client.post(
        "/auth/refresh", headers={"Authorization": f"Bearer {token_expire}"}
    )
    assert reponse.status_code == 401
