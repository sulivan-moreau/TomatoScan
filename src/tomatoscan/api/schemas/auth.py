"""
Schémas Pydantic pour l'authentification JWT.
"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Identifiants envoyés par le client pour obtenir un token."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """Réponse retournée après une authentification réussie."""

    access_token: str
    token_type: str
