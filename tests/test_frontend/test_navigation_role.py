"""Tests de bout en bout (AppTest) — flux connexion puis navigation par rôle.

Complète tests/test_frontend/test_api_client.py : ici on exécute le vrai
app.py + les vraies pages via streamlit.testing.v1.AppTest, pour vérifier que
le rôle mis en session au login pilote bien la navigation et les garde-fous
de page. Seul requests.post/get est mocké (aucun appel réseau réel).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import jwt
from streamlit.testing.v1 import AppTest

# `streamlit run` ajoute automatiquement le dossier du script principal à
# sys.path — AppTest n'exécute pas ce chemin de démarrage, on le reproduit ici.
_FRONT_DIR = str(Path(__file__).resolve().parents[2] / "src" / "tomatoscan" / "front")
if _FRONT_DIR not in sys.path:
    sys.path.insert(0, _FRONT_DIR)

APP_PATH = "src/tomatoscan/front/app.py"


def _jwt(role: str, sub: str = "utilisateur_test") -> str:
    return jwt.encode(
        {"sub": sub, "role": role, "exp": 9_999_999_999},
        "secret-de-test-sans-rapport-avec-la-cle-reelle",
        algorithm="HS256",
    )


def _reponse_login_mock(token: str) -> MagicMock:
    reponse = MagicMock()
    reponse.status_code = 200
    reponse.ok = True
    reponse.json.return_value = {"access_token": token, "token_type": "bearer"}
    return reponse


def _reponse_me_mock(username: str, role: str) -> MagicMock:
    reponse = MagicMock()
    reponse.status_code = 200
    reponse.ok = True
    reponse.json.return_value = {"username": username, "role": role}
    return reponse


def _connecter(
    at: AppTest, nom_utilisateur: str, mot_de_passe: str, token: str, role: str
) -> AppTest:
    """Simule une connexion complète via le vrai formulaire pages/login.py,
    avec uniquement l'appel réseau mocké."""
    at.switch_page("pages/login.py")
    at.run()

    with (
        patch(
            "tomatoscan.front.utils.api_client.requests.post",
            return_value=_reponse_login_mock(token),
        ),
        patch(
            "tomatoscan.front.utils.api_client.requests.get",
            return_value=_reponse_me_mock(nom_utilisateur, role),
        ),
    ):
        at.text_input[0].input(nom_utilisateur).run()
        at.text_input[1].input(mot_de_passe).run()
        at.button[0].click().run()

    return at


def test_admin_a_acces_aux_pages_admin_et_a_la_section_administration():
    at = AppTest.from_file(APP_PATH)
    at.run()
    at = _connecter(at, "admin", "admin123", _jwt("admin"), "admin")
    assert at.session_state["role"] == "admin"

    at.switch_page("pages/dashboard.py")
    at.run()
    assert not at.exception
    assert "Accès réservé aux administrateurs." not in [e.value for e in at.error]

    at.switch_page("pages/creer_membre.py")
    at.run()
    assert not at.exception
    assert "Accès réservé aux administrateurs." not in [e.value for e in at.error]

    at.switch_page("pages/accueil.py")
    at.run()
    assert "Administration" in " ".join(m.value for m in at.markdown)


def test_agriculteur_est_bloque_sur_les_pages_admin():
    at = AppTest.from_file(APP_PATH)
    at.run()
    at = _connecter(at, "agriculteur01", "secret", _jwt("agriculteur"), "agriculteur")
    assert at.session_state["role"] == "agriculteur"

    at.switch_page("pages/dashboard.py")
    at.run()
    assert not at.exception
    assert "Accès réservé aux administrateurs." in [e.value for e in at.error]

    at.switch_page("pages/creer_membre.py")
    at.run()
    assert "Accès réservé aux administrateurs." in [e.value for e in at.error]

    at.switch_page("pages/accueil.py")
    at.run()
    assert "Administration" not in " ".join(m.value for m in at.markdown)


def test_changer_le_role_dans_le_token_change_immediatement_l_acces_affiche():
    """Le rôle n'est jamais mis en cache dans une variable séparée : une
    reconnexion avec un autre rôle, sans logout explicite, doit changer l'accès
    dès le rerun suivant — preuve qu'aucun état résiduel du compte précédent
    ne survit."""
    at = AppTest.from_file(APP_PATH)
    at.run()

    at = _connecter(at, "admin", "admin123", _jwt("admin"), "admin")
    at.switch_page("pages/dashboard.py")
    at.run()
    assert "Accès réservé aux administrateurs." not in [e.value for e in at.error]

    at = _connecter(at, "agriculteur01", "secret", _jwt("agriculteur"), "agriculteur")
    at.switch_page("pages/dashboard.py")
    at.run()
    assert "Accès réservé aux administrateurs." in [e.value for e in at.error]
