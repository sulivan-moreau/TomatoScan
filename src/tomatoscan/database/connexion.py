"""
Connexion à la base de données via SQLAlchemy (moteur asynchrone, asyncpg).
Fournit le moteur, la session factory, la base déclarative et la dépendance FastAPI.
"""

import os
from collections.abc import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

# Chargement des variables d'environnement — idempotent si déjà chargées par main.py
load_dotenv()

# URL de connexion lue depuis .env — jamais écrite en dur.
# Schéma attendu : postgresql+asyncpg://... (le pilote asyncpg est asynchrone,
# incompatible avec un DSN "postgresql://" ou "postgresql+psycopg2://" nu).
URL_BASE_DE_DONNEES = os.getenv("DATABASE_URL", "")

# Moteur SQLAlchemy asynchrone — la connexion effective est établie à la première requête
moteur = create_async_engine(URL_BASE_DE_DONNEES)

# Factory de sessions asynchrones — une session par requête HTTP, autocommit désactivé
SessionLocal = async_sessionmaker(
    autocommit=False, autoflush=False, bind=moteur, expire_on_commit=False
)

# Base déclarative partagée par tous les modèles du projet
Base = declarative_base()


async def obtenir_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dépendance FastAPI : ouvre une session BDD asynchrone, la passe à la route,
    puis la ferme.

    Utilisation dans une route :
        session: AsyncSession = Depends(obtenir_session)
    """
    session: AsyncSession = SessionLocal()
    try:
        yield session
    finally:
        await session.close()
