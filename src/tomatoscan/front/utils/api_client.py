"""Client HTTP pour communiquer avec l'API FastAPI de TomatoScan.

Expose :
- ping()           — vérifie que l'API répond (GET /health)
- login()          — authentifie l'utilisateur, retourne le token JWT
- predict()        — envoie une image, retourne le résultat de prédiction
- get_history()    — récupère l'historique des prédictions de l'utilisateur
- is_token_valid() — vérifie localement que le token n'est pas expiré
- fr_label()       — traduit une classe brute du modèle en libellé français

Les erreurs HTTP sont remontées via ApiError, qui porte le code HTTP
(status_code) afin que les pages puissent réagir précisément (401, 400, 503…).
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

# Délais d'attente (en secondes).
TIMEOUT = 10  # requêtes courtes (health, login)
TIMEOUT_PREDICT = 30  # l'inférence CNN peut être plus longue


# --- Correspondance classes du modèle → libellés français -------------------

DISEASE_LABELS = {
    "Tomato_healthy": "Tomate saine",
    "Tomato_Bacterial_spot": "Tache bactérienne",
    "Tomato_Early_blight": "Alternariose précoce",
    "Tomato_Late_blight": "Mildiou",
    "Tomato_Leaf_Mold": "Moisissure des feuilles",
    "Tomato_Septoria_leaf_spot": "Septoriose",
    "Tomato_Spider_mites_Two_spotted_spider_mite": "Acariens (tétranyques)",
    "Tomato__Target_Spot": "Tache cible",
    "Tomato__Tomato_mosaic_virus": "Virus de la mosaïque",
    "Tomato__Tomato_YellowLeaf__Curl_Virus": "Virus de l'enroulement jaune",
}


def fr_label(classe: str) -> str:
    """Renvoie le libellé français d'une classe brute du modèle."""
    if not classe:
        return "Inconnu"
    return DISEASE_LABELS.get(classe, str(classe).replace("_", " "))


# --- Classe d'erreur --------------------------------------------------------


class ApiError(Exception):
    """Erreur métier renvoyée par le client API.

    status_code porte le code HTTP à l'origine de l'erreur (ou None pour
    une erreur réseau), afin que les pages puissent réagir précisément.
    """

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


# --- Outils internes --------------------------------------------------------


def _entetes_auth(token: str) -> dict:
    """Construit l'en-tête d'authentification Bearer."""
    return {"Authorization": f"Bearer {token}"}


def _extraire_detail(reponse, message_defaut: str) -> str:
    """Extrait un message d'erreur lisible depuis la réponse JSON de l'API."""
    try:
        return reponse.json().get("detail", message_defaut)
    except ValueError:
        return message_defaut


# --- Fonctions publiques ----------------------------------------------------


def ping() -> bool:
    """Vérifie que l'API répond (GET /health).

    Retourne True si le service répond avec un code 2xx, False sinon
    (réseau, timeout, erreur HTTP).
    """
    try:
        reponse = requests.get(f"{API_URL}/health", timeout=TIMEOUT)
        return reponse.ok
    except requests.RequestException:
        # Toute erreur réseau / timeout est considérée comme « API injoignable ».
        return False


def login(nom_utilisateur: str, mot_de_passe: str) -> str:
    """Authentifie l'utilisateur via POST /auth/token.

    Envoie les identifiants en JSON et retourne l'access_token JWT si valides.
    Lève ApiError (avec status_code) si les identifiants sont rejetés
    ou si l'API est injoignable.
    """
    try:
        reponse = requests.post(
            f"{API_URL}/auth/token",
            json={"username": nom_utilisateur, "password": mot_de_passe},
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        raise ApiError("Impossible de joindre le serveur. Vérifiez votre connexion.")

    if reponse.status_code == 401:
        raise ApiError(
            "Identifiants invalides. Vérifiez votre nom d'utilisateur et votre mot de passe.",
            status_code=401,
        )
    if not reponse.ok:
        raise ApiError(
            _extraire_detail(reponse, "Échec de la connexion."),
            status_code=reponse.status_code,
        )

    token = reponse.json().get("access_token")
    if not token:
        raise ApiError("Réponse d'authentification invalide (token manquant).")
    return token


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


def predict(octets_image: bytes, nom_fichier: str, token: str) -> dict:
    """Envoie une image à l'API pour analyse et retourne le résultat de prédiction.

    Appelle POST /predict avec le token Bearer et l'image en multipart/form-data.
    Retourne un dict {"classe": ..., "confiance": ..., "message": ...}.
    Lève ApiError (avec status_code) en cas d'erreur HTTP ou réseau.
    """
    # Déduction du type MIME à partir de l'extension du fichier
    extension = (
        str(nom_fichier).lower().rsplit(".", 1)[-1] if "." in str(nom_fichier) else ""
    )
    type_contenu = "image/png" if extension == "png" else "image/jpeg"

    try:
        reponse = requests.post(
            f"{API_URL}/predict",
            headers=_entetes_auth(token),
            # Le champ multipart s'appelle "fichier" côté API FastAPI
            files={"fichier": (nom_fichier, octets_image, type_contenu)},
            timeout=TIMEOUT_PREDICT,
        )
    except requests.RequestException:
        # Erreur réseau : pas de code HTTP disponible
        raise ApiError(
            "Impossible de joindre le serveur pour l'analyse.", status_code=None
        )

    if not reponse.ok:
        detail = _extraire_detail(reponse, f"Erreur {reponse.status_code}.")
        raise ApiError(detail, status_code=reponse.status_code)

    try:
        return reponse.json()
    except ValueError:
        raise ApiError("Réponse de l'API illisible (JSON attendu).")


def get_history(token: str) -> list[dict]:
    """Récupère l'historique des prédictions de l'utilisateur via GET /predictions/history.

    Retourne une liste de dict (id, nom_fichier, classe_predite, confiance, created_at).
    Lève ApiError si l'API retourne une erreur ou est injoignable.
    """
    try:
        reponse = requests.get(
            f"{API_URL}/predictions/history",
            headers=_entetes_auth(token),
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        raise ApiError("Impossible de joindre le serveur pour récupérer l'historique.")

    if not reponse.ok:
        raise ApiError(
            _extraire_detail(reponse, "Impossible de récupérer l'historique."),
            status_code=reponse.status_code,
        )

    try:
        return reponse.json()
    except ValueError:
        raise ApiError("Réponse de l'API illisible (JSON attendu).")
