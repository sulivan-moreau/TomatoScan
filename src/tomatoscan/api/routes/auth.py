"""
Route POST /auth/token — authentification par identifiants, retourne un token JWT.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from sqlalchemy.orm import Session

from tomatoscan.api.core.limiter import limiteur
from tomatoscan.api.core.security import creer_token_acces, verifier_mot_de_passe
from tomatoscan.api.schemas.auth import LoginRequest, TokenResponse
from tomatoscan.database.connexion import obtenir_session
from tomatoscan.database.modeles import User

router = APIRouter(prefix="/auth", tags=["Authentification"])


@router.post(
    "/token",
    response_model=TokenResponse,
    responses={
        401: {
            "description": "Identifiants invalides (nom d'utilisateur ou mot de passe incorrect)."
        },
        429: {
            "description": "Trop de tentatives — limité à 5 requêtes par minute par IP."
        },
    },
)
@limiteur.limit("5/minute")
def connexion(
    request: Request,
    credentials: LoginRequest,
    session: Session = Depends(obtenir_session),
) -> TokenResponse:
    """
    Authentifie un utilisateur et retourne un token JWT Bearer.

    **Exemple de requête** :
    ```json
    { "username": "admin", "password": "mon_mot_de_passe" }
    ```

    **Exemple de réponse** :
    ```json
    { "access_token": "eyJhbGci...", "token_type": "bearer" }
    ```

    Utiliser ensuite le token dans les requêtes protégées :
    ```
    Authorization: Bearer eyJhbGci...
    ```

    - Identifiants vérifiés contre la table `users` (mot de passe hashé bcrypt)
    - Le compte admin est initialisé au démarrage depuis `ADMIN_USERNAME` / `ADMIN_PASSWORD` (`.env`)
    - Le token embarque le rôle (`admin` ou `agriculteur`) de l'utilisateur
    - Token valide pour la durée définie dans `ACCESS_TOKEN_EXPIRE_MINUTES` (.env, défaut 30 min)
    - **Limité à 5 requêtes par minute** par IP (protection brute-force, OWASP API4)
    """
    utilisateur = session.query(User).filter_by(username=credentials.username).first()

    # Vérification des identifiants — comparaison en temps constant évitée volontairement
    # car ce projet est monocompte/multi-agriculteurs et ne nécessite pas de protection
    # contre le timing attack pour cet usage
    if utilisateur is None or not verifier_mot_de_passe(
        credentials.password, utilisateur.hashed_password
    ):
        logger.warning(
            f"Tentative de connexion échouée pour l'utilisateur : {credentials.username!r}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants invalides",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = creer_token_acces({"sub": utilisateur.username, "role": utilisateur.role})
    logger.info(
        f"Connexion réussie pour : {utilisateur.username!r} (rôle : {utilisateur.role})"
    )
    return TokenResponse(access_token=token, token_type="bearer")
