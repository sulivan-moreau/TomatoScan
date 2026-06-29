"""
Gestion de la sécurité JWT : génération et validation des tokens d'accès.
Toutes les clés sont lues depuis les variables d'environnement, jamais en dur.
"""

import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from loguru import logger

# Schéma OAuth2 — tokenUrl indique l'URL de connexion pour la doc Swagger
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def creer_token_acces(donnees: dict) -> str:
    """
    Génère un token JWT signé avec les paramètres lus depuis l'environnement.

    Args:
        donnees: dict contenant au minimum {"sub": "<username>"}

    Returns:
        Token JWT sous forme de chaîne encodée.
    """
    cle_secrete = os.getenv("SECRET_KEY", "")
    algorithme = os.getenv("ALGORITHM", "HS256")
    duree_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    if not cle_secrete:
        logger.error("SECRET_KEY manquante dans l'environnement — token non généré")
        raise RuntimeError("SECRET_KEY non configurée")

    charge = donnees.copy()
    expiration = datetime.now(timezone.utc) + timedelta(minutes=duree_minutes)
    charge["exp"] = expiration

    return jwt.encode(charge, cle_secrete, algorithm=algorithme)


def obtenir_utilisateur_courant(token: str = Depends(oauth2_scheme)) -> str:
    """
    Dépendance FastAPI : valide le token Bearer et retourne le nom d'utilisateur.

    Raises:
        HTTPException 401 si le token est absent, invalide ou expiré.
    """
    erreur_401 = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )

    cle_secrete = os.getenv("SECRET_KEY", "")
    algorithme = os.getenv("ALGORITHM", "HS256")

    if not cle_secrete:
        logger.error("SECRET_KEY manquante — impossible de valider le token")
        raise erreur_401

    try:
        charge = jwt.decode(token, cle_secrete, algorithms=[algorithme])
        nom_utilisateur: str | None = charge.get("sub")
        if nom_utilisateur is None:
            raise erreur_401
        return nom_utilisateur
    except JWTError as erreur:
        logger.warning(f"Token JWT invalide : {erreur}")
        raise erreur_401
