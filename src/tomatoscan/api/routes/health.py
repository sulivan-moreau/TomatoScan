# Route de monitoring — vérifie que l'API est en ligne
from fastapi import APIRouter

router = APIRouter(tags=["Monitoring"])


@router.get(
    "/health",
    response_description="Statut de l'API — `ok` si le service répond correctement",
)
def health_check():
    """
    Vérifie que l'API TomatoScan est en ligne et opérationnelle.

    Aucune authentification requise. Utilisé par les load balancers,
    le CI/CD et les outils de monitoring (Prometheus, Uptime Kuma…).

    Retourne `{"status": "ok"}` tant que le service répond.
    """
    return {"status": "ok"}
