# Point d'entrée de l'API TomatoScan
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from tomatoscan.api.routes.health import router as health_router
from tomatoscan.api.routes.predict import router as predict_router
from tomatoscan.api.services import model_service

# Chargement des variables d'environnement depuis .env
load_dotenv()


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

# Middleware CORS — origines configurables via CORS_ORIGINS dans .env
app.add_middleware(
    CORSMiddleware,
    allow_origins=_lire_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclusion des routes
app.include_router(health_router)
app.include_router(predict_router)
