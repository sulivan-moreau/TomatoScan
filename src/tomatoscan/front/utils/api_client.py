"""Client HTTP pour communiquer avec l'API FastAPI de TomatoScan.

Expose :
- ping()           — vérifie que l'API répond (GET /health)
- login()          — authentifie l'utilisateur, retourne le token JWT
- me()             — récupère la session validée côté API (GET /auth/me)
- is_token_valid() — vérifie localement que le token n'est pas expiré
- predict()        — envoie une image, retourne le résultat de prédiction
- get_history()    — récupère l'historique des prédictions de l'utilisateur
- list_users()     — liste les comptes utilisateurs (admin uniquement)
- create_user()    — crée un compte agriculteur (admin uniquement)
- delete_user()    — supprime un compte utilisateur (admin uniquement)
- fr_label()       — traduit une classe brute du modèle en libellé français

Les erreurs HTTP sont remontées via ApiError, qui porte le code HTTP
(status_code) afin que les pages puissent réagir précisément (401, 400, 503…).
"""

import logging
import os
import time
from typing import Callable

import jwt
import requests

# loguru n'est pas une dépendance du frontend déployé (Dockerfile.front installe
# requirements.txt, un sous-ensemble volontairement minimal de pyproject.toml —
# voir Dockerfile.front) : on utilise donc le module logging standard ici, pas loguru.
logger = logging.getLogger(__name__)

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
    """Extrait un message d'erreur lisible depuis la réponse JSON de l'API.

    Repli sûr sur message_defaut si le corps n'est pas du JSON valide (ValueError)
    OU si c'est du JSON valide mais pas un objet (ex. une liste ou une chaîne —
    .get() n'existerait pas dessus, d'où le AttributeError explicitement couvert).
    """
    try:
        corps = reponse.json()
    except ValueError:
        return message_defaut
    if not isinstance(corps, dict):
        return message_defaut
    return corps.get("detail", message_defaut)


def _requete_api(
    methode: str,
    chemin: str,
    *,
    token: str | None = None,
    json_corps: dict | None = None,
    fichiers: dict | None = None,
    timeout: int = TIMEOUT,
    message_erreur_reseau: str,
    message_erreur_defaut: str | Callable[[requests.Response], str],
    messages_par_code: dict[int, str] | None = None,
) -> requests.Response:
    """Exécute une requête HTTP vers l'API et centralise la gestion des erreurs
    réseau et des réponses non-2xx — squelette commun à login/predict/
    list_users/create_user/delete_user/get_history (auparavant dupliqué
    identiquement dans chacune). Chaque appelant garde la responsabilité
    d'interpréter le corps de la réponse en cas de succès (2xx) ; seule la
    gestion des erreurs et le timeout sont mutualisés ici.

    messages_par_code permet de substituer un message fixe pour un code HTTP
    précis (ex. 401 sur /auth/token affiche toujours le même message convivial
    plutôt que le detail brut renvoyé par l'API) — comportement préexistant de
    login(), conservé à l'identique par ce paramètre plutôt que supprimé.

    Dispatch explicite vers requests.get/post/delete (plutôt que
    requests.request générique) pour que le point d'entrée réseau reste
    identique à celui d'avant la factorisation — tests/test_frontend/
    test_api_client.py patche "tomatoscan.front.utils.api_client.requests.post"
    directement, ce patch doit continuer à intercepter les appels.
    """
    fonctions_par_methode = {
        "GET": requests.get,
        "POST": requests.post,
        "DELETE": requests.delete,
    }
    appel_requests = fonctions_par_methode[methode]
    entetes = _entetes_auth(token) if token else None
    try:
        reponse = appel_requests(
            f"{API_URL}{chemin}",
            headers=entetes,
            json=json_corps,
            files=fichiers,
            timeout=timeout,
        )
    except requests.RequestException:
        raise ApiError(message_erreur_reseau, status_code=None)

    if not reponse.ok:
        if messages_par_code and reponse.status_code in messages_par_code:
            raise ApiError(
                messages_par_code[reponse.status_code],
                status_code=reponse.status_code,
            )
        defaut = (
            message_erreur_defaut(reponse)
            if callable(message_erreur_defaut)
            else message_erreur_defaut
        )
        raise ApiError(
            _extraire_detail(reponse, defaut),
            status_code=reponse.status_code,
        )

    return reponse


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
    reponse = _requete_api(
        "POST",
        "/auth/token",
        json_corps={"username": nom_utilisateur, "password": mot_de_passe},
        message_erreur_reseau="Impossible de joindre le serveur. Vérifiez votre connexion.",
        message_erreur_defaut="Échec de la connexion.",
        messages_par_code={
            401: "Identifiants invalides. Vérifiez votre nom d'utilisateur et votre mot de passe.",
        },
    )

    token = reponse.json().get("access_token")
    if not token:
        raise ApiError("Réponse d'authentification invalide (token manquant).")
    return token


