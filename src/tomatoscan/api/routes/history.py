"""Route GET /predictions/history — historique des prédictions de l'utilisateur connecté.

Retourne la liste des prédictions de l'utilisateur triées par date décroissante.
Authentification JWT Bearer requise.
"""

from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy.orm import Session

from tomatoscan.api.core.security import obtenir_utilisateur_courant
from tomatoscan.api.schemas.history import HistoryItem
from tomatoscan.database.connexion import obtenir_session
from tomatoscan.database.modeles import Prediction, User

router = APIRouter(tags=["Historique"])


@router.get("/predictions/history", response_model=list[HistoryItem])
def obtenir_historique(
    nom_utilisateur: str = Depends(obtenir_utilisateur_courant),
    session: Session = Depends(obtenir_session),
) -> list[HistoryItem]:
    """Retourne l'historique des prédictions de l'utilisateur connecté, trié par date décroissante.

    Si l'utilisateur n'a aucune prédiction enregistrée, retourne une liste vide.
    """
    try:
        # Recherche de l'utilisateur dans la BDD par son nom
        utilisateur = session.query(User).filter_by(username=nom_utilisateur).first()
        if utilisateur is None:
            # Aucun enregistrement BDD pour cet utilisateur — liste vide
            logger.debug(
                f"Utilisateur {nom_utilisateur!r} absent de la BDD, historique vide."
            )
            return []

        # Récupération des prédictions triées par date décroissante (la plus récente en premier)
        predictions = (
            session.query(Prediction)
            .filter_by(user_id=utilisateur.id)
            .order_by(Prediction.created_at.desc())
            .all()
        )
        logger.debug(
            f"{len(predictions)} prédiction(s) trouvée(s) pour {nom_utilisateur!r}."
        )
        return predictions

    except Exception as erreur:
        logger.error(f"Erreur lors de la récupération de l'historique : {erreur}")
        return []
