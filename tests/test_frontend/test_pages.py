"""Tests de composants métier des pages Streamlit (AppTest) — C17.

Complète test_navigation_role.py / test_gestion_401.py en couvrant les pages
laissées sans test unitaire : le rendu de pages/history.py (cas nominal, état
vide, garde-fous), le masquage de navigation par rôle produit dans app.py, et
la correction des icônes Material affichées en texte brut dans pages/predict.py.

Stratégie : on exécute les vraies pages via streamlit.testing.v1.AppTest, en
mockant uniquement la couche réseau (requests.get/post interceptés) — jamais de
vrai serveur ni de vrai appel HTTP. L'état d'authentification est préréglé
directement dans st.session_state pour cibler une page précise sans rejouer tout
le parcours de connexion.
"""

import io
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import jwt
from PIL import Image
from streamlit.testing.v1 import AppTest

# `streamlit run` ajoute le dossier du script principal à sys.path — AppTest ne
# rejoue pas ce démarrage, on le reproduit ici (comme les autres tests frontend).
_FRONT_DIR = str(Path(__file__).resolve().parents[2] / "src" / "tomatoscan" / "front")
if _FRONT_DIR not in sys.path:
    sys.path.insert(0, _FRONT_DIR)

# Chemin absolu du script principal — robuste quel que soit le répertoire courant
# depuis lequel pytest est lancé (contrairement à un chemin relatif au cwd).
APP_PATH = str(
    Path(__file__).resolve().parents[2] / "src" / "tomatoscan" / "front" / "app.py"
)


def _jwt(role: str) -> str:
    """Fabrique un vrai JWT non expiré (exp très lointain) : is_token_valid() le
    valide localement, sans le moindre appel réseau."""
    return jwt.encode(
        {"sub": "utilisateur_test", "role": role, "exp": 9_999_999_999},
        "secret-de-test-sans-rapport-avec-la-cle-reelle",
        algorithm="HS256",
    )


def _reponse_mock(status_code: int, corps_json) -> MagicMock:
    """Construit un faux requests.Response — .ok suit status_code comme le vrai objet."""
    reponse = MagicMock()
    reponse.status_code = status_code
    reponse.ok = status_code < 400
    reponse.json.return_value = corps_json
    return reponse


def _app_connectee(role: str = "agriculteur") -> AppTest:
    """Prépare une AppTest avec une session déjà authentifiée (token + rôle)."""
    at = AppTest.from_file(APP_PATH)
    at.session_state["token"] = _jwt(role)
    at.session_state["role"] = role
    at.session_state["username"] = "utilisateur_test"
    return at


# Historique factice renvoyé par l'API (deux analyses, une saine, une malade).
_HISTORIQUE = [
    {
        "created_at": "2026-07-20T10:30:00",
        "nom_fichier": "feuille_saine.jpg",
        "classe_predite": "Tomato_healthy",
        "confiance": 0.984,
    },
    {
        "created_at": "2026-07-19T09:15:00",
        "nom_fichier": "feuille_malade.jpg",
        "classe_predite": "Tomato_Late_blight",
        "confiance": 0.712,
    },
]


# --- pages/history.py --------------------------------------------------------


class TestHistorique:
    """Rendu et garde-fous de la page Historique (0 % de couverture auparavant)."""

    def test_rendu_nominal_affiche_le_tableau(self):
        """Cas nominal (rôle admin) : le titre, le lien vers le tableau de bord
        (réservé admin) et le tableau des analyses s'affichent sans erreur."""
        at = _app_connectee("admin")
        at.switch_page("pages/history.py")
        with patch(
            "tomatoscan.front.utils.api_client.requests.get",
            return_value=_reponse_mock(200, _HISTORIQUE),
        ):
            at.run()

        assert not at.exception
        assert "Historique des analyses" in [t.value for t in at.title]
        # Une ligne de résumé indique le nombre d'analyses enregistrées.
        assert any("analyse(s) enregistrée(s)" in c.value for c in at.caption)
        # Le tableau (DataFrame stylé) est bien produit.
        assert len(at.dataframe) == 1

    def test_etat_vide_affiche_le_message_dedie(self):
        """Historique vide : le bloc d'état vide invite à lancer une analyse."""
        at = _app_connectee("agriculteur")
        at.switch_page("pages/history.py")
        with patch(
            "tomatoscan.front.utils.api_client.requests.get",
            return_value=_reponse_mock(200, []),
        ):
            at.run()

        assert not at.exception
        texte_markdown = " ".join(m.value for m in at.markdown)
        assert "Pas encore d'analyse enregistrée" in texte_markdown
        # Aucun tableau ne doit être rendu quand il n'y a pas de données.
        assert len(at.dataframe) == 0

    def test_sans_token_affiche_le_garde_fou(self):
        """Sans token en session, la page bloque l'accès (avertissement) au lieu
        d'appeler l'API."""
        at = AppTest.from_file(APP_PATH)  # aucune session préparée
        at.switch_page("pages/history.py")
        at.run()

        assert "Veuillez vous connecter pour accéder à l'historique." in [
            w.value for w in at.warning
        ]

    def test_session_sans_role_affiche_le_garde_fou(self):
        """Token présent mais rôle absent : la page considère la session incomplète."""
        at = AppTest.from_file(APP_PATH)
        at.session_state["token"] = _jwt("agriculteur")  # pas de "role"
        at.switch_page("pages/history.py")
        at.run()

        assert "Session incomplète, veuillez vous reconnecter." in [
            w.value for w in at.warning
        ]

    def test_401_vide_la_session(self):
        """Un 401 renvoyé par l'API vide la session (déconnexion) via gerer_erreur_401."""
        at = _app_connectee("agriculteur")
        at.switch_page("pages/history.py")
        with patch(
            "tomatoscan.front.utils.api_client.requests.get",
            return_value=_reponse_mock(401, {"detail": "Token expiré"}),
        ):
            at.run()

        assert "token" not in at.session_state
        assert not at.exception


