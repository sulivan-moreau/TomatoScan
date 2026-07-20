"""
Rate limiter slowapi — protection contre les attaques par force brute.
Implémente OWASP API4 : Unrestricted Resource Consumption.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Instance partagée du rate limiter — identifie chaque client par son adresse IP
# Cette instance est importée dans main.py (state) et dans les routes décorées
#
# Limite assumée : aucun `storage_uri` n'est fourni, slowapi retombe donc sur son
# backend par défaut "memory://" (slowapi/extension.py). Les compteurs vivent dans
# la mémoire du processus : ils repartent de zéro à chaque redémarrage et ne sont
# partagés ni entre workers uvicorn ni entre réplicas du conteneur. Suffisant pour
# le déploiement mono-worker actuel ; un backend Redis partagé serait nécessaire
# pour une montée en charge multi-réplicas (voir core/owasp.md, section API4).
limiteur = Limiter(key_func=get_remote_address)


def gestionnaire_limite_atteinte(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    """Remplace la réponse texte brut de slowapi par un JSON cohérent avec l'API."""
    return JSONResponse(
        status_code=429,
        content={"detail": "Trop de requêtes — réessayez dans 1 minute."},
    )
