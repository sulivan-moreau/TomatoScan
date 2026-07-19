"""
Routes d'authentification : POST /auth/token (connexion), GET /auth/me (session
courante) et POST /auth/refresh (renouvellement du token avant expiration).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tomatoscan.api.core.limiter import limiteur
from tomatoscan.api.core.security import (
    creer_token_acces,
    obtenir_role_courant,
    obtenir_utilisateur_courant,
    verifier_mot_de_passe,
)
from tomatoscan.api.schemas.auth import LoginRequest, MeResponse, TokenResponse
from tomatoscan.database.connexion import obtenir_session
from tomatoscan.database.modeles import User

router = APIRouter(prefix="/auth", tags=["Authentification"])

# Compteur d'échecs de connexion consécutifs par nom d'utilisateur — répond à la
# user story "SÉCURITÉ : 5 échecs consécutifs → rate limiting déclenché", distincte
# du rate limiting slowapi par IP ci-dessous : slowapi protège contre un débit élevé
# de requêtes (5/minute), mais une fenêtre glissante par minute n'empêche pas un
# attaquant patient d'espacer ses tentatives pour rester sous ce seuil indéfiniment.
# Ce compteur, lui, ne dépend pas du temps écoulé : il ne se réinitialise que sur
# une connexion réussie, donc 5 échecs consécutifs bloquent le compte quel que soit
# le rythme des tentatives.
_echecs_consecutifs: dict[str, int] = {}
SEUIL_ECHECS_CONSECUTIFS = 5


def reinitialiser_echecs_consecutifs() -> None:
    """Vide le compteur d'échecs consécutifs — utilisé par les tests pour éviter
    toute accumulation entre tests indépendants (miroir de la réinitialisation du
    rate limiter slowapi déjà faite dans tests/conftest.py)."""
    _echecs_consecutifs.clear()


@router.get(
    "/me",
    response_model=MeResponse,
    responses={401: {"description": "Token invalide, expiré ou absent."}},
)
async def session_courante(
    username: str = Depends(obtenir_utilisateur_courant),
    role: str = Depends(obtenir_role_courant),
) -> MeResponse:
    """Retourne la session courante validée par le serveur.

    Ce point de vérité permet au frontend de récupérer l'identité et le rôle
    depuis l'API plutôt que de relire le JWT localement.
    """
    return MeResponse(username=username, role=role)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={401: {"description": "Token invalide, expiré ou absent."}},
)
async def renouveler_token(
    username: str = Depends(obtenir_utilisateur_courant),
    role: str = Depends(obtenir_role_courant),
) -> TokenResponse:
    """Réémet un token JWT avec les mêmes claims (username, rôle) et une expiration fraîche.

    Le token courant doit être valide et non expiré — `obtenir_utilisateur_courant`
    lève 401 sinon, aucun cas particulier à gérer ici. Un seul type de token, pas
    de refresh token séparé ni de nouvelle table : juste une réémission.
    """
    nouveau_token = creer_token_acces({"sub": username, "role": role})
    return TokenResponse(access_token=nouveau_token, token_type="bearer")


@router.post(
    "/token",
    response_model=TokenResponse,
    responses={
        401: {
            "description": "Identifiants invalides (nom d'utilisateur ou mot de passe incorrect)."
        },
        429: {
            "description": "Trop de tentatives — 5 requêtes par minute par IP, "
            "ou 5 échecs consécutifs pour ce compte."
        },
    },
)
@limiteur.limit("5/minute")
async def connexion(
    request: Request,
    credentials: LoginRequest,
    session: AsyncSession = Depends(obtenir_session),
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
    - **Limité à 5 requêtes par minute** par IP (protection brute-force rapide, OWASP API4)
    - **Bloqué après 5 échecs consécutifs** pour un même compte, indépendamment du
      débit (protection contre un attaquant qui espace ses tentatives, OWASP API4)
    """
    if _echecs_consecutifs.get(credentials.username, 0) >= SEUIL_ECHECS_CONSECUTIFS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de tentatives échouées pour ce compte. Réessayez plus tard.",
        )

    resultat = await session.execute(
        select(User).filter_by(username=credentials.username)
    )
    utilisateur = resultat.scalar_one_or_none()

    # Vérification des identifiants — comparaison en temps constant évitée volontairement
    # car ce projet est monocompte/multi-agriculteurs et ne nécessite pas de protection
    # contre le timing attack pour cet usage
    if utilisateur is None or not verifier_mot_de_passe(
        credentials.password, utilisateur.hashed_password
    ):
        _echecs_consecutifs[credentials.username] = (
            _echecs_consecutifs.get(credentials.username, 0) + 1
        )
        logger.warning(
            f"Tentative de connexion échouée pour l'utilisateur : {credentials.username!r} "
            f"({_echecs_consecutifs[credentials.username]}/{SEUIL_ECHECS_CONSECUTIFS})"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants invalides",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Connexion réussie : le compteur d'échecs de ce compte est remis à zéro
    _echecs_consecutifs.pop(credentials.username, None)

    token = creer_token_acces({"sub": utilisateur.username, "role": utilisateur.role})
    logger.info(
        f"Connexion réussie pour : {utilisateur.username!r} (rôle : {utilisateur.role})"
    )
    return TokenResponse(access_token=token, token_type="bearer")
