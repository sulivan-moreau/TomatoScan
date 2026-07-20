"""
Schémas Pydantic pour les endpoints /reports — historique d'entraînement et
rapport d'évaluation du modèle MobileNetV2.
"""

from typing import Any

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


class EvaluationResponse(BaseModel):
    """
    Réponse de l'endpoint GET /reports/evaluation — rapport d'évaluation finale
    du modèle sur le jeu de test, tel que produit par model/evaluate.py.
    """

    # Date de génération du rapport d'évaluation (ISO)
    date: str
    # Nom de l'architecture évaluée (ex. MobileNetV2)
    modele: str
    # Epoch du meilleur checkpoint retenu (sur la validation)
    meilleure_epoch: int
    # Meilleure accuracy de validation atteinte
    meilleure_accuracy_validation: float
    # Accuracy mesurée sur le jeu de test (métrique de référence du modèle)
    accuracy_test: float
    # Classes dont le F1-score passe sous le seuil (liste vide si aucune)
    classes_sous_performantes: list[str]
    # Rapport de classification par classe (precision / recall / f1-score / support)
    rapport_classification: dict[str, Any]
