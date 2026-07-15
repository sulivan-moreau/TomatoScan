"""
Route POST /predict — prend une image, retourne la maladie détectée et le score de confiance.

Après chaque prédiction réussie, l'analyse est sauvegardée en BDD
pour constituer l'historique de l'utilisateur (Issue #32).
"""

import time

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from loguru import logger
from PIL import UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tomatoscan.api.core.security import obtenir_utilisateur_courant
from tomatoscan.api.metrics import (
    errors_total,
    prediction_duration_seconds,
    predictions_total,
)
from tomatoscan.api.schemas.predict import PredictionResponse
from tomatoscan.api.services import model_service
from tomatoscan.database.connexion import obtenir_session
from tomatoscan.database.modeles import Prediction, User

router = APIRouter(tags=["Prédiction"])

# Formats d'image acceptés
FORMATS_ACCEPTES = {"image/jpeg", "image/jpg", "image/png"}
EXTENSIONS_ACCEPTEES = {".jpg", ".jpeg", ".png"}
TAILLE_MAX_OCTETS = 5 * 1024 * 1024  # 5 Mo


async def _obtenir_ou_creer_user(nom_utilisateur: str, session: AsyncSession) -> UUID:
    """Retourne l'id de l'utilisateur en BDD, en créant un enregistrement minimal si absent.

    L'authentification est désormais vérifiée contre la table `users` (mot de
    passe hashé), donc l'utilisateur existe normalement déjà à ce stade. Ce
    filet de sécurité ne joue que pour un cas limite : un compte supprimé par
    un admin alors que son token JWT (encore valide jusqu'à expiration)
    continue d'être utilisé pour une prédiction.
    """
    resultat = await session.execute(select(User).filter_by(username=nom_utilisateur))
    utilisateur = resultat.scalar_one_or_none()
    if utilisateur is None:
        utilisateur = User(
            username=nom_utilisateur,
            email=f"{nom_utilisateur}@tomatoscan.local",
            hashed_password="",
        )
        session.add(utilisateur)
        await session.flush()  # Génère l'id sans committer la transaction
        logger.debug(f"Utilisateur {nom_utilisateur!r} créé en BDD pour l'historique.")
    return utilisateur.id


@router.post(
    "/predict",
    response_model=PredictionResponse,
    responses={
        400: {
            "description": "Format non supporté, fichier trop volumineux (> 5 Mo) ou image corrompue."
        },
        401: {"description": "Token invalide, expiré ou absent."},
        503: {
            "description": "Modèle de prédiction indisponible ou erreur d'inférence."
        },
    },
)
async def predire_maladie(
    fichier: UploadFile = File(...),
    _utilisateur: str = Depends(obtenir_utilisateur_courant),
    session: AsyncSession = Depends(obtenir_session),
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
        errors_total.labels(type_erreur="format_invalide").inc()
        raise HTTPException(
            status_code=400,
            detail="Format non supporté. Formats acceptés : jpg, jpeg, png.",
        )

    # Lecture des bytes et vérification de la taille
    contenu = await fichier.read()

    if len(contenu) > TAILLE_MAX_OCTETS:
        errors_total.labels(type_erreur="fichier_trop_lourd").inc()
        raise HTTPException(
            status_code=400,
            detail="Fichier trop volumineux. Taille max : 5 Mo.",
        )

    # Vérification que le modèle est disponible
    if not model_service.modele_disponible():
        errors_total.labels(type_erreur="modele_indisponible").inc()
        raise HTTPException(
            status_code=503,
            detail="Modèle de prédiction indisponible. Réessayez plus tard.",
        )

    # Prédiction — le timer couvre uniquement l'inférence MobileNetV2
    debut = time.perf_counter()
    try:
        classe, confiance = model_service.predire(contenu)
    except UnidentifiedImageError:
        # PIL ne reconnaît pas le fichier : le contenu est corrompu malgré l'extension correcte
        logger.warning(f"Image corrompue ou format non reconnu : {nom!r}")
        errors_total.labels(type_erreur="image_corrompue").inc()
        raise HTTPException(
            status_code=400, detail="Image corrompue ou format non reconnu."
        )
    except Exception as erreur:
        logger.error(f"Erreur de prédiction : {erreur}")
        errors_total.labels(type_erreur="erreur_prediction").inc()
        raise HTTPException(status_code=503, detail="Erreur lors de la prédiction.")
    finally:
        # Observé même en cas d'erreur pour mesurer les requêtes lentes ou bloquantes
        prediction_duration_seconds.observe(time.perf_counter() - debut)

    # Prédiction réussie : compteur par classe et statut
    predictions_total.labels(classe=classe, statut="succes").inc()

    # Message lisible selon la classe détectée
    if "healthy" in classe.lower():
        message = "Tomate saine — aucune maladie détectée."
    else:
        nom_maladie = (
            classe.replace("Tomato_", "").replace("Tomato__", "").replace("_", " ")
        )
        message = f"Maladie détectée : {nom_maladie} (confiance : {confiance:.1%})"

    # Sauvegarde de la prédiction en BDD (non bloquante si la BDD est indisponible)
    try:
        identifiant_user = await _obtenir_ou_creer_user(_utilisateur, session)
        enregistrement = Prediction(
            user_id=identifiant_user,
            nom_fichier=nom,
            classe_predite=classe,
            confiance=confiance,
        )
        session.add(enregistrement)
        await session.commit()
        logger.info(
            f"Prédiction sauvegardée pour {_utilisateur!r} : {classe} ({confiance:.1%})"
        )
    except Exception as erreur_bdd:
        logger.warning(f"Sauvegarde BDD échouée (non bloquante) : {erreur_bdd}")
        try:
            await session.rollback()
        except Exception:
            pass

    return PredictionResponse(classe=classe, confiance=confiance, message=message)
