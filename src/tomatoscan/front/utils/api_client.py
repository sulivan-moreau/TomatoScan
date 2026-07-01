"""Client HTTP pour communiquer avec l'API FastAPI de TomatoScan.

Passe 1 (structure de base) : seule la fonction `ping()` est exposée
pour vérifier que l'API est joignable. Les appels d'authentification et
de prédiction seront ajoutés dans les passes suivantes.
"""

import os

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


def ping():
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
