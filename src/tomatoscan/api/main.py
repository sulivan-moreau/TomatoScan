# Point d'entrée de l'API TomatoScan
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from prometheus_client import make_asgi_app
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from tomatoscan.api.core.limiter import gestionnaire_limite_atteinte, limiteur
from tomatoscan.api.routes.auth import router as auth_router
from tomatoscan.api.routes.health import router as health_router
from tomatoscan.api.routes.history import router as history_router
from tomatoscan.api.routes.predict import router as predict_router
from tomatoscan.api.routes.reports import router as reports_router
from tomatoscan.api.services import model_service
from tomatoscan.database.connexion import Base, moteur

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
    """Cycle de vie de l'application : initialisation BDD et modèle au démarrage."""
    env = os.getenv("APP_ENV", "development")
    logger.info(f"TomatoScan API démarrée — environnement : {env}")
    logger.info("Variables d'environnement chargées depuis .env")
    # Création des tables BDD si elles n'existent pas encore (idempotent)
    Base.metadata.create_all(moteur)
    logger.info("Tables BDD initialisées.")
    # Chargement unique du modèle au démarrage
    model_service.initialiser_modele()
    yield


_DESCRIPTION = """
API de détection de maladies sur les feuilles de tomates par deep learning (MobileNetV2).

## Fonctionnalités

- **Prédiction** : envoie une photo de feuille → reçoit la maladie détectée et le score de confiance
- **Authentification** : JWT Bearer, token obtenu via `/auth/token`
- **Rapports** : historique d'entraînement du modèle (loss / accuracy par epoch)
- **Monitoring** : endpoint `/health` pour les health checks

## Authentification

Toutes les routes sauf `/health` et `/auth/token` requièrent un header :
```
Authorization: Bearer <token>
```
Le token s'obtient via `POST /auth/token` avec les identifiants configurés dans `.env`.
"""

_TAGS_METADATA = [
    {
        "name": "Monitoring",
        "description": "Health check — vérifie que l'API est en ligne. "
        "Aucune authentification requise.",
    },
    {
        "name": "Authentification",
        "description": "Connexion par identifiants (username / password). "
        "Retourne un token JWT Bearer valide pour les endpoints protégés. "
        "Limité à 5 requêtes/minute par IP.",
    },
    {
        "name": "Prédiction",
        "description": "Analyse d'une image de feuille de tomate par MobileNetV2. "
        "Retourne la classe de maladie détectée et le score de confiance. "
        "**JWT Bearer requis.**",
    },
    {
        "name": "Rapports",
        "description": "Historique d'entraînement du modèle MobileNetV2 (loss / accuracy). "
        "Lit un fichier CSV dont le chemin est configuré dans `.env`. "
        "**JWT Bearer requis.**",
    },
]

app = FastAPI(
    title="TomatoScan API",
    description=_DESCRIPTION,
    version="0.1.0",
    lifespan=lifespan,
    contact={
        "name": "Sulivan Moreau",
        "email": "sulivan.moreau@hotmail.fr",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=_TAGS_METADATA,
)

# Rate limiter — l'instance doit être dans app.state pour que SlowAPIMiddleware la trouve
app.state.limiter = limiteur
# Réponse 429 en JSON custom (gestionnaire_limite_atteinte) au lieu du texte brut slowapi
app.add_exception_handler(RateLimitExceeded, gestionnaire_limite_atteinte)

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
app.include_router(history_router)
app.include_router(reports_router)

# Endpoint Prometheus — exposé sur /metrics sans authentification pour le scraping
# make_asgi_app() génère une app WSGI/ASGI standard compatible avec les agents Prometheus
app.mount("/metrics", make_asgi_app())
