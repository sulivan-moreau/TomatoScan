"""
Routes GET /reports — historique d'entraînement, rapport d'évaluation et
matrice de confusion du modèle MobileNetV2. Toutes protégées par JWT
(Depends(obtenir_utilisateur_courant)).
"""

import csv
import glob
import json
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from loguru import logger

from tomatoscan.api.core.security import obtenir_utilisateur_courant
from tomatoscan.api.schemas.reports import (
    EvaluationResponse,
    RapportEpoch,
    RapportResponse,
)

router = APIRouter(tags=["Rapports"])

# Chemin par défaut si REPORTS_PATH n'est pas défini dans .env
CHEMIN_DEFAUT = "models/historique_20260624_161841.csv"

# Dossier où evaluate.py::generer_rapport() écrit les rapports d'évaluation
# (rapport_evaluation_<horodatage>.json) et la matrice de confusion
# (confusion_matrix.png, nom fixe, écrasée à chaque évaluation).
DOSSIER_EVALUATION_DEFAUT = "./docs"


@router.get(
    "/reports",
    response_model=RapportResponse,
    responses={
        401: {"description": "Token invalide, expiré ou absent."},
        404: {
            "description": "Fichier CSV introuvable au chemin configuré (REPORTS_PATH)."
        },
        500: {"description": "Erreur de lecture ou format CSV invalide."},
    },
)
def obtenir_rapport(
    _utilisateur: str = Depends(obtenir_utilisateur_courant),
) -> RapportResponse:
    """
    Retourne l'historique complet d'entraînement du modèle MobileNetV2.

    **Authentification requise** : `Authorization: Bearer <token>` — obtenu via `POST /auth/token`.

    Lit le fichier CSV défini par `REPORTS_PATH` dans `.env`.
    Colonnes attendues : `epoch`, `train_loss`, `train_accuracy`, `val_loss`, `val_accuracy`.

    **Format de réponse** :
    - `fichier` : chemin du CSV lu
    - `nb_epochs` : nombre total d'epochs enregistrées
    - `meilleure_val_accuracy` : meilleure précision de validation atteinte
    - `historique` : liste des métriques par epoch

    **Codes d'erreur** :
    - `401` : token manquant ou expiré
    - `404` : fichier CSV introuvable au chemin configuré dans `REPORTS_PATH`
    - `500` : erreur de lecture ou format CSV invalide
    """
    chemin_csv = os.getenv("REPORTS_PATH", CHEMIN_DEFAUT)

    # Vérification de l'existence du fichier avant lecture
    if not os.path.isfile(chemin_csv):
        logger.warning(f"Fichier de rapport introuvable : {chemin_csv}")
        raise HTTPException(
            status_code=404,
            detail=f"Fichier de rapport introuvable : {chemin_csv}",
        )

    # Lecture du CSV et construction de la liste d'epochs
    historique: list[RapportEpoch] = []
    try:
        with open(chemin_csv, newline="", encoding="utf-8") as fichier:
            lecteur = csv.DictReader(fichier)
            for ligne in lecteur:
                historique.append(
                    RapportEpoch(
                        epoch=int(ligne["epoch"]),
                        train_loss=float(ligne["train_loss"]),
                        train_accuracy=float(ligne["train_accuracy"]),
                        val_loss=float(ligne["val_loss"]),
                        val_accuracy=float(ligne["val_accuracy"]),
                    )
                )
    except Exception as erreur:
        logger.error(f"Erreur de lecture du CSV {chemin_csv} : {erreur}")
        raise HTTPException(
            status_code=500,
            detail="Erreur lors de la lecture du fichier de rapport.",
        )

    # Calcul de la meilleure val_accuracy sur toutes les epochs
    meilleure_val_accuracy = max((e.val_accuracy for e in historique), default=0.0)

    logger.info(
        f"Rapport lu : {len(historique)} epochs, meilleure val_acc={meilleure_val_accuracy:.4f}"
    )

    return RapportResponse(
        fichier=chemin_csv,
        nb_epochs=len(historique),
        meilleure_val_accuracy=meilleure_val_accuracy,
        historique=historique,
    )


def _chemin_dernier_rapport_evaluation() -> str | None:
    """Retourne le chemin du rapport d'évaluation le plus récent (tri sur le
    nom horodaté, rapport_evaluation_<YYYYmmdd_HHMMSS>.json), ou None si
    aucun n'existe. Un nouveau fichier est écrit à chaque évaluation
    (evaluate.py::generer_rapport()) — jamais écrasé, contrairement à la
    matrice de confusion."""
    dossier = os.getenv("EVALUATION_REPORT_DIR", DOSSIER_EVALUATION_DEFAUT)
    fichiers = sorted(glob.glob(os.path.join(dossier, "rapport_evaluation_*.json")))
    return fichiers[-1] if fichiers else None


@router.get(
    "/reports/evaluation",
    response_model=EvaluationResponse,
    responses={
        401: {"description": "Token invalide, expiré ou absent."},
        404: {"description": "Aucun rapport d'évaluation trouvé."},
        500: {"description": "Erreur de lecture ou format JSON invalide."},
    },
)
def obtenir_evaluation(
    _utilisateur: str = Depends(obtenir_utilisateur_courant),
) -> EvaluationResponse:
    """
    Retourne le dernier rapport d'évaluation du modèle sur le jeu de test
    (accuracy test, meilleure accuracy de validation, précision/rappel/F1 par
    classe) — généré par `evaluate.py::generer_rapport()`.

    **Authentification requise** : `Authorization: Bearer <token>`.
    """
    chemin_rapport = _chemin_dernier_rapport_evaluation()
    if chemin_rapport is None:
        logger.warning("Aucun rapport d'évaluation trouvé (EVALUATION_REPORT_DIR).")
        raise HTTPException(
            status_code=404, detail="Aucun rapport d'évaluation trouvé."
        )

    try:
        with open(chemin_rapport, encoding="utf-8") as fichier:
            return EvaluationResponse(**json.load(fichier))
    except Exception as erreur:
        logger.error(
            f"Erreur de lecture du rapport d'évaluation {chemin_rapport} : {erreur}"
        )
        raise HTTPException(
            status_code=500,
            detail="Erreur lors de la lecture du rapport d'évaluation.",
        )


@router.get(
    "/reports/confusion-matrix",
    responses={
        401: {"description": "Token invalide, expiré ou absent."},
        404: {"description": "Matrice de confusion introuvable."},
    },
)
def obtenir_matrice_confusion(
    _utilisateur: str = Depends(obtenir_utilisateur_courant),
) -> FileResponse:
    """
    Retourne l'image PNG de la matrice de confusion normalisée, générée lors
    de la dernière évaluation du modèle (`evaluate.py::afficher_confusion_matrix()`).

    **Authentification requise** : `Authorization: Bearer <token>`.
    """
    dossier = os.getenv("EVALUATION_REPORT_DIR", DOSSIER_EVALUATION_DEFAUT)
    chemin_image = os.path.join(dossier, "confusion_matrix.png")
    if not os.path.isfile(chemin_image):
        logger.warning(f"Matrice de confusion introuvable : {chemin_image}")
        raise HTTPException(status_code=404, detail="Matrice de confusion introuvable.")
    return FileResponse(chemin_image, media_type="image/png")
