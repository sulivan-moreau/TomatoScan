"""Tests de bout en bout (AppTest) — flux connexion puis navigation par rôle.

Complète tests/test_frontend/test_api_client.py : ici on exécute le vrai
app.py + les vraies pages via streamlit.testing.v1.AppTest (exécution réelle
du script, pas un mock de haut niveau), pour vérifier que le rôle affiché
correspond toujours au token réellement en session — architecture où
session_state["role"] n'existe plus du tout : le rôle est recalculé à la
demande via api_client.obtenir_role(token) partout où il est nécessaire
(app.py, pages/accueil.py, pages/dashboard.py, pages/creer_membre.py,
pages/history.py). Voir docs/audit_role_final_complet.md pour le
raisonnement complet derrière ce choix.

Seul requests.post est mocké (aucun appel réseau réel) — tout le reste
(session_state, rerun, navigation, garde-fous de page) est exécuté pour de
vrai par Streamlit.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import jwt
from streamlit.testing.v1 import AppTest

# `streamlit run` ajoute automatiquement le dossier du script principal à
# sys.path (streamlit.web.bootstrap._fix_sys_path), ce qui permet aux pages
# de faire `from utils import api_client`. AppTest n'exécute pas ce chemin de
# démarrage (il instancie directement un ScriptRunner) — on reproduit donc
# manuellement cet ajout ici, sinon chaque script exécuté par AppTest lève
# ModuleNotFoundError: No module named 'utils'.
_FRONT_DIR = str(Path(__file__).resolve().parents[2] / "src" / "tomatoscan" / "front")
if _FRONT_DIR not in sys.path:
    sys.path.insert(0, _FRONT_DIR)

APP_PATH = "src/tomatoscan/front/app.py"
SECRET_TEST = "secret-de-test-sans-rapport-avec-la-cle-reelle"


def _jwt(role: str, sub: str = "utilisateur_test") -> str:
    """Construit un JWT via PyJWT (comme le ferait l'API réelle)."""
    return jwt.encode(
        {"sub": sub, "role": role, "exp": 9_999_999_999},
        SECRET_TEST,
        algorithm="HS256",
    )


def _reponse_login_mock(token: str) -> MagicMock:
    reponse = MagicMock()
    reponse.status_code = 200
    reponse.ok = True
    reponse.json.return_value = {"access_token": token, "token_type": "bearer"}
    return reponse


def _connecter(
    at: AppTest, nom_utilisateur: str, mot_de_passe: str, token: str
) -> AppTest:
    """Simule une connexion complète via le vrai formulaire pages/login.py,
    avec uniquement l'appel réseau (requests.post) mocké."""
    at.switch_page("pages/login.py")
    at.run()

    with patch(
        "tomatoscan.front.utils.api_client.requests.post",
        return_value=_reponse_login_mock(token),
    ):
        at.text_input[0].input(nom_utilisateur).run()
        at.text_input[1].input(mot_de_passe).run()
        at.button[0].click().run()

    return at


class TestConnexionAdmin:
    """Un token contenant role=admin doit donner accès aux pages admin,
    immédiatement après la connexion (pas besoin d'un second rerun)."""

    def test_connexion_admin_ne_leve_aucune_exception(self):
        at = AppTest.from_file(APP_PATH)
        at.run()
        at = _connecter(at, "admin", "admin123", _jwt("admin"))

        assert not at.exception

    def test_admin_accede_au_tableau_de_bord_sans_etre_bloque(self):
        at = AppTest.from_file(APP_PATH)
        at.run()
        at = _connecter(at, "admin", "admin123", _jwt("admin"))

        at.switch_page("pages/dashboard.py")
        at.run()

        assert not at.exception
        messages_erreur = [e.value for e in at.error]
        assert "Accès réservé aux administrateurs." not in messages_erreur

    def test_admin_accede_a_creer_membre_sans_etre_bloque(self):
        at = AppTest.from_file(APP_PATH)
        at.run()
        at = _connecter(at, "admin", "admin123", _jwt("admin"))

        at.switch_page("pages/creer_membre.py")
        at.run()

        assert not at.exception
        messages_erreur = [e.value for e in at.error]
        assert "Accès réservé aux administrateurs." not in messages_erreur

    def test_accueil_affiche_bien_la_section_administration_pour_un_admin(self):
        at = AppTest.from_file(APP_PATH)
        at.run()
        at = _connecter(at, "admin", "admin123", _jwt("admin"))

        at.switch_page("pages/accueil.py")
        at.run()

        assert not at.exception
        contenu = " ".join(m.value for m in at.markdown)
        assert "Administration" in contenu


class TestConnexionAgriculteur:
    """Un token contenant role=agriculteur doit être bloqué sur les pages
    admin, et ne jamais afficher la section Administration de l'accueil —
    même immédiatement après la connexion."""

    def test_connexion_agriculteur_ne_leve_aucune_exception(self):
        at = AppTest.from_file(APP_PATH)
        at.run()
        at = _connecter(at, "agriculteur01", "secret", _jwt("agriculteur"))

        assert not at.exception

    def test_agriculteur_est_bloque_sur_le_tableau_de_bord(self):
        at = AppTest.from_file(APP_PATH)
        at.run()
        at = _connecter(at, "agriculteur01", "secret", _jwt("agriculteur"))

        at.switch_page("pages/dashboard.py")
        at.run()

        assert not at.exception
        messages_erreur = [e.value for e in at.error]
        assert "Accès réservé aux administrateurs." in messages_erreur

    def test_agriculteur_est_bloque_sur_creer_membre(self):
        at = AppTest.from_file(APP_PATH)
        at.run()
        at = _connecter(at, "agriculteur01", "secret", _jwt("agriculteur"))

        at.switch_page("pages/creer_membre.py")
        at.run()

        assert not at.exception
        messages_erreur = [e.value for e in at.error]
        assert "Accès réservé aux administrateurs." in messages_erreur

    def test_accueil_n_affiche_pas_la_section_administration_pour_un_agriculteur(self):
        at = AppTest.from_file(APP_PATH)
        at.run()
        at = _connecter(at, "agriculteur01", "secret", _jwt("agriculteur"))

        at.switch_page("pages/accueil.py")
        at.run()

        assert not at.exception
        contenu = " ".join(m.value for m in at.markdown)
        assert "Administration" not in contenu


class TestImpossibiliteDeDesynchronisation:
    """Preuve directe qu'il n'existe plus de state "role" à désynchroniser :
    session_state ne contient jamais la clé "role", avant ni après connexion,
    quel que soit le rôle du compte connecté."""

    def test_session_state_ne_contient_jamais_la_cle_role_apres_connexion_admin(self):
        at = AppTest.from_file(APP_PATH)
        at.run()
        at = _connecter(at, "admin", "admin123", _jwt("admin"))

        assert "role" not in at.session_state

    def test_session_state_ne_contient_jamais_la_cle_role_apres_connexion_agriculteur(
        self,
    ):
        at = AppTest.from_file(APP_PATH)
        at.run()
        at = _connecter(at, "agriculteur01", "secret", _jwt("agriculteur"))

        assert "role" not in at.session_state

    def test_changer_le_role_dans_le_token_change_immediatement_l_acces_affiche(self):
        """Le rôle n'est jamais mis en cache dans une variable séparée : si un
        second compte se connecte avec un token différent (autre rôle) sur la
        même session, sans passer par un logout explicite, l'accès affiché
        doit refléter EXACTEMENT le nouveau token, dès le premier rerun qui
        suit — sans dépendre d'un quelconque état résiduel du compte
        précédent. C'est un test plus strict qu'un simple aller-retour
        déconnexion/reconnexion : il prouve qu'il n'existe aucune valeur
        "role" mise en cache qui pourrait survivre au changement de token.

        Note d'implémentation : ce test réutilise directement _connecter()
        une seconde fois plutôt que de cliquer sur le bouton "Déconnexion" du
        sidebar — AppTest, via le mécanisme de routage par dossier pages/
        (PagesManager.uses_pages_directory), n'exécute pas app.py au complet
        (donc pas sidebar_header()) lors d'un switch_page() vers une page du
        dossier pages/, seulement le contenu de la page elle-même. Le bouton
        "Déconnexion" n'est donc pas capturable de façon fiable ici — mais
        login.py écrase de toute façon token/username sans condition, donc
        une reconnexion directe est un test strictement équivalent (et même
        plus strict, puisqu'il ne bénéficie d'aucun `clear()` intermédiaire).
        """
        at = AppTest.from_file(APP_PATH)
        at.run()

        # 1) connexion admin — accès attendu
        at = _connecter(at, "admin", "admin123", _jwt("admin"))
        at.switch_page("pages/dashboard.py")
        at.run()
        assert "Accès réservé aux administrateurs." not in [e.value for e in at.error]

        # 2) reconnexion avec un compte agriculteur, sans logout explicite —
        # accès attendu bloqué malgré l'admin encore "récent"
        at = _connecter(at, "agriculteur01", "secret", _jwt("agriculteur"))
        at.switch_page("pages/dashboard.py")
        at.run()
        assert "Accès réservé aux administrateurs." in [e.value for e in at.error]
