# Point d'entrée de l'API TomatoScan
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from tomatoscan.api.core.limiter import limiteur
from tomatoscan.api.routes.auth import router as auth_router
from tomatoscan.api.routes.health import router as health_router
from tomatoscan.api.routes.predict import router as predict_router
from tomatoscan.api.routes.reports import router as reports_router
from tomatoscan.api.services import model_service

# Chargement des variables d'environnement depuis .env
load_dotenv()


class EnteteSecuriteMiddleware(BaseHTTPMiddleware):
    """Ajoute des headers de sécurité HTTP sur chaque réponse (OWASP API7)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Injecte X-Content-Type-Options, X-Frame-Options et X-XSS-Protection."""
        reponse = await call_next(request)
        reponse.headers["X-Content-Type-Options"] = "nosniff"
        reponse.headers["X-Frame-Options"] = "DENY"
        reponse.headers["X-XSS-Protection"] = "1; mode=block"
        return reponse


def _lire_cors_origins() -> list[str]:
    """Lit CORS_ORIGINS depuis l'environnement et retourne une liste d'origines."""
    valeur = os.getenv("CORS_ORIGINS", "*")
    # Supporte plusieurs origines séparées par des virgules : "http://a.com,http://b.com"
    return [origine.strip() for origine in valeur.split(",")]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cycle de vie de l'application : log au démarrage."""
    env = os.getenv("APP_ENV", "development")
    logger.info(f"TomatoScan API démarrée — environnement : {env}")
    logger.info(f"Variables d'environnement chargées depuis .env")
    # Chargement unique du modèle au démarrage
    model_service.initialiser_modele()
    yield


app = FastAPI(
    title="TomatoScan API",
    description="Détection de maladies sur tomates par CNN (MobileNetV2)",
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limiter — l'instance doit être dans app.state pour que SlowAPIMiddleware la trouve
app.state.limiter = limiteur
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Middlewares — ajoutés du plus interne au plus externe (dernier ajouté = premier exécuté)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_lire_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Headers de sécurité ajoutés en dernier pour couvrir toutes les réponses (OWASP API7)
app.add_middleware(EnteteSecuriteMiddleware)

# Inclusion des routes
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(predict_router)
app.include_router(reports_router)
