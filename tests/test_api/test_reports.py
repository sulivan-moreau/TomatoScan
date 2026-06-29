# Tests de l'endpoint GET /reports — historique d'entraînement MobileNetV2
import os

import pytest
from fastapi.testclient import TestClient

from tomatoscan.api.main import app

client = TestClient(app)

# Identifiants définis dans tests/conftest.py
NOM_ADMIN = os.getenv("ADMIN_USERNAME", "admin_test")
MOT_DE_PASSE_ADMIN = os.getenv("ADMIN_PASSWORD", "motdepasse_test_123")

# Contenu CSV minimal pour les tests — 2 epochs avec val_accuracy croissante
CSV_CONTENU = (
    "epoch,train_loss,train_accuracy,val_loss,val_accuracy\n"
    "1,0.7588,0.7760,0.3914,0.9001\n"
    "2,0.4102,0.8748,0.3121,0.9084\n"
)


def _obtenir_token_valide() -> str:
    """Effectue une connexion et retourne le token JWT Bearer."""
    reponse = client.post(
        "/auth/token",
        json={"username": NOM_ADMIN, "password": MOT_DE_PASSE_ADMIN},
    )
    return reponse.json()["access_token"]


def test_reports_sans_token():
    """Appel à /reports sans token Bearer — attend status 401."""
    reponse = client.get("/reports")
    assert reponse.status_code == 401


def test_reports_avec_token(tmp_path, monkeypatch):
    """CSV temporaire pointé par REPORTS_PATH — attend 200 avec les champs attendus."""
    # Création du fichier CSV temporaire via tmp_path pytest
    fichier_csv = tmp_path / "historique_test.csv"
    fichier_csv.write_text(CSV_CONTENU, encoding="utf-8")

    # Injection de REPORTS_PATH pour pointer vers le CSV temporaire
    monkeypatch.setenv("REPORTS_PATH", str(fichier_csv))

    token = _obtenir_token_valide()
    reponse = client.get("/reports", headers={"Authorization": f"Bearer {token}"})

    assert reponse.status_code == 200
    corps = reponse.json()

    # Vérification des champs de RapportResponse
    assert corps["fichier"] == str(fichier_csv)
    assert corps["nb_epochs"] == 2
    assert corps["meilleure_val_accuracy"] == pytest.approx(0.9084, rel=1e-4)
    assert len(corps["historique"]) == 2

    # Vérification du détail de la première epoch
    epoch_1 = corps["historique"][0]
    assert epoch_1["epoch"] == 1
    assert epoch_1["train_loss"] == pytest.approx(0.7588, rel=1e-4)
    assert epoch_1["val_accuracy"] == pytest.approx(0.9001, rel=1e-4)


def test_reports_fichier_introuvable(monkeypatch):
    """REPORTS_PATH pointe vers un fichier inexistant — attend status 404."""
    monkeypatch.setenv("REPORTS_PATH", "/chemin/inexistant/historique.csv")

    token = _obtenir_token_valide()
    reponse = client.get("/reports", headers={"Authorization": f"Bearer {token}"})

    assert reponse.status_code == 404
    assert "introuvable" in reponse.json()["detail"]
