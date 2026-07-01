"""Client HTTP pour communiquer avec l'API FastAPI de TomatoScan.

Expose :
- ping()           — vérifie que l'API répond
- login()          — authentifie l'utilisateur, retourne le token JWT
- is_token_valid() — vérifie localement que le token n'est pas expiré
"""

import base64
import json
import os
import time

import requests

# Chargement optionnel d'un fichier .env (sans dépendance obligatoire).
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv absent : on ignore silencieusement.
    pass

# URL de base de l'API, lue depuis l'environnement (jamais en dur).
API_URL = os.getenv("TOMATOSCAN_API_URL", "http://localhost:8000").rstrip("/")

# Délai d'attente (en secondes) pour les requêtes.
TIMEOUT = 10


class ApiError(Exception):
    """Erreur métier renvoyée par le client API (message lisible)."""


def ping() -> bool:
    """Vérifie que l'API répond.

    Appelle GET /health et renvoie True si le service est joignable
    et répond avec un code 2xx, False sinon (réseau, timeout, erreur HTTP).
    """
    try:
        response = requests.get(f"{API_URL}/health", timeout=TIMEOUT)
        return response.ok
    except requests.RequestException:
        # Toute erreur réseau / timeout est considérée comme « API injoignable ».
        return False


def login(nom_utilisateur: str, mot_de_passe: str) -> str:
    """Authentifie l'utilisateur via POST /auth/token.

    Envoie les identifiants en JSON et retourne l'access_token JWT si valides.
    Lève ApiError avec un message lisible si les identifiants sont rejetés
    ou si l'API est injoignable.
    """
    try:
        reponse = requests.post(
            f"{API_URL}/auth/token",
            json={"username": nom_utilisateur, "password": mot_de_passe},
            timeout=TIMEOUT,
        )
        # 401 = identifiants invalides
        if reponse.status_code == 401:
            raise ApiError("Identifiants invalides. Vérifiez votre nom d'utilisateur et votre mot de passe.")
        if not reponse.ok:
            raise ApiError(f"Erreur serveur ({reponse.status_code}). Réessayez plus tard.")
        return reponse.json()["access_token"]
    except ApiError:
        raise
    except requests.RequestException:
        raise ApiError("API injoignable. Vérifiez que le serveur est démarré.")


def is_token_valid(token: str | None = None) -> bool:
    """Vérifie si un token JWT est présent et non expiré.

    Décode la payload du JWT sans vérifier la signature (la vérification
    cryptographique est effectuée côté serveur à chaque appel API protégé).
    Retourne False si le token est absent, malformé ou expiré.
    """
    if not token:
        return False
    try:
        # La payload JWT est la 2e section (index 1), encodée en base64url
        partie_payload = token.split(".")[1]
        # Ajouter le padding manquant pour décoder en base64 standard
        partie_payload += "=" * (4 - len(partie_payload) % 4)
        payload = json.loads(base64.b64decode(partie_payload))
        date_expiration = payload.get("exp", 0)
        return time.time() < date_expiration
    except Exception:
        # Token malformé → invalide
        return False