# --- pages/dashboard.py : rendu + cache éco-conception -----------------------

# Réponses factices des trois endpoints agrégés par le tableau de bord.
_RAPPORT = {
    "fichier": "reports/entrainement.csv",
    "nb_epochs": 10,
    "meilleure_val_accuracy": 0.923,
    "historique": [
        {"epoch": 1, "val_accuracy": 0.80},
        {"epoch": 2, "val_accuracy": 0.92},
    ],
}
_UTILISATEURS = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "username": "admin",
        "role": "admin",
        "created_at": "2026-01-01T00:00:00",
    },
    {
        "id": "22222222-2222-2222-2222-222222222222",
        "username": "agri01",
        "role": "agriculteur",
        "created_at": "2026-02-01T00:00:00",
    },
]


def _get_par_url(url, **kwargs) -> MagicMock:
    """side_effect requests.get : route la réponse selon l'endpoint appelé, car
    le tableau de bord interroge trois routes GET différentes en un seul run."""
    if url.endswith("/reports"):
        return _reponse_mock(200, _RAPPORT)
    if url.endswith("/users"):
        return _reponse_mock(200, _UTILISATEURS)
    if url.endswith("/predictions/history"):
        return _reponse_mock(200, _HISTORIQUE)
    return _reponse_mock(404, {"detail": "introuvable"})


class TestTableauDeBord:
    """Rendu du tableau de bord et validation du cache @st.cache_data ajouté pour
    éviter de rejouer les trois appels API à chaque re-run (éco-conception)."""

    def test_rendu_nominal_agrege_les_trois_appels(self):
        at = _app_connectee("admin")
        at.switch_page("pages/dashboard.py")
        with patch(
            "tomatoscan.front.utils.api_client.requests.get", side_effect=_get_par_url
        ):
            at.run()

        assert not at.exception
        assert "Tableau de bord" in [t.value for t in at.title]
        # Métriques du rapport d'entraînement (via _charger_rapport).
        libelles_metriques = [m.label for m in at.metric]
        assert "Epochs entraînées" in libelles_metriques
        assert "Meilleure précision (val)" in libelles_metriques
        # Deux tableaux : détail par epoch + liste des utilisateurs.
        assert len(at.dataframe) == 2

    def test_suppression_agriculteur_invalide_le_cache(self):
        """Le parcours de suppression appelle l'API (DELETE) puis vide le cache des
        données mutables (_vider_cache_donnees) — on vérifie que le DELETE part."""
        at = _app_connectee("admin")
        at.switch_page("pages/dashboard.py")
        cle_agri = "22222222-2222-2222-2222-222222222222"
        with (
            patch(
                "tomatoscan.front.utils.api_client.requests.get",
                side_effect=_get_par_url,
            ),
            patch(
                "tomatoscan.front.utils.api_client.requests.delete",
                return_value=_reponse_mock(204, {}),
            ) as mock_delete,
        ):
            at.run()
            # 1er clic : demande de confirmation ; 2e clic : confirmation.
            at.button(key=f"supprimer_{cle_agri}").click().run()
            at.button(key=f"confirme_oui_{cle_agri}").click().run()

        assert mock_delete.called
        assert not at.exception


# --- app.py : navigation masquée par rôle ------------------------------------


@contextmanager
def _capturer_navigation():
    """Espionne st.navigation pour récupérer la liste de pages réellement produite
    par app.py, tout en laissant la navigation fonctionner normalement."""
    import streamlit as st

    navigation_reelle = st.navigation
    captures: list = []

    def espion(pages, *args, **kwargs):
        captures.append(pages)
        return navigation_reelle(pages, *args, **kwargs)

    with patch.object(st, "navigation", side_effect=espion):
        yield captures


def _titres_de_navigation(captures: list) -> list[str]:
    """Extrait les titres des st.Page passés à st.navigation (dict par section)."""
    titres: list[str] = []
    for pages in captures:
        sections = pages.values() if isinstance(pages, dict) else [pages]
        for liste in sections:
            titres.extend(page.title for page in liste)
    return titres


