"""Tests de bout en bout (AppTest) — comportement sur 401, factorisé via
utils.session.gerer_erreur_401 (auparavant dupliqué dans 4 pages).

Vérifie que le comportement observable (nettoyage de session + redirection)
reste strictement identique à avant la factorisation, sur les 4 pages
concernées : creer_membre.py, dashboard.py, history.py, predict.py.
"""

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import jwt
from PIL import Image
from streamlit.testing.v1 import AppTest

_FRONT_DIR = str(Path(__file__).resolve().parents[2] / "src" / "tomatoscan" / "front")
if _FRONT_DIR not in sys.path:
    sys.path.insert(0, _FRONT_DIR)

APP_PATH = "src/tomatoscan/front/app.py"


def _image_jpeg_valide() -> bytes:
    """Vraie image JPEG minimale — st.image() décode réellement le contenu
    (PIL), un bytes factice ferait planter le script avant même le bouton."""
    image = Image.new("RGB", (10, 10), color=(80, 160, 40))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _jwt_admin() -> str:
    return jwt.encode(
        {"sub": "admin", "role": "admin", "exp": 9_999_999_999}, "s", algorithm="HS256"
    )


def _reponse_login_mock() -> MagicMock:
    reponse = MagicMock()
    reponse.status_code = 200
    reponse.ok = True
    reponse.json.return_value = {"access_token": _jwt_admin(), "token_type": "bearer"}
    return reponse


def _reponse_401_mock() -> MagicMock:
    reponse = MagicMock()
    reponse.status_code = 401
    reponse.ok = False
    reponse.json.return_value = {"detail": "Token invalide ou expiré"}
    return reponse


def _connecter_admin(at: AppTest) -> AppTest:
    at.switch_page("pages/login.py")
    at.run()
    with patch(
        "tomatoscan.front.utils.api_client.requests.post",
        return_value=_reponse_login_mock(),
    ):
        at.text_input[0].input("admin").run()
        at.text_input[1].input("admin123").run()
        at.button[0].click().run()
    assert "token" in at.session_state
    return at


class TestGestion401Factorisee:
    """Sur chaque page, un 401 renvoyé par l'API doit vider la session (donc
    déconnecter) — comportement inchangé par la factorisation via
    gerer_erreur_401()."""

    def test_dashboard_401_vide_la_session(self):
        at = AppTest.from_file(APP_PATH)
        at.run()
        at = _connecter_admin(at)

        at.switch_page("pages/dashboard.py")
        with patch(
            "tomatoscan.front.utils.api_client.requests.get",
            return_value=_reponse_401_mock(),
        ):
            at.run()

        assert "token" not in at.session_state
        assert not at.exception

    def test_history_401_vide_la_session(self):
        at = AppTest.from_file(APP_PATH)
        at.run()
        at = _connecter_admin(at)

        at.switch_page("pages/history.py")
        with patch(
            "tomatoscan.front.utils.api_client.requests.get",
            return_value=_reponse_401_mock(),
        ):
            at.run()

        assert "token" not in at.session_state
        assert not at.exception

    def test_creer_membre_401_vide_la_session(self):
        at = AppTest.from_file(APP_PATH)
        at.run()
        at = _connecter_admin(at)

        at.switch_page("pages/creer_membre.py")
        at.run()
        with patch(
            "tomatoscan.front.utils.api_client.requests.post",
            return_value=_reponse_401_mock(),
        ):
            at.text_input[0].input("nouveau_agri").run()
            at.text_input[1].input("motdepasse123").run()
            at.button[0].click().run()

        assert "token" not in at.session_state
        assert not at.exception

    def test_predict_401_vide_la_session(self):
        at = AppTest.from_file(APP_PATH)
        at.run()
        at = _connecter_admin(at)

        at.switch_page("pages/predict.py")
        at.run()
        at.file_uploader[0].upload(
            "feuille.jpg", _image_jpeg_valide(), "image/jpeg"
        ).run()
        with patch(
            "tomatoscan.front.utils.api_client.requests.post",
            return_value=_reponse_401_mock(),
        ):
            at.button[0].click().run()

        assert "token" not in at.session_state
        assert not at.exception

    def test_predict_erreur_400_n_efface_pas_la_session(self):
        """Non-régression : seul un 401 doit vider la session — un 400 (image
        invalide) doit rester géré par la branche if erreur.status_code == 400
        de predict.py, pas par gerer_erreur_401 (qui ne fait rien dans ce cas)."""
        at = AppTest.from_file(APP_PATH)
        at.run()
        at = _connecter_admin(at)

        at.switch_page("pages/predict.py")
        at.run()
        at.file_uploader[0].upload(
            "feuille.jpg", _image_jpeg_valide(), "image/jpeg"
        ).run()

        reponse_400 = MagicMock()
        reponse_400.status_code = 400
        reponse_400.ok = False
        reponse_400.json.return_value = {"detail": "Image invalide"}
        with patch(
            "tomatoscan.front.utils.api_client.requests.post",
            return_value=reponse_400,
        ):
            at.button[0].click().run()

        assert "token" in at.session_state
        messages_erreur = [e.value for e in at.error]
        assert "Image invalide — vérifiez le format (jpg/png)." in messages_erreur
