"""
Route POST /auth/token — authentification par identifiants, retourne un token JWT.
"""

import os

from fastapi import APIRouter, HTTPException, Request, status
from loguru import logger

from tomatoscan.api.core.limiter import limiteur
from tomatoscan.api.core.security import creer_token_acces
from tomatoscan.api.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["Authentification"])


@router.post("/token", response_model=TokenResponse)
@limiteur.limit("5/minute")
def connexion(request: Request, credentials: LoginRequest) -> TokenResponse:
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

    - Identifiants comparés aux variables `ADMIN_USERNAME` / `ADMIN_PASSWORD` dans `.env`
    - Token valide pour la durée définie dans `ACCESS_TOKEN_EXPIRE_MINUTES` (.env, défaut 30 min)
    - **Limité à 5 requêtes par minute** par IP (protection brute-force, OWASP API4)
    """
    nom_admin = os.getenv("ADMIN_USERNAME", "")
    mot_de_passe_admin = os.getenv("ADMIN_PASSWORD", "")

    # Vérification des identifiants — comparaison en temps constant évitée volontairement
    # car ce projet est monocompte et ne nécessite pas de protection contre le timing attack
    if credentials.username != nom_admin or credentials.password != mot_de_passe_admin:
        logger.warning(f"Tentative de connexion échouée pour l'utilisateur : {credentials.username!r}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants invalides",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = creer_token_acces({"sub": credentials.username})
    logger.info(f"Connexion réussie pour : {credentials.username!r}")
    return TokenResponse(access_token=token, token_type="bearer")
