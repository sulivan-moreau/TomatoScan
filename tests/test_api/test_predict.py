# Tests de l'endpoint POST /predict
import io
import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from tomatoscan.api.main import app

client = TestClient(app)

# Identifiants définis dans tests/conftest.py
NOM_ADMIN = os.getenv("ADMIN_USERNAME", "admin_test")
MOT_DE_PASSE_ADMIN = os.getenv("ADMIN_PASSWORD", "motdepasse_test_123")


def _obtenir_token_valide() -> str:
    """Obtient un token JWT valide pour authentifier les requêtes de test."""
    reponse = client.post(
        "/auth/token",
        json={"username": NOM_ADMIN, "password": MOT_DE_PASSE_ADMIN},
    )
    return reponse.json()["access_token"]


def _creer_image_jpg(largeur: int = 100, hauteur: int = 100) -> bytes:
    """Crée une image JPEG valide en mémoire pour les tests."""
    image = Image.new("RGB", (largeur, hauteur), color=(120, 180, 60))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_predict_image_valide():
    """Envoie une image JPG valide avec token — attend status 200 avec classe et confiance."""
    token = _obtenir_token_valide()
    image_bytes = _creer_image_jpg()
    reponse = client.post(
        "/predict",
        headers={"Authorization": f"Bearer {token}"},
        files={"fichier": ("feuille.jpg", image_bytes, "image/jpeg")},
    )
    assert reponse.status_code == 200
    corps = reponse.json()
    assert "classe" in corps
    assert "confiance" in corps
    assert isinstance(corps["confiance"], float)
    assert 0.0 <= corps["confiance"] <= 1.0


def test_predict_format_invalide():
    """Envoie un fichier .txt avec token — attend status 400."""
    token = _obtenir_token_valide()
    reponse = client.post(
        "/predict",
        headers={"Authorization": f"Bearer {token}"},
        files={"fichier": ("notes.txt", b"ceci n'est pas une image", "text/plain")},
    )
    assert reponse.status_code == 400


def test_predict_fichier_trop_lourd():
    """Envoie un fichier JPEG dépassant 5 Mo avec token — attend status 400."""
    token = _obtenir_token_valide()
    # Génère un contenu de 6 Mo (dépasse la limite de 5 Mo)
    gros_contenu = b"\xff\xd8\xff" + b"x" * (6 * 1024 * 1024)
    reponse = client.post(
        "/predict",
        headers={"Authorization": f"Bearer {token}"},
        files={"fichier": ("photo.jpg", gros_contenu, "image/jpeg")},
    )
    assert reponse.status_code == 400
