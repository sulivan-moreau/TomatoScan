"""
Routes GET/POST/DELETE /users — gestion des comptes agriculteur.

Toutes réservées aux administrateurs via Depends(verifier_role_admin).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.orm import Session

from tomatoscan.api.core.security import (
    hacher_mot_de_passe,
    obtenir_utilisateur_courant,
    verifier_role_admin,
)
from tomatoscan.api.schemas.users import UserCreate, UserOut
from tomatoscan.database.connexion import obtenir_session
from tomatoscan.database.modeles import Prediction, User

router = APIRouter(
    prefix="/users",
    tags=["Utilisateurs"],
    dependencies=[Depends(verifier_role_admin)],
    # Communs aux 3 routes ci-dessous : verifier_role_admin (et sa dépendance
    # obtenir_role_courant → _decoder_charge) lève 401 puis 403 avant même
    # d'atteindre le corps de la route.
    responses={
        401: {"description": "Token invalide, expiré ou absent."},
        403: {"description": "Rôle insuffisant — réservé aux administrateurs."},
    },
)


@router.get("", response_model=list[UserOut])
def lister_utilisateurs(session: Session = Depends(obtenir_session)) -> list[User]:
    """Liste tous les comptes utilisateurs (id, username, rôle, date de création)."""
    return session.query(User).order_by(User.created_at.asc()).all()


@router.post(
    "",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Ce nom d'utilisateur est déjà utilisé."}},
)
def creer_utilisateur(
    donnees: UserCreate, session: Session = Depends(obtenir_session)
) -> User:
    """Crée un compte agriculteur.

    Le rôle est toujours "agriculteur" : cette route ne permet pas de créer
    un autre compte admin, pour ne pas élargir la surface d'attaque.
    """
    existant = session.query(User).filter_by(username=donnees.username).first()
    if existant is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ce nom d'utilisateur est déjà utilisé.",
        )

    utilisateur = User(
        username=donnees.username,
        email=f"{donnees.username}@tomatoscan.local",
        hashed_password=hacher_mot_de_passe(donnees.password),
        role="agriculteur",
    )
    session.add(utilisateur)
    session.commit()
    session.refresh(utilisateur)
    logger.info(f"Compte agriculteur créé : {donnees.username!r}")
    return utilisateur


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        400: {
            "description": "Un administrateur ne peut pas supprimer son propre compte."
        },
        404: {"description": "Utilisateur introuvable."},
        409: {
            "description": "Suppression refusée — l'utilisateur a des prédictions enregistrées."
        },
    },
)
def supprimer_utilisateur(
    user_id: UUID,
    nom_admin: str = Depends(obtenir_utilisateur_courant),
    session: Session = Depends(obtenir_session),
) -> None:
    """Supprime un compte utilisateur.

    Un admin ne peut pas se supprimer lui-même. La suppression est refusée
    si l'utilisateur a des prédictions enregistrées — on préserve l'historique
    plutôt que de le supprimer en cascade silencieusement (pas de ON DELETE
    CASCADE défini sur la contrainte, ce choix reste donc explicite et visible
    ici plutôt qu'implicite dans le schéma).
    """
    utilisateur = session.query(User).filter_by(id=user_id).first()
    if utilisateur is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable."
        )

    # Comparaison par username plutôt que par id récupéré séparément : équivalent
    # puisque username est unique, et évite une requête supplémentaire.
    if utilisateur.username == nom_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas supprimer votre propre compte.",
        )

    a_des_predictions = (
        session.query(Prediction).filter_by(user_id=user_id).first() is not None
    )
    if a_des_predictions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Impossible de supprimer un utilisateur ayant des prédictions enregistrées.",
        )

    session.delete(utilisateur)
    session.commit()
    logger.info(f"Compte {utilisateur.username!r} supprimé par {nom_admin!r}.")
