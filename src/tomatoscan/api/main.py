# Point d'entrée de l'API TomatoScan
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from prometheus_client import make_asgi_app
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIASGIMiddleware
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from tomatoscan.api.core.limiter import gestionnaire_limite_atteinte, limiteur
from tomatoscan.api.routes.auth import router as auth_router
from tomatoscan.api.routes.health import router as health_router
from tomatoscan.api.routes.history import router as history_router
from tomatoscan.api.routes.predict import router as predict_router
from tomatoscan.api.routes.reports import router as reports_router
from tomatoscan.api.routes.users import router as users_router
from tomatoscan.api.services import model_service
from tomatoscan.database.bootstrap import bootstrap_admin
from tomatoscan.database.connexion import Base, SessionLocal, moteur

# Chargement des variables d'environnement depuis .env
load_dotenv()


class EnteteSecuriteMiddleware:
    """Ajoute des headers de sécurité HTTP sur chaque réponse (OWASP API8).

    Middleware ASGI pur (scope/receive/send), pas BaseHTTPMiddleware : ce dernier
    exécute la suite de la requête dans une tâche anyio distincte de celle de la
    requête entrante (via son call_next interne), ce qui casse asyncpg dès qu'une
    route en aval ouvre une connexion PostgreSQL — RuntimeError "Future ...
    attached to a different loop" (incompatibilité connue Starlette
    BaseHTTPMiddleware / asyncpg). Le pattern ASGI pur ci-dessous reste dans la
    tâche d'origine : il intercepte le message "http.response.start" envoyé par
    l'application pour y ajouter les headers, sans tâche séparée.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Enveloppe `send` pour injecter les headers avant l'envoi de la réponse."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def envoyer_avec_entetes(message: Message) -> None:
            if message["type"] == "http.response.start":
                entetes = MutableHeaders(scope=message)
                entetes["X-Content-Type-Options"] = "nosniff"
                entetes["X-Frame-Options"] = "DENY"
                entetes["X-XSS-Protection"] = "1; mode=block"
            await send(message)

        await self.app(scope, receive, envoyer_avec_entetes)


def _lire_cors_origins() -> tuple[list[str], bool]:
    """Lit CORS_ORIGINS et retourne le couple (origines autorisées, allow_credentials).

    Garde-fou OWASP API8 (Security Misconfiguration) : la combinaison
    `allow_origins=["*"]` + `allow_credentials=True` est interdite par la spec CORS,
    et Starlette la contourne en renvoyant l'origine de la requête telle quelle avec
    `Access-Control-Allow-Credentials: true` (cors.py, branche
    `allow_all_origins and allow_credentials`) — n'importe quelle origine peut alors
    émettre des requêtes authentifiées par cookie. CORS_ORIGINS absente du `.env`
    suffisait à produire silencieusement cette configuration.

    Comportement selon `APP_ENV` quand aucune origine explicite n'est configurée :
    - environnements de production (tout `APP_ENV` hors des valeurs de
      développement/test ci-dessous) : `RuntimeError` au démarrage, l'API refuse
      de servir une configuration CORS permissive en préproduction ou production ;
    - développement et test/CI : WARNING loguru et repli sur `["*"]` **avec
      `allow_credentials=False`**, seule forme du joker valide au regard de la spec.
      Les environnements de test (`APP_ENV=test`, utilisé par la CI) sont traités
      comme non productifs : ils n'ont pas de frontend réel dont il faudrait
      restreindre l'origine.

    Returns:
        Tuple (liste des origines autorisées, valeur à passer à `allow_credentials`).
    """
    valeur = os.getenv("CORS_ORIGINS", "").strip()
    # Supporte plusieurs origines séparées par des virgules : "http://a.com,http://b.com"
    origines = [origine.strip() for origine in valeur.split(",") if origine.strip()]

    if origines and "*" not in origines:
        return origines, True

    # Environnements non productifs : le joker CORS permissif y est toléré car il
    # n'existe pas de frontend réel dont il faudrait restreindre l'origine.
    ENVIRONNEMENTS_NON_PRODUCTION = {
        "development",
        "dev",
        "local",
        "test",
        "testing",
        "ci",
    }
    env = os.getenv("APP_ENV", "development")
    motif = "CORS_ORIGINS absente ou vide" if not origines else "CORS_ORIGINS vaut '*'"
    if env not in ENVIRONNEMENTS_NON_PRODUCTION:
        logger.error(
            f"{motif} avec APP_ENV={env!r} : configuration CORS permissive refusée. "
            "Renseigner CORS_ORIGINS avec les origines explicites du frontend."
        )
        raise RuntimeError(
            f"{motif} : une origine explicite est obligatoire en production "
            "(voir CORS_ORIGINS dans .env.example)."
        )

    logger.warning(
        f"{motif} : repli sur allow_origins=['*'] avec allow_credentials=False "
        f"(toléré en {env}). Renseigner CORS_ORIGINS avant tout déploiement "
        "en production — voir .env.example."
    )
    return ["*"], False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cycle de vie de l'application : initialisation BDD et modèle au démarrage."""
    env = os.getenv("APP_ENV", "development")
    logger.info(f"TomatoScan API démarrée — environnement : {env}")
    logger.info("Variables d'environnement chargées depuis .env")
    # Création des tables BDD si elles n'existent pas encore (idempotent) — run_sync
    # exécute l'appel Base.metadata.create_all (synchrone, API Core) sur la connexion
    # asynchrone, seul moyen standard de mélanger les deux ici.
    async with moteur.begin() as connexion:
        await connexion.run_sync(Base.metadata.create_all)
    logger.info("Tables BDD initialisées.")
    # Garantit qu'un compte admin (role="admin", mot de passe hashé) existe en BDD
    async with SessionLocal() as session:
        await bootstrap_admin(session)
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
        "Limité à 5 requêtes/minute par IP. `/auth/refresh` réémet un token "
        "avant son expiration (JWT Bearer requis, token courant encore valide).",
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
    {
        "name": "Utilisateurs",
        "description": "Gestion des comptes agriculteur (liste, création, suppression). "
        "**Réservé aux administrateurs.**",
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

# Rate limiter — l'instance doit être dans app.state pour que SlowAPIASGIMiddleware la trouve
app.state.limiter = limiteur
# Réponse 429 en JSON custom (gestionnaire_limite_atteinte) au lieu du texte brut slowapi
app.add_exception_handler(RateLimitExceeded, gestionnaire_limite_atteinte)


@app.exception_handler(Exception)
async def gestionnaire_erreur_generique(
    request: Request, exc: Exception
) -> JSONResponse:
    """Filet de sécurité : logue toute exception non prévue (bug réel, pas une
    HTTPException volontaire comme un 401/404/503) avant de renvoyer un 500
    générique — sans ça, un crash inattendu ne laisserait aucune trace dans les
    logs. Starlette ne passe ici que les exceptions sans handler plus spécifique :
    les HTTPException levées volontairement dans les routes gardent leur propre
    code de statut, inchangé.
    """
    logger.error(f"Erreur non gérée sur {request.method} {request.url.path} : {exc}")
    return JSONResponse(
        status_code=500, content={"detail": "Erreur interne du serveur."}
    )


# Middlewares — ajoutés du plus interne au plus externe (dernier ajouté = premier exécuté)
# SlowAPIASGIMiddleware (ASGI pur, fourni par slowapi) plutôt que SlowAPIMiddleware
# (héritait de BaseHTTPMiddleware — même incompatibilité asyncpg "attached to a
# different loop" que EnteteSecuriteMiddleware, corrigée séparément ci-dessous).
# Ajouté et lu de façon identique (app.add_middleware), même gestionnaire d'exception,
# mêmes limites par route (@limiteur.limit(...)) — comportement inchangé.
app.add_middleware(SlowAPIASGIMiddleware)
# _lire_cors_origins() décide aussi de allow_credentials : le joker '*' n'est jamais
# combiné à allow_credentials=True (voir la docstring de la fonction).
_origines_cors, _cors_credentials = _lire_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origines_cors,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Headers de sécurité ajoutés en dernier pour couvrir toutes les réponses
# (OWASP API8 — Security Misconfiguration, voir core/owasp.md)
app.add_middleware(EnteteSecuriteMiddleware)

# Inclusion des routes
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(predict_router)
app.include_router(history_router)
app.include_router(reports_router)
app.include_router(users_router)

# Endpoint Prometheus — exposé sur /metrics sans authentification pour le scraping
# make_asgi_app() génère une app WSGI/ASGI standard compatible avec les agents Prometheus
# Choix assumé et documenté : voir la section "/metrics — endpoint non authentifié"
# de core/owasp.md (aucune donnée personnelle en label, restriction recommandée en prod).
app.mount("/metrics", make_asgi_app())
