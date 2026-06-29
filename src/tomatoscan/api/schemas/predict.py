# Schémas Pydantic pour l'endpoint /predict
from pydantic import BaseModel


class PredictionResponse(BaseModel):
    """Réponse de l'endpoint POST /predict."""

    classe: str
    confiance: float
    message: str
