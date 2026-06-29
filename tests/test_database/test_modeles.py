"""
Tests des modèles SQLAlchemy User et Prediction.
Base SQLite en mémoire — aucune dépendance PostgreSQL requise.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tomatoscan.database.connexion import Base
from tomatoscan.database.modeles import Prediction, User


@pytest.fixture
def session_test():
    """Crée une BDD SQLite en mémoire, les tables, une session, puis nettoie après le test."""
    moteur_test = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(moteur_test)
    SessionTest = sessionmaker(bind=moteur_test)
    session = SessionTest()
    yield session
    session.close()
    Base.metadata.drop_all(moteur_test)


def test_creer_user(session_test):
    """Crée un User en BDD et vérifie que tous les champs sont enregistrés correctement."""
    utilisateur = User(
        username="agriculteur1",
        email="agriculteur@test.com",
        hashed_password="hash_bcrypt_123",
        role="agriculteur",
    )
    session_test.add(utilisateur)
    session_test.commit()

    resultat = session_test.query(User).filter_by(username="agriculteur1").first()
    assert resultat is not None
    assert resultat.username == "agriculteur1"
    assert resultat.email == "agriculteur@test.com"
    assert resultat.role == "agriculteur"
    assert resultat.id is not None
    assert resultat.created_at is not None


def test_creer_prediction(session_test):
    """Crée un User puis une Prediction liée — vérifie la FK et la relation ORM."""
    utilisateur = User(
        username="admin1",
        email="admin@test.com",
        hashed_password="hash_bcrypt_456",
        role="admin",
    )
    session_test.add(utilisateur)
    session_test.commit()

    prediction = Prediction(
        user_id=utilisateur.id,
        nom_fichier="feuille_tomate.jpg",
        classe_predite="Tomato_Early_blight",
        confiance=0.92,
    )
    session_test.add(prediction)
    session_test.commit()

    resultat = session_test.query(Prediction).filter_by(user_id=utilisateur.id).first()
    assert resultat is not None
    assert resultat.nom_fichier == "feuille_tomate.jpg"
    assert resultat.classe_predite == "Tomato_Early_blight"
    assert resultat.confiance == 0.92
    # Vérification de la relation ORM vers l'utilisateur
    assert resultat.utilisateur.username == "admin1"
    assert resultat.user_id == utilisateur.id
