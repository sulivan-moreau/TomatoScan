"""
Routes /reports — exposent les rapports du modèle MobileNetV2 :
  - GET /reports             : historique d'entraînement (CSV)
  - GET /reports/evaluation  : rapport d'évaluation finale sur le jeu de test (JSON)
Toutes deux protégées par JWT (Depends(obtenir_utilisateur_courant)).
"""

import csv
import json
import os

from fastapi import APIRouter, Depends, HTTPException
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

# Chemin par défaut du rapport d'évaluation si EVALUATION_PATH n'est pas défini
CHEMIN_EVALUATION_DEFAUT = "docs/rapport_evaluation_20260624_163236.json"


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


@router.get(
    "/reports/evaluation",
    response_model=EvaluationResponse,
    responses={
        401: {"description": "Token invalide, expiré ou absent."},
        404: {
            "description": "Rapport d'évaluation introuvable au chemin configuré (EVALUATION_PATH)."
        },
        500: {"description": "Erreur de lecture ou format JSON invalide."},
    },
)
def obtenir_evaluation(
    _utilisateur: str = Depends(obtenir_utilisateur_courant),
) -> EvaluationResponse:
    """
    Retourne le rapport d'évaluation finale du modèle MobileNetV2 sur le jeu de test.

    **Authentification requise** : `Authorization: Bearer <token>` — obtenu via `POST /auth/token`.

    Lit le fichier JSON défini par `EVALUATION_PATH` dans `.env` (produit par
    `model/evaluate.py`). Contient l'accuracy de test, la meilleure epoch, les
    classes sous-performantes et le rapport de classification par classe.

    **Codes d'erreur** :
    - `401` : token manquant ou expiré
    - `404` : rapport introuvable au chemin configuré dans `EVALUATION_PATH`
    - `500` : erreur de lecture ou format JSON invalide
    """
    chemin_json = os.getenv("EVALUATION_PATH", CHEMIN_EVALUATION_DEFAUT)

    # Vérification de l'existence du fichier avant lecture
    if not os.path.isfile(chemin_json):
        logger.warning(f"Rapport d'évaluation introuvable : {chemin_json}")
        raise HTTPException(
            status_code=404,
            detail=f"Rapport d'évaluation introuvable : {chemin_json}",
        )

    # Lecture et validation du JSON d'évaluation
    try:
        with open(chemin_json, encoding="utf-8") as fichier:
            donnees = json.load(fichier)
        rapport = EvaluationResponse(**donnees)
    except Exception as erreur:
        logger.error(f"Erreur de lecture du rapport {chemin_json} : {erreur}")
        raise HTTPException(
            status_code=500,
            detail="Erreur lors de la lecture du rapport d'évaluation.",
        )

    logger.info(
        f"Rapport d'évaluation lu : {chemin_json}, accuracy_test={rapport.accuracy_test:.4f}"
    )
    return rapport
