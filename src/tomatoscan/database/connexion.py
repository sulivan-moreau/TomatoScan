"""
Connexion à la base de données via SQLAlchemy.
Fournit le moteur, la session factory, la base déclarative et la dépendance FastAPI.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# Chargement des variables d'environnement — idempotent si déjà chargées par main.py
load_dotenv()

# URL de connexion lue depuis .env — jamais écrite en dur
URL_BASE_DE_DONNEES = os.getenv("DATABASE_URL", "")

# Moteur SQLAlchemy — la connexion effective est établie à la première requête
moteur = create_engine(URL_BASE_DE_DONNEES)

# Factory de sessions — une session par requête HTTP, autocommit désactivé
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=moteur)

# Base déclarative partagée par tous les modèles du projet
Base = declarative_base()


def obtenir_session():
    """
    Dépendance FastAPI : ouvre une session BDD, la passe à la route, puis la ferme.

    Utilisation dans une route :
        session: Session = Depends(obtenir_session)
    """
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
