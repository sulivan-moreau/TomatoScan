"""Schémas Pydantic pour l'historique des prédictions (Issue #32).

Expose :
- HistoryItem   : représente une prédiction sauvegardée en BDD
- HistoryResponse : liste paginée de HistoryItem (non utilisée directement mais
                    conservée pour une évolution future vers la pagination)
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HistoryItem(BaseModel):
    """Représente une entrée de l'historique des prédictions."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nom_fichier: str
    classe_predite: str
    confiance: float
    created_at: datetime
