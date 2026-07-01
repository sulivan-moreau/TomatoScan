"""Tests des cas limites de sécurité JWT — couvre les branches non testées de security.py.

Lignes visées :
- 33-34 : creer_token_acces() avec SECRET_KEY absente → RuntimeError
- 60-61 : obtenir_utilisateur_courant() avec SECRET_KEY absente → 401
- 67    : obtenir_utilisateur_courant() avec token sans champ 'sub' → 401
"""

import os
import time

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from tomatoscan.api.core.security import creer_token_acces
from tomatoscan.api.main import app

NOM_ADMIN = os.getenv("ADMIN_USERNAME", "admin_test")
MOT_DE_PASSE_ADMIN = os.getenv("ADMIN_PASSWORD", "motdepasse_test_123")

client = TestClient(app)


def test_token_sans_secret_key(monkeypatch):
    """SECRET_KEY absente → comportement sécurisé sur les deux chemins critiques.

    - Validation d'un token existant : obtenir_utilisateur_courant() retourne 401 (lignes 60-61)
    - Création d'un nouveau token : creer_token_acces() lève RuntimeError (lignes 33-34)
    """
    # Obtenir un token valide pendant que SECRET_KEY est encore présente
    reponse = client.post(
        "/auth/token",
        json={"username": NOM_ADMIN, "password": MOT_DE_PASSE_ADMIN},
    )
    token_existant = reponse.json()["access_token"]

    # Supprimer SECRET_KEY de l'environnement — monkeypatch la restaure après le test
    monkeypatch.delenv("SECRET_KEY")

    # Avec SECRET_KEY absente, un token existant ne peut plus être validé → 401 (lignes 60-61)
    reponse_protege = client.get(
        "/predictions/history",
        headers={"Authorization": f"Bearer {token_existant}"},
    )
    assert reponse_protege.status_code == 401

    # Avec SECRET_KEY absente, creer_token_acces() lève RuntimeError (lignes 33-34)
    # Appel direct à la fonction pour tester ce chemin sans passer par le TestClient
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        creer_token_acces({"sub": "utilisateur_test"})


def test_token_sans_sub():
    """JWT signé avec une clé valide mais sans le champ 'sub' → 401.

    Couvre security.py ligne 67 : if nom_utilisateur is None: raise erreur_401
    """
    cle_secrete = os.getenv("SECRET_KEY", "cle_secrete_test_uniquement")
    algorithme = os.getenv("ALGORITHM", "HS256")

    # Construire un JWT dont la signature est correcte mais sans le champ 'sub'
    token_sans_sub = jwt.encode(
        {"exp": int(time.time()) + 3600, "donnee": "valeur_quelconque"},
        cle_secrete,
        algorithm=algorithme,
    )

    # L'endpoint protégé doit rejeter ce token : 'sub' absent → nom_utilisateur est None → 401
    reponse = client.get(
        "/predictions/history",
        headers={"Authorization": f"Bearer {token_sans_sub}"},
    )
    assert reponse.status_code == 401
