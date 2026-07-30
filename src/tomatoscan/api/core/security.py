"""
Gestion de la sécurité JWT : génération et validation des tokens d'accès.
Toutes les clés sont lues depuis les variables d'environnement, jamais en dur.
"""

import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from loguru import logger
from passlib.context import CryptContext

# Schéma Bearer — le bouton "Authorize" de Swagger propose un champ où coller le
# token obtenu via POST /auth/token (le formulaire OAuth2 password envoyait du
# form-urlencoded, incompatible avec le corps JSON attendu par cette route).
# auto_error=False : l'absence de header est gérée dans _decoder_charge() pour
# répondre 401 comme avant (HTTPBearer répondrait 403 par défaut).
porteur_bearer = HTTPBearer(auto_error=False)

# Contexte de hash des mots de passe — bcrypt, un seul schéma nécessaire pour ce projet
_contexte_mot_de_passe = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hacher_mot_de_passe(mot_de_passe: str) -> str:
    """Hash un mot de passe en clair avec bcrypt, pour stockage en BDD."""
    return _contexte_mot_de_passe.hash(mot_de_passe)


def verifier_mot_de_passe(mot_de_passe: str, hash_stocke: str) -> bool:
    """Vérifie un mot de passe en clair contre son hash stocké en BDD.

    Retourne False (plutôt que de lever une exception) si le hash stocké
    est vide ou malformé, pour ne jamais faire planter la route de login.
    """
    if not hash_stocke:
        return False
    try:
        return _contexte_mot_de_passe.verify(mot_de_passe, hash_stocke)
    except ValueError:
        return False


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


def _decoder_charge(
    identifiants: HTTPAuthorizationCredentials | None = Depends(porteur_bearer),
) -> dict:
    """
    Dépendance FastAPI interne : valide le token Bearer et retourne sa charge décodée.

    Partagée par obtenir_utilisateur_courant() et obtenir_role_courant() — FastAPI met
    en cache le résultat d'une dépendance par requête, donc le token n'est décodé
    qu'une seule fois même si une route dépend des deux.

    Raises:
        HTTPException 401 si le token est absent, invalide ou expiré.
    """
    erreur_401 = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Header Authorization absent ou sans schéma Bearer — 401 immédiat
    if identifiants is None:
        raise erreur_401

    cle_secrete = os.getenv("SECRET_KEY", "")
    algorithme = os.getenv("ALGORITHM", "HS256")

    if not cle_secrete:
        logger.error("SECRET_KEY manquante — impossible de valider le token")
        raise erreur_401

    try:
        return jwt.decode(
            identifiants.credentials, cle_secrete, algorithms=[algorithme]
        )
    except JWTError as erreur:
        logger.warning(f"Token JWT invalide : {erreur}")
        raise erreur_401


def obtenir_utilisateur_courant(charge: dict = Depends(_decoder_charge)) -> str:
    """Dépendance FastAPI : retourne le nom d'utilisateur (claim "sub") du token courant."""
    nom_utilisateur: str | None = charge.get("sub")
    if nom_utilisateur is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return nom_utilisateur


def obtenir_role_courant(charge: dict = Depends(_decoder_charge)) -> str:
    """Dépendance FastAPI : retourne le rôle (claim "role") du token courant.

    Rejette explicitement (401) si le claim est absent — un token sans rôle
    n'est pas censé exister (créer_token_acces() l'inclut toujours), donc le
    considérer invalide plutôt que de deviner un rôle par défaut. Un ancien
    comportement supposait silencieusement "agriculteur" dans ce cas : un
    admin avec un token sans rôle (bug ailleurs, token corrompu) se faisait
    alors bloquer sur les routes admin sans explication claire — corrigé ici
    pour que ce cas produise un 401 explicite ("reconnecte-toi") plutôt qu'un
    403 trompeur qui laisse penser que l'accès est normalement refusé.
    """
    role = charge.get("role")
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return role


def verifier_role_admin(role: str = Depends(obtenir_role_courant)) -> None:
    """Dépendance FastAPI : lève 403 si le rôle du token courant n'est pas "admin"."""
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs",
        )
