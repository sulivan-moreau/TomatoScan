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


class EvaluationResponse(BaseModel):
    """Réponse de l'endpoint /reports/evaluation — rapport d'évaluation sur le
    jeu de test, tel que généré par evaluate.py::generer_rapport().

    rapport_classification n'est pas typé plus précisément que dict : il
    contient un mélange hétérogène de clés (un nom de classe → un dict
    precision/recall/f1-score/support, mais aussi "accuracy" → un float brut,
    et "macro avg"/"weighted avg" → un dict) — reflet direct de la sortie de
    sklearn.metrics.classification_report(output_dict=True), pas la peine de
    la re-modéliser ici, le frontend filtre les clés utiles à l'affichage.
    """

    date: str
    modele: str
    meilleure_epoch: int
    meilleure_accuracy_validation: float
    accuracy_test: float
    classes_sous_performantes: list[str]
    rapport_classification: dict
