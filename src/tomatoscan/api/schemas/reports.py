"""
Schémas Pydantic pour l'endpoint GET /reports — historique d'entraînement MobileNetV2.
"""

from pydantic import BaseModel


class RapportEpoch(BaseModel):
    """Métriques d'entraînement pour une epoch donnée."""

    epoch: int
    train_loss: float
    train_accuracy: float
    val_loss: float
    val_accuracy: float


class RapportResponse(BaseModel):
    """Réponse complète de l'endpoint /reports."""

    # Chemin du fichier CSV lu
    fichier: str
    # Nombre total d'epochs dans l'historique
    nb_epochs: int
    # Meilleure val_accuracy atteinte sur toutes les epochs
    meilleure_val_accuracy: float
    # Détail ligne par ligne de l'historique d'entraînement
    historique: list[RapportEpoch]
