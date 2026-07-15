# Tests de l'endpoint POST /predict
# model_service.predire est mocké pour isoler les tests du checkpoint .pt
import io
import os
from unittest.mock import patch

from PIL import Image, UnidentifiedImageError

# Identifiants définis dans tests/conftest.py
NOM_ADMIN = os.getenv("ADMIN_USERNAME", "admin_test")
MOT_DE_PASSE_ADMIN = os.getenv("ADMIN_PASSWORD", "motdepasse_test_123")

# Chemins de mock — on patche l'objet dans le module qui l'importe
_PREDIRE = "tomatoscan.api.routes.predict.model_service.predire"
_DISPONIBLE = "tomatoscan.api.routes.predict.model_service.modele_disponible"


async def _obtenir_token_valide(client) -> str:
    """Obtient un token JWT valide pour authentifier les requêtes de test."""
    reponse = await client.post(
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


# --- Tests avec modèle mocké ------------------------------------------------


@patch(_PREDIRE, return_value=("Tomato_healthy", 0.99))
@patch(_DISPONIBLE, return_value=True)
async def test_predict_image_valide(mock_dispo, mock_predire, client):
    """Envoie une image JPG valide avec token et modèle mocké — attend 200 avec classe et confiance."""
    token = await _obtenir_token_valide(client)
    reponse = await client.post(
        "/predict",
        headers={"Authorization": f"Bearer {token}"},
        files={"fichier": ("feuille.jpg", _creer_image_jpg(), "image/jpeg")},
    )
    assert reponse.status_code == 200
    corps = reponse.json()
    assert "classe" in corps
    assert "confiance" in corps
    assert isinstance(corps["confiance"], float)
    assert 0.0 <= corps["confiance"] <= 1.0
    # Le mock a bien été appelé — le checkpoint .pt n'est pas chargé
    mock_predire.assert_called_once()


@patch(_PREDIRE, return_value=("Tomato_Early_blight", 0.85))
@patch(_DISPONIBLE, return_value=True)
async def test_predict_maladie_detectee(mock_dispo, mock_predire, client):
    """Vérifie que le message contient 'Maladie détectée' pour une classe non-saine."""
    token = await _obtenir_token_valide(client)
    reponse = await client.post(
        "/predict",
        headers={"Authorization": f"Bearer {token}"},
        files={"fichier": ("feuille.jpg", _creer_image_jpg(), "image/jpeg")},
    )
    assert reponse.status_code == 200
    assert "Maladie détectée" in reponse.json().get("message", "")


@patch(_PREDIRE, side_effect=UnidentifiedImageError("cannot identify image file"))
@patch(_DISPONIBLE, return_value=True)
async def test_predict_image_corrompue(mock_dispo, mock_predire, client):
    """Envoie un .jpg avec contenu invalide — PIL.UnidentifiedImageError doit provoquer un 400."""
    token = await _obtenir_token_valide(client)
    reponse = await client.post(
        "/predict",
        headers={"Authorization": f"Bearer {token}"},
        files={"fichier": ("feuille.jpg", b"pas une image", "image/jpeg")},
    )
    assert reponse.status_code == 400
    assert "corromp" in reponse.json()["detail"].lower()


@patch(_DISPONIBLE, return_value=False)
async def test_predict_modele_indisponible(mock_dispo, client):
    """Vérifie que /predict retourne 503 quand le modèle n'est pas encore chargé."""
    token = await _obtenir_token_valide(client)
    reponse = await client.post(
        "/predict",
        headers={"Authorization": f"Bearer {token}"},
        files={"fichier": ("feuille.jpg", _creer_image_jpg(), "image/jpeg")},
    )
    assert reponse.status_code == 503
    assert "indisponible" in reponse.json()["detail"].lower()


@patch(_PREDIRE, side_effect=RuntimeError("erreur GPU inattendue"))
@patch(_DISPONIBLE, return_value=True)
async def test_predict_erreur_interne(mock_dispo, mock_predire, client):
    """Vérifie que /predict retourne 503 pour une exception inattendue du modèle."""
    token = await _obtenir_token_valide(client)
    reponse = await client.post(
        "/predict",
        headers={"Authorization": f"Bearer {token}"},
        files={"fichier": ("feuille.jpg", _creer_image_jpg(), "image/jpeg")},
    )
    assert reponse.status_code == 503


# --- Tests sans modèle (validation en amont) --------------------------------


async def test_predict_format_invalide(client):
    """Envoie un fichier .txt avec token — attend status 400 (format rejeté avant le modèle)."""
    token = await _obtenir_token_valide(client)
    reponse = await client.post(
        "/predict",
        headers={"Authorization": f"Bearer {token}"},
        files={"fichier": ("notes.txt", b"ceci n'est pas une image", "text/plain")},
    )
    assert reponse.status_code == 400


async def test_predict_fichier_trop_lourd(client):
    """Envoie un fichier JPEG dépassant 5 Mo avec token — attend status 400."""
    token = await _obtenir_token_valide(client)
    # Génère un contenu de 6 Mo (dépasse la limite de 5 Mo)
    gros_contenu = b"\xff\xd8\xff" + b"x" * (6 * 1024 * 1024)
    reponse = await client.post(
        "/predict",
        headers={"Authorization": f"Bearer {token}"},
        files={"fichier": ("photo.jpg", gros_contenu, "image/jpeg")},
    )
    assert reponse.status_code == 400
