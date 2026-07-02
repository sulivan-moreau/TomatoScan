"""
Route POST /predict — prend une image, retourne la maladie détectée et le score de confiance.

Après chaque prédiction réussie, l'analyse est sauvegardée en BDD
pour constituer l'historique de l'utilisateur (Issue #32).
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from loguru import logger
from PIL import UnidentifiedImageError
from sqlalchemy.orm import Session

from tomatoscan.api.core.security import obtenir_utilisateur_courant
from tomatoscan.api.schemas.predict import PredictionResponse
from tomatoscan.api.services import model_service
from tomatoscan.database.connexion import obtenir_session
from tomatoscan.database.modeles import Prediction, User

router = APIRouter(tags=["Prédiction"])

# Formats d'image acceptés
FORMATS_ACCEPTES = {"image/jpeg", "image/jpg", "image/png"}
EXTENSIONS_ACCEPTEES = {".jpg", ".jpeg", ".png"}
TAILLE_MAX_OCTETS = 5 * 1024 * 1024  # 5 Mo


def _obtenir_ou_creer_user(nom_utilisateur: str, session: Session) -> int:
    """Retourne l'id de l'utilisateur en BDD, en créant un enregistrement minimal si absent.

    L'authentification étant gérée via .env (pas via la BDD), les utilisateurs
    peuvent ne pas avoir d'entrée dans `users`. On les crée à la volée pour
    pouvoir stocker la clé étrangère user_id sur les prédictions.
    """
    utilisateur = session.query(User).filter_by(username=nom_utilisateur).first()
    if utilisateur is None:
        utilisateur = User(
            username=nom_utilisateur,
            # Email fictif unique — l'auth réelle passe par .env, pas par la BDD
            email=f"{nom_utilisateur}@tomatoscan.local",
            hashed_password="",
        )
        session.add(utilisateur)
        session.flush()  # Génère l'id sans committer la transaction
        logger.debug(f"Utilisateur {nom_utilisateur!r} créé en BDD pour l'historique.")
    return utilisateur.id


@router.post("/predict", response_model=PredictionResponse)
async def predire_maladie(
    fichier: UploadFile = File(...),
    _utilisateur: str = Depends(obtenir_utilisateur_courant),
    session: Session = Depends(obtenir_session),
):
    """
    Analyse une image de feuille de tomate et retourne la maladie détectée par MobileNetV2.

    **Authentification requise** : `Authorization: Bearer <token>` — obtenu via `POST /auth/token`.

    **Formats acceptés** : JPG, JPEG, PNG
    **Taille maximale** : 5 Mo

    **Réponse** :
    - `classe` : nom de la classe prédite (ex. `Tomato_Early_blight`, `Tomato_healthy`)
    - `confiance` : score de confiance entre 0.0 et 1.0
    - `message` : description lisible (ex. `"Maladie détectée : Early blight (confiance : 92.3%)"`)

    **Codes d'erreur** :
    - `400` : format non supporté ou fichier dépassant 5 Mo
    - `401` : token manquant ou expiré
    - `503` : modèle non chargé (vérifier `MODEL_PATH` dans `.env`)
    """
    # Vérification du format via content-type et extension du fichier
    nom = fichier.filename or ""
    extension = "." + nom.rsplit(".", 1)[-1].lower() if "." in nom else ""
    content_type = fichier.content_type or ""

    if content_type not in FORMATS_ACCEPTES and extension not in EXTENSIONS_ACCEPTEES:
        logger.warning(f"Format refusé : {content_type} / {nom}")
        raise HTTPException(
            status_code=400,
            detail="Format non supporté. Formats acceptés : jpg, jpeg, png.",
        )

    # Lecture des bytes et vérification de la taille
    contenu = await fichier.read()

    if len(contenu) > TAILLE_MAX_OCTETS:
        raise HTTPException(
            status_code=400,
            detail="Fichier trop volumineux. Taille max : 5 Mo.",
        )

    # Vérification que le modèle est disponible
    if not model_service.modele_disponible():
        raise HTTPException(
            status_code=503,
            detail="Modèle de prédiction indisponible. Réessayez plus tard.",
        )

    # Prédiction
    try:
        classe, confiance = model_service.predire(contenu)
    except UnidentifiedImageError:
        # PIL ne reconnaît pas le fichier : le contenu est corrompu malgré l'extension correcte
        logger.warning(f"Image corrompue ou format non reconnu : {nom!r}")
        raise HTTPException(status_code=400, detail="Image corrompue ou format non reconnu.")
    except Exception as erreur:
        logger.error(f"Erreur de prédiction : {erreur}")
        raise HTTPException(status_code=503, detail="Erreur lors de la prédiction.")

    # Message lisible selon la classe détectée
    if "healthy" in classe.lower():
        message = "Tomate saine — aucune maladie détectée."
    else:
        nom_maladie = classe.replace("Tomato_", "").replace("Tomato__", "").replace("_", " ")
        message = f"Maladie détectée : {nom_maladie} (confiance : {confiance:.1%})"

    # Sauvegarde de la prédiction en BDD (non bloquante si la BDD est indisponible)
    try:
        identifiant_user = _obtenir_ou_creer_user(_utilisateur, session)
        enregistrement = Prediction(
            user_id=identifiant_user,
            nom_fichier=nom,
            classe_predite=classe,
            confiance=confiance,
        )
        session.add(enregistrement)
        session.commit()
        logger.info(f"Prédiction sauvegardée pour {_utilisateur!r} : {classe} ({confiance:.1%})")
    except Exception as erreur_bdd:
        logger.warning(f"Sauvegarde BDD échouée (non bloquante) : {erreur_bdd}")
        try:
            session.rollback()
        except Exception:
            pass

    return PredictionResponse(classe=classe, confiance=confiance, message=message)
