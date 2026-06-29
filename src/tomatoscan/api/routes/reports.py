"""
Route GET /reports — retourne l'historique d'entraînement MobileNetV2 depuis le CSV.
Protégée par JWT (Depends(obtenir_utilisateur_courant)).
"""

import csv
import os

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from tomatoscan.api.core.security import obtenir_utilisateur_courant
from tomatoscan.api.schemas.reports import RapportEpoch, RapportResponse

router = APIRouter(tags=["Rapports"])

# Chemin par défaut si REPORTS_PATH n'est pas défini dans .env
CHEMIN_DEFAUT = "models/historique_20260624_161841.csv"


@router.get("/reports", response_model=RapportResponse)
def obtenir_rapport(
    _utilisateur: str = Depends(obtenir_utilisateur_courant),
) -> RapportResponse:
    """
    Retourne l'historique d'entraînement MobileNetV2 depuis le fichier CSV.

    - Chemin du CSV configurable via REPORTS_PATH dans .env
    - Retourne les métriques par epoch et la meilleure val_accuracy
    - 404 si le fichier CSV est introuvable
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

    logger.info(f"Rapport lu : {len(historique)} epochs, meilleure val_acc={meilleure_val_accuracy:.4f}")

    return RapportResponse(
        fichier=chemin_csv,
        nb_epochs=len(historique),
        meilleure_val_accuracy=meilleure_val_accuracy,
        historique=historique,
    )
