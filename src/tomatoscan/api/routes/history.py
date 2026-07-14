"""Route GET /predictions/history — historique des prédictions.

Retourne les prédictions triées par date décroissante : celles de l'utilisateur
connecté pour un agriculteur, celles de tout le monde pour un admin.
Authentification JWT Bearer requise.
"""

from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy.orm import Session

from tomatoscan.api.core.security import (
    obtenir_role_courant,
    obtenir_utilisateur_courant,
)
from tomatoscan.api.schemas.history import HistoryItem
from tomatoscan.database.connexion import obtenir_session
from tomatoscan.database.modeles import Prediction, User

router = APIRouter(tags=["Historique"])


@router.get(
    "/predictions/history",
    response_model=list[HistoryItem],
    responses={401: {"description": "Token invalide, expiré ou absent."}},
)
def obtenir_historique(
    nom_utilisateur: str = Depends(obtenir_utilisateur_courant),
    role: str = Depends(obtenir_role_courant),
    session: Session = Depends(obtenir_session),
) -> list[HistoryItem]:
    """Retourne l'historique des prédictions, trié par date décroissante.

    Un agriculteur ne voit que ses propres prédictions. Un admin voit celles
    de tous les utilisateurs. Si l'utilisateur n'a aucune prédiction, retourne
    une liste vide.
    """
    try:
        requete = session.query(Prediction)

        if role != "admin":
            # Recherche de l'utilisateur dans la BDD par son nom
            utilisateur = (
                session.query(User).filter_by(username=nom_utilisateur).first()
            )
            if utilisateur is None:
                # Aucun enregistrement BDD pour cet utilisateur — liste vide
                logger.debug(
                    f"Utilisateur {nom_utilisateur!r} absent de la BDD, historique vide."
                )
                return []
            requete = requete.filter_by(user_id=utilisateur.id)

        # Récupération des prédictions triées par date décroissante (la plus récente en premier)
        predictions = requete.order_by(Prediction.created_at.desc()).all()
        logger.debug(
            f"{len(predictions)} prédiction(s) trouvée(s) pour {nom_utilisateur!r} (rôle : {role})."
        )
        # Conversion explicite en HistoryItem : le type annoncé (list[HistoryItem])
        # doit correspondre à ce qui est réellement retourné, pas seulement à ce
        # que FastAPI sérialise implicitement via response_model.
        return [HistoryItem.model_validate(prediction) for prediction in predictions]

    except Exception as erreur:
        logger.error(f"Erreur lors de la récupération de l'historique : {erreur}")
        return []
