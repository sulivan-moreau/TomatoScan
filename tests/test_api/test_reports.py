# Tests de l'endpoint GET /reports — historique d'entraînement MobileNetV2
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


# --- GET /reports/evaluation --------------------------------------------------

RAPPORT_EVALUATION_CONTENU = {
    "date": "2026-07-20T00:00:00",
    "modele": "MobileNetV2",
    "meilleure_epoch": 13,
    "meilleure_accuracy_validation": 0.9455,
    "accuracy_test": 0.9355,
    "classes_sous_performantes": ["Tomato_Early_blight"],
    "rapport_classification": {
        "Tomato_healthy": {
            "precision": 0.98,
            "recall": 0.97,
            "f1-score": 0.975,
            "support": 100.0,
        },
        "Tomato_Early_blight": {
            "precision": 0.7,
            "recall": 0.65,
            "f1-score": 0.674,
            "support": 80.0,
        },
        "accuracy": 0.9355,
        "macro avg": {
            "precision": 0.84,
            "recall": 0.81,
            "f1-score": 0.8245,
            "support": 180.0,
        },
    },
}


async def test_reports_evaluation_sans_token(client):
    """Appel à /reports/evaluation sans token — attend status 401."""
    reponse = await client.get("/reports/evaluation")
    assert reponse.status_code == 401


async def test_reports_evaluation_avec_token(tmp_path, monkeypatch, client):
    """Rapport JSON temporaire pointé par EVALUATION_REPORT_DIR — attend 200
    avec les champs attendus, la ligne "accuracy" (un float, pas un dict)
    n'empêche pas la validation du reste."""
    fichier_rapport = tmp_path / "rapport_evaluation_20260101_000000.json"
    fichier_rapport.write_text(json.dumps(RAPPORT_EVALUATION_CONTENU), encoding="utf-8")
    monkeypatch.setenv("EVALUATION_REPORT_DIR", str(tmp_path))

    token = await _obtenir_token_valide(client)
    reponse = await client.get(
        "/reports/evaluation", headers={"Authorization": f"Bearer {token}"}
    )

    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["accuracy_test"] == pytest.approx(0.9355, rel=1e-4)
    assert corps["classes_sous_performantes"] == ["Tomato_Early_blight"]
    assert corps["rapport_classification"]["Tomato_healthy"][
        "f1-score"
    ] == pytest.approx(0.975, rel=1e-4)


async def test_reports_evaluation_prend_le_rapport_le_plus_recent(
    tmp_path, monkeypatch, client
):
    """Deux rapports horodatés dans le dossier → le plus récent (tri lexicographique
    sur le nom horodaté) est retourné, pas le premier trouvé."""
    ancien = dict(RAPPORT_EVALUATION_CONTENU, accuracy_test=0.5)
    recent = dict(RAPPORT_EVALUATION_CONTENU, accuracy_test=0.99)
    (tmp_path / "rapport_evaluation_20260101_000000.json").write_text(
        json.dumps(ancien), encoding="utf-8"
    )
    (tmp_path / "rapport_evaluation_20260601_000000.json").write_text(
        json.dumps(recent), encoding="utf-8"
    )
    monkeypatch.setenv("EVALUATION_REPORT_DIR", str(tmp_path))

    token = await _obtenir_token_valide(client)
    reponse = await client.get(
        "/reports/evaluation", headers={"Authorization": f"Bearer {token}"}
    )

    assert reponse.json()["accuracy_test"] == pytest.approx(0.99, rel=1e-4)


async def test_reports_evaluation_aucun_rapport(tmp_path, monkeypatch, client):
    """Dossier vide (aucun rapport_evaluation_*.json) — attend status 404."""
    monkeypatch.setenv("EVALUATION_REPORT_DIR", str(tmp_path))

    token = await _obtenir_token_valide(client)
    reponse = await client.get(
        "/reports/evaluation", headers={"Authorization": f"Bearer {token}"}
    )

    assert reponse.status_code == 404


# --- GET /reports/confusion-matrix ---------------------------------------------


async def test_confusion_matrix_sans_token(client):
    """Appel à /reports/confusion-matrix sans token — attend status 401."""
    reponse = await client.get("/reports/confusion-matrix")
    assert reponse.status_code == 401


async def test_confusion_matrix_avec_token(tmp_path, monkeypatch, client):
    """Image PNG présente dans EVALUATION_REPORT_DIR — attend 200 avec le
    content-type image/png et les octets exacts du fichier."""
    contenu_png = b"\x89PNG\r\n\x1a\nfaux-contenu-png-pour-le-test"
    (tmp_path / "confusion_matrix.png").write_bytes(contenu_png)
    monkeypatch.setenv("EVALUATION_REPORT_DIR", str(tmp_path))

    token = await _obtenir_token_valide(client)
    reponse = await client.get(
        "/reports/confusion-matrix", headers={"Authorization": f"Bearer {token}"}
    )

    assert reponse.status_code == 200
    assert reponse.headers["content-type"] == "image/png"
    assert reponse.content == contenu_png


async def test_confusion_matrix_introuvable(tmp_path, monkeypatch, client):
    """Dossier sans confusion_matrix.png — attend status 404."""
    monkeypatch.setenv("EVALUATION_REPORT_DIR", str(tmp_path))

    token = await _obtenir_token_valide(client)
    reponse = await client.get(
        "/reports/confusion-matrix", headers={"Authorization": f"Bearer {token}"}
    )

    assert reponse.status_code == 404
