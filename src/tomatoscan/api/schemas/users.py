"""
Schémas Pydantic pour la gestion des comptes utilisateur (admin uniquement).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    """Identifiants envoyés par un admin pour créer un compte agriculteur."""

    username: str
    password: str


class UserOut(BaseModel):
    """Représentation publique d'un utilisateur — ne contient jamais le mot de passe hashé."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    created_at: datetime
