"""
Route POST /predict — prend une image, retourne la maladie détectée et le score de confiance.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from loguru import logger

from tomatoscan.api.core.security import obtenir_utilisateur_courant
from tomatoscan.api.schemas.predict import PredictionResponse
from tomatoscan.api.services import model_service

router = APIRouter(tags=["Prédiction"])

# Formats d'image acceptés
FORMATS_ACCEPTES = {"image/jpeg", "image/jpg", "image/png"}
EXTENSIONS_ACCEPTEES = {".jpg", ".jpeg", ".png"}
TAILLE_MAX_OCTETS = 5 * 1024 * 1024  # 5 Mo


@router.post("/predict", response_model=PredictionResponse)
async def predire_maladie(
    fichier: UploadFile = File(...),
    _utilisateur: str = Depends(obtenir_utilisateur_courant),
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
            detail=f"Format non supporté. Formats acceptés : jpg, jpeg, png.",
        )

    # Lecture des bytes et vérification de la taille
    contenu = await fichier.read()

    if len(contenu) > TAILLE_MAX_OCTETS:
        raise HTTPException(
            status_code=400,
            detail=f"Fichier trop volumineux. Taille max : 5 Mo.",
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
    except Exception as erreur:
        logger.error(f"Erreur de prédiction : {erreur}")
        raise HTTPException(status_code=503, detail="Erreur lors de la prédiction.")

    # Message lisible selon la classe détectée
    if "healthy" in classe.lower():
        message = "Tomate saine — aucune maladie détectée."
    else:
        nom_maladie = classe.replace("Tomato_", "").replace("Tomato__", "").replace("_", " ")
        message = f"Maladie détectée : {nom_maladie} (confiance : {confiance:.1%})"

    return PredictionResponse(classe=classe, confiance=confiance, message=message)