class TestNavigationParRole:
    """La liste de pages construite par app.py (lignes du bloc role == 'admin')
    doit masquer les pages d'administration aux non-admins."""

    def test_agriculteur_sans_pages_admin(self):
        """Pour un agriculteur, ni « Tableau de bord » ni « Créer un membre » ne
        doivent figurer dans la navigation ; l'analyse et l'historique, oui."""
        at = _app_connectee("agriculteur")
        with _capturer_navigation() as captures:
            at.run()

        titres = _titres_de_navigation(captures)
        assert titres, "st.navigation aurait dû être appelée par app.py"
        assert "Tableau de bord" not in titres
        assert "Créer un membre" not in titres
        assert "Analyse" in titres
        assert "Historique" in titres

    def test_admin_avec_pages_admin(self):
        """Pour un admin, les pages d'administration sont bien ajoutées (couvre le
        bloc `if role_actuel == 'admin'` d'app.py)."""
        at = _app_connectee("admin")
        with _capturer_navigation() as captures:
            at.run()

        titres = _titres_de_navigation(captures)
        assert "Tableau de bord" in titres
        assert "Créer un membre" in titres


# --- pages/predict.py : icônes Material dans le HTML injecté ------------------


def _blocs_html(at: AppTest) -> list[str]:
    """Retourne les sorties st.markdown contenant du HTML brut (balises)."""
    return [m.value for m in at.markdown if "<" in m.value and ">" in m.value]


class TestPredictIconesMaterial:
    """Les bandeaux résultat de predict.py sont injectés en HTML brut
    (unsafe_allow_html) : une directive `:material/...:` y resterait affichée en
    texte au lieu d'être rendue en icône. On vérifie qu'aucune ne subsiste."""

    def test_bandeau_sain_sans_directive_material_dans_le_html(self):
        at = _app_connectee("agriculteur")
        at.session_state["dernier_resultat"] = {
            "classe": "Tomato_healthy",
            "confiance": 0.95,
            "message": "Tomate saine — aucune maladie détectée.",
        }
        at.switch_page("pages/predict.py")
        at.run()

        blocs = _blocs_html(at)
        assert blocs, "le bandeau HTML du résultat aurait dû être rendu"
        for bloc in blocs:
            assert ":material/" not in bloc

    def test_bandeau_maladie_sans_directive_material_dans_le_html(self):
        at = _app_connectee("agriculteur")
        at.session_state["dernier_resultat"] = {
            "classe": "Tomato_Late_blight",
            "confiance": 0.80,
            "message": "Maladie détectée : Late blight (confiance : 80.0%)",
        }
        at.switch_page("pages/predict.py")
        at.run()

        blocs = _blocs_html(at)
        assert blocs, "le bandeau HTML du résultat aurait dû être rendu"
        for bloc in blocs:
            assert ":material/" not in bloc


# --- pages/predict.py : compression d'image éco-conception -------------------


def _image_jpeg_bruit(largeur: int, hauteur: int) -> bytes:
    """Génère un JPEG de bruit aléatoire aux dimensions données. Le bruit ne se
    compresse quasiment pas : l'image d'origine est donc volumineuse, ce qui rend
    l'effet du redimensionnement mesurable (contrairement à un aplat de couleur)."""
    image = Image.frombytes(
        "RGB", (largeur, hauteur), os.urandom(largeur * hauteur * 3)
    )
    tampon = io.BytesIO()
    image.save(tampon, format="JPEG", quality=95)
    return tampon.getvalue()


class TestPredictCompression:
    """L'image est redimensionnée/recompressée côté client avant l'envoi réseau
    (éco-conception C17) : on vérifie que les octets réellement transmis à l'API
    sont plus légers, bornés à 1024 px de côté, et restent un JPEG décodable."""

    def test_grande_image_est_compressee_avant_envoi(self):
        at = _app_connectee("agriculteur")
        at.switch_page("pages/predict.py")
        at.run()

        image_originale = _image_jpeg_bruit(2000, 1500)
        at.file_uploader[0].upload("grande.jpg", image_originale, "image/jpeg").run()

        reponse_ok = _reponse_mock(
            200,
            {"classe": "Tomato_healthy", "confiance": 0.91, "message": "ok"},
        )
        with patch(
            "tomatoscan.front.utils.api_client.requests.post", return_value=reponse_ok
        ) as mock_post:
            at.button[0].click().run()

        assert not at.exception
        assert mock_post.called
        # Octets réellement transmis dans le champ multipart "fichier".
        _, octets_envoyes, mime = mock_post.call_args.kwargs["files"]["fichier"]
        assert len(octets_envoyes) < len(image_originale)
        assert mime == "image/jpeg"
        image_envoyee = Image.open(io.BytesIO(octets_envoyes))
        assert max(image_envoyee.size) <= 1024