def me(token: str) -> dict:
    """Récupère la session courante validée par l'API via GET /auth/me.

    Retourne un dict contenant au minimum {"username": ..., "role": ...}.
    Lève ApiError si le token est invalide, expiré ou si l'API est injoignable.
    """
    reponse = _requete_api(
        "GET",
        "/auth/me",
        token=token,
        message_erreur_reseau="Impossible de joindre le serveur pour récupérer la session.",
        message_erreur_defaut="Impossible de récupérer la session courante.",
    )

    try:
        return reponse.json()
    except ValueError:
        raise ApiError("Réponse de l'API illisible (JSON attendu).")


def _decoder_payload_token(token: str) -> dict:
    """Décode la payload d'un JWT sans vérifier la signature (la vérification de
    validité se fait côté API, ici on lit juste le contenu pour affichage côté client).

    Décodage délégué à PyJWT plutôt que fait à la main (ancien code : découpage
    manuel + base64) — PyJWT gère correctement l'encodage base64url du JWT
    (RFC 7519) et le padding, sans réinventer cette logique ici.
    """
    return jwt.decode(token, options={"verify_signature": False})


def is_token_valid(token: str | None = None) -> bool:
    """Vérifie si un token JWT est présent et non expiré.

    Retourne False si le token est absent, malformé ou expiré.
    """
    if not token:
        return False
    try:
        date_expiration = _decoder_payload_token(token).get("exp", 0)
        return time.time() < date_expiration
    except Exception:
        # Token malformé → invalide. Loggué pour ne pas masquer silencieusement
        # un échec de décodage réel (jwt.decode lève une exception PyJWT).
        logger.warning("Échec du décodage du token JWT (is_token_valid)", exc_info=True)
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

    reponse = _requete_api(
        "POST",
        "/predict",
        token=token,
        # Le champ multipart s'appelle "fichier" côté API FastAPI
        fichiers={"fichier": (nom_fichier, octets_image, type_contenu)},
        timeout=TIMEOUT_PREDICT,
        message_erreur_reseau="Impossible de joindre le serveur pour l'analyse.",
        message_erreur_defaut=lambda r: f"Erreur {r.status_code}.",
    )

    try:
        return reponse.json()
    except ValueError:
        raise ApiError("Réponse de l'API illisible (JSON attendu).")


def list_users(token: str) -> list[dict]:
    """Récupère la liste des utilisateurs via GET /users (admin uniquement).

    Retourne une liste de dict (id, username, role, created_at).
    Lève ApiError (403 si le compte n'est pas admin) en cas d'erreur HTTP ou réseau.
    """
    reponse = _requete_api(
        "GET",
        "/users",
        token=token,
        message_erreur_reseau="Impossible de joindre le serveur pour récupérer les utilisateurs.",
        message_erreur_defaut="Impossible de récupérer les utilisateurs.",
    )

    try:
        return reponse.json()
    except ValueError:
        raise ApiError("Réponse de l'API illisible (JSON attendu).")


def create_user(nom_utilisateur: str, mot_de_passe: str, token: str) -> dict:
    """Crée un compte agriculteur via POST /users (admin uniquement).

    Lève ApiError (409 si le username est déjà pris) en cas d'erreur HTTP ou réseau.
    """
    reponse = _requete_api(
        "POST",
        "/users",
        token=token,
        json_corps={"username": nom_utilisateur, "password": mot_de_passe},
        message_erreur_reseau="Impossible de joindre le serveur pour créer le compte.",
        message_erreur_defaut="Échec de la création du compte.",
    )

    try:
        return reponse.json()
    except ValueError:
        raise ApiError("Réponse de l'API illisible (JSON attendu).")


def delete_user(user_id: str, token: str) -> None:
    """Supprime un compte utilisateur via DELETE /users/{id} (admin uniquement).

    user_id est une chaîne (UUID côté API depuis la migration des identifiants
    utilisateur) — jamais parsée côté frontend, uniquement interpolée dans l'URL.

    Lève ApiError (400 si auto-suppression, 409 si l'utilisateur a des prédictions)
    en cas d'erreur HTTP ou réseau.
    """
    _requete_api(
        "DELETE",
        f"/users/{user_id}",
        token=token,
        message_erreur_reseau="Impossible de joindre le serveur pour supprimer le compte.",
        message_erreur_defaut="Échec de la suppression du compte.",
    )


def get_history(token: str) -> list[dict]:
    """Récupère l'historique des prédictions de l'utilisateur via GET /predictions/history.

    Retourne une liste de dict (id, nom_fichier, classe_predite, confiance, created_at).
    Lève ApiError si l'API retourne une erreur ou est injoignable.
    """
    reponse = _requete_api(
        "GET",
        "/predictions/history",
        token=token,
        message_erreur_reseau="Impossible de joindre le serveur pour récupérer l'historique.",
        message_erreur_defaut="Impossible de récupérer l'historique.",
    )

    try:
        return reponse.json()
    except ValueError:
        raise ApiError("Réponse de l'API illisible (JSON attendu).")
