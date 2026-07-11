"""Initialisation du compte administrateur en base de données.

Avant l'introduction des rôles, l'admin était vérifié uniquement contre
ADMIN_USERNAME/ADMIN_PASSWORD (.env), sans jamais toucher la table `users`.
Cette fonction fait le pont : elle garantit qu'une ligne User avec role="admin"
et un mot de passe hashé existe en base, pour que /auth/token puisse authentifier
tout le monde (admin compris) de la même façon, via la BDD.
"""

import os

from loguru import logger
from sqlalchemy.orm import Session

from tomatoscan.api.core.security import hacher_mot_de_passe
from tomatoscan.database.modeles import User


def bootstrap_admin(session: Session) -> None:
    """Crée ou met à niveau le compte admin à partir des identifiants du `.env`.

    Idempotent : si le compte existe déjà avec le rôle "admin" et un mot de passe
    hashé, ne fait rien. Corrige aussi le cas d'un compte auto-créé par /predict
    avant cette fonctionnalité (role="agriculteur", hashed_password="").
    """
    nom_admin = os.getenv("ADMIN_USERNAME", "")
    mot_de_passe_admin = os.getenv("ADMIN_PASSWORD", "")

    if not nom_admin or not mot_de_passe_admin:
        logger.warning(
            "ADMIN_USERNAME/ADMIN_PASSWORD absents de l'environnement — "
            "aucun compte admin initialisé en BDD."
        )
        return

    utilisateur = session.query(User).filter_by(username=nom_admin).first()

    if utilisateur is None:
        session.add(
            User(
                username=nom_admin,
                email=f"{nom_admin}@tomatoscan.local",
                hashed_password=hacher_mot_de_passe(mot_de_passe_admin),
                role="admin",
            )
        )
        session.commit()
        logger.info(f"Compte admin {nom_admin!r} créé en BDD.")
    elif utilisateur.role != "admin" or not utilisateur.hashed_password:
        utilisateur.role = "admin"
        utilisateur.hashed_password = hacher_mot_de_passe(mot_de_passe_admin)
        session.commit()
        logger.info(
            f"Compte {nom_admin!r} mis à niveau en admin (rôle + mot de passe hashé)."
        )
