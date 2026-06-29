# Tests de l'endpoint POST /predict
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from tomatoscan.api.main import app

client = TestClient(app)


def _creer_image_jpg(largeur: int = 100, hauteur: int = 100) -> bytes:
    """Crée une image JPEG valide en mémoire pour les tests."""
    image = Image.new("RGB", (largeur, hauteur), color=(120, 180, 60))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_predict_image_valide():
    """Envoie une image JPG valide — attend status 200 avec classe et confiance."""
    image_bytes = _creer_image_jpg()
    reponse = client.post(
        "/predict",
        files={"fichier": ("feuille.jpg", image_bytes, "image/jpeg")},
    )
    assert reponse.status_code == 200
    corps = reponse.json()
    assert "classe" in corps
    assert "confiance" in corps
    assert isinstance(corps["confiance"], float)
    assert 0.0 <= corps["confiance"] <= 1.0


def test_predict_format_invalide():
    """Envoie un fichier .txt — attend status 400."""
    reponse = client.post(
        "/predict",
        files={"fichier": ("notes.txt", b"ceci n'est pas une image", "text/plain")},
    )
    assert reponse.status_code == 400


def test_predict_fichier_trop_lourd():
    """Envoie un fichier JPEG dépassant 5 Mo — attend status 400."""
    # Génère un contenu de 6 Mo (dépasse la limite de 5 Mo)
    gros_contenu = b"\xff\xd8\xff" + b"x" * (6 * 1024 * 1024)
    reponse = client.post(
        "/predict",
        files={"fichier": ("photo.jpg", gros_contenu, "image/jpeg")},
    )
    assert reponse.status_code == 400
