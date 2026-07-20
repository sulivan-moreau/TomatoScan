# Tests des endpoints /reports — historique d'entraînement et évaluation MobileNetV2
import json
import os

import pytest

# Identifiants définis dans tests/conftest.py
NOM_ADMIN = os.getenv("ADMIN_USERNAME", "admin_test")
MOT_DE_PASSE_ADMIN = os.getenv("ADMIN_PASSWORD", "motdepasse_test_123")

# Contenu CSV minimal pour les tests — 2 epochs avec val_accuracy croissante
CSV_CONTENU = (
    "epoch,train_loss,train_accuracy,val_loss,val_accuracy\n"
    "1,0.7588,0.7760,0.3914,0.9001\n"
    "2,0.4102,0.8748,0.3121,0.9084\n"
)


async def _obtenir_token_valide(client) -> str:
    """Effectue une connexion et retourne le token JWT Bearer."""
    reponse = await client.post(
        "/auth/token",
        json={"username": NOM_ADMIN, "password": MOT_DE_PASSE_ADMIN},
    )
    return reponse.json()["access_token"]


async def test_reports_sans_token(client):
    """Appel à /reports sans token Bearer — attend status 401."""
    reponse = await client.get("/reports")
    assert reponse.status_code == 401


async def test_reports_avec_token(tmp_path, monkeypatch, client):
    """CSV temporaire pointé par REPORTS_PATH — attend 200 avec les champs attendus."""
    # Création du fichier CSV temporaire via tmp_path pytest
    fichier_csv = tmp_path / "historique_test.csv"
    fichier_csv.write_text(CSV_CONTENU, encoding="utf-8")

    # Injection de REPORTS_PATH pour pointer vers le CSV temporaire
    monkeypatch.setenv("REPORTS_PATH", str(fichier_csv))

    token = await _obtenir_token_valide(client)
    reponse = await client.get("/reports", headers={"Authorization": f"Bearer {token}"})

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


async def test_reports_fichier_introuvable(monkeypatch, client):
    """REPORTS_PATH pointe vers un fichier inexistant — attend status 404."""
    monkeypatch.setenv("REPORTS_PATH", "/chemin/inexistant/historique.csv")

    token = await _obtenir_token_valide(client)
    reponse = await client.get("/reports", headers={"Authorization": f"Bearer {token}"})

    assert reponse.status_code == 404
    assert "introuvable" in reponse.json()["detail"]


# Rapport d'évaluation minimal pour les tests de GET /reports/evaluation
EVALUATION_CONTENU = {
    "date": "2026-06-24T16:32:36.184168",
    "modele": "MobileNetV2",
    "meilleure_epoch": 13,
    "meilleure_accuracy_validation": 0.9455,
    "accuracy_test": 0.9355,
    "classes_sous_performantes": [],
    "rapport_classification": {
        "Tomato_healthy": {
            "precision": 0.9793,
            "recall": 0.9958,
            "f1-score": 0.9875,
            "support": 238.0,
        }
    },
}


async def test_evaluation_sans_token(client):
    """Appel à /reports/evaluation sans token Bearer — attend status 401."""
    reponse = await client.get("/reports/evaluation")
    assert reponse.status_code == 401


async def test_evaluation_avec_token(tmp_path, monkeypatch, client):
    """JSON temporaire pointé par EVALUATION_PATH — attend 200 avec les champs attendus."""
    fichier_json = tmp_path / "rapport_evaluation_test.json"
    fichier_json.write_text(
        json.dumps(EVALUATION_CONTENU, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setenv("EVALUATION_PATH", str(fichier_json))

    token = await _obtenir_token_valide(client)
    reponse = await client.get(
        "/reports/evaluation", headers={"Authorization": f"Bearer {token}"}
    )

    assert reponse.status_code == 200
    corps = reponse.json()

    assert corps["modele"] == "MobileNetV2"
    assert corps["meilleure_epoch"] == 13
    assert corps["accuracy_test"] == pytest.approx(0.9355, rel=1e-4)
    assert corps["classes_sous_performantes"] == []
    # Le rapport de classification par classe est bien transmis
    assert "Tomato_healthy" in corps["rapport_classification"]


async def test_evaluation_fichier_introuvable(monkeypatch, client):
    """EVALUATION_PATH pointe vers un fichier inexistant — attend status 404."""
    monkeypatch.setenv("EVALUATION_PATH", "/chemin/inexistant/evaluation.json")

    token = await _obtenir_token_valide(client)
    reponse = await client.get(
        "/reports/evaluation", headers={"Authorization": f"Bearer {token}"}
    )

    assert reponse.status_code == 404
    assert "introuvable" in reponse.json()["detail"]
