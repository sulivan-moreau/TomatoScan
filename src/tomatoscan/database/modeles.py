"""
Modèles SQLAlchemy pour TomatoScan.
  - User       : compte utilisateur (admin ou agriculteur)
  - Prediction : historique des prédictions de maladies sur les images
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from tomatoscan.database.connexion import Base


def _maintenant() -> datetime:
    """Retourne l'heure actuelle en UTC — utilisée comme valeur par défaut des colonnes."""
    return datetime.now(timezone.utc)


class User(Base):
    """Compte utilisateur — peut être administrateur ou agriculteur."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    # Rôle attendu : "admin" ou "agriculteur"
    role = Column(String, nullable=False, default="agriculteur")
    created_at = Column(DateTime(timezone=True), default=_maintenant, nullable=False)

    # Relation vers l'historique des prédictions de cet utilisateur
    predictions = relationship("Prediction", back_populates="utilisateur")


class Prediction(Base):
    """Enregistrement d'une prédiction de maladie sur une image de feuille de tomate."""

    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    nom_fichier = Column(String, nullable=False)
    classe_predite = Column(String, nullable=False)
    confiance = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_maintenant, nullable=False)

    # Relation inverse vers l'utilisateur ayant déclenché la prédiction
    utilisateur = relationship("User", back_populates="predictions")
