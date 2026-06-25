# Route de monitoring — vérifie que l'API est en ligne
from fastapi import APIRouter

router = APIRouter(tags=["Monitoring"])


@router.get("/health")
def health_check():
    """Retourne le statut de l'API."""
    return {"status": "ok"}
