"""Tests d'intégration frontend ↔ API (compétence C10).

Périmètre : src/tomatoscan/front/utils/api_client.py — le client HTTP utilisé par
les pages Streamlit pour appeler l'API FastAPI. Un test nominal par fonction/
endpoint, plus le cas d'erreur explicitement attendu (401 sur les endpoints
protégés) — pas de variantes multiples d'un même scénario.

Stratégie de mock : tous les appels réseau sont interceptés via
unittest.mock.patch("tomatoscan.front.utils.api_client.requests.*") — jamais de
vrai serveur API, jamais de vrai réseau.
"""

import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from tomatoscan.front.utils.api_client import (
    ApiError,
    API_URL,
    _decoder_payload_token,
    create_user,
    delete_user,
    get_confusion_matrix,
    get_evaluation,
    get_history,
    get_reports,
    is_token_valid,
    list_users,
    login,
    me,
    predict,
    refresh_token,
    renouveler_si_necessaire,
)


def _reponse_mock(
    status_code: int, corps_json: dict, ok: bool | None = None
) -> MagicMock:
    """Construit un faux requests.Response — .ok suit status_code si non précisé,
    comme le fait le vrai objet requests.Response (ok = status_code < 400)."""
    reponse = MagicMock()
    reponse.status_code = status_code
    reponse.ok = ok if ok is not None else status_code < 400
    reponse.json.return_value = corps_json
    return reponse


def _fabriquer_jwt(payload: dict) -> str:
    """Construit un vrai JWT via PyJWT — la clé de signature n'a pas d'importance
    ici, _decoder_payload_token ne la vérifie jamais (verify_signature=False)."""
    return jwt.encode(payload, "cle-de-signature-sans-importance", algorithm="HS256")


class TestLogin:
    """POST /auth/token."""

    @patch("tomatoscan.front.utils.api_client.requests.post")
    def test_login_extrait_le_token_et_envoie_les_bons_identifiants(self, mock_post):
        mock_post.return_value = _reponse_mock(
            200, {"access_token": "faux.jwt.token", "token_type": "bearer"}
        )

        token = login("agriculteur01", "secret")

        assert token == "faux.jwt.token"
        args, kwargs = mock_post.call_args
        assert args[0] == f"{API_URL}/auth/token"
        assert kwargs["json"] == {"username": "agriculteur01", "password": "secret"}

    @patch("tomatoscan.front.utils.api_client.requests.post")
    def test_login_identifiants_invalides_leve_apierror_401(self, mock_post):
        mock_post.return_value = _reponse_mock(
            401, {"detail": "Identifiants invalides"}
        )

        with pytest.raises(ApiError) as erreur:
            login("admin", "mauvais_mot_de_passe")

        assert erreur.value.status_code == 401


class TestSessionCourante:
    """GET /auth/me."""

    @patch("tomatoscan.front.utils.api_client.requests.get")
    def test_me_retourne_la_session_avec_le_bon_header(self, mock_get):
        mock_get.return_value = _reponse_mock(
            200, {"username": "admin_test", "role": "admin"}
        )

        session_courante = me("mon.token.valide")

        assert session_courante == {"username": "admin_test", "role": "admin"}
        args, kwargs = mock_get.call_args
        assert args[0] == f"{API_URL}/auth/me"
        assert kwargs["headers"] == {"Authorization": "Bearer mon.token.valide"}


class TestListUsers:
    """GET /users (admin uniquement)."""

    @patch("tomatoscan.front.utils.api_client.requests.get")
    def test_list_users_retourne_la_liste_et_le_bon_header(self, mock_get):
        mock_get.return_value = _reponse_mock(
            200, [{"id": "1", "username": "agri01", "role": "agriculteur"}]
        )

        utilisateurs = list_users("mon.token.admin")

        assert utilisateurs == [
            {"id": "1", "username": "agri01", "role": "agriculteur"}
        ]
        args, kwargs = mock_get.call_args
        assert args[0] == f"{API_URL}/users"
        assert kwargs["headers"] == {"Authorization": "Bearer mon.token.admin"}


class TestCreateUser:
    """POST /users (admin uniquement)."""

    @patch("tomatoscan.front.utils.api_client.requests.post")
    def test_create_user_envoie_les_bons_identifiants(self, mock_post):
        mock_post.return_value = _reponse_mock(
            201, {"id": "2", "username": "agri02", "role": "agriculteur"}
        )

        utilisateur = create_user("agri02", "motdepasse123", "mon.token.admin")

        assert utilisateur["username"] == "agri02"
        args, kwargs = mock_post.call_args
        assert args[0] == f"{API_URL}/users"
        assert kwargs["json"] == {"username": "agri02", "password": "motdepasse123"}


class TestDeleteUser:
    """DELETE /users/{id} (admin uniquement)."""

    @patch("tomatoscan.front.utils.api_client.requests.delete")
    def test_delete_user_appelle_le_bon_endpoint(self, mock_delete):
        mock_delete.return_value = _reponse_mock(204, {})

        delete_user("id-utilisateur-123", "mon.token.admin")

        args, kwargs = mock_delete.call_args
        assert args[0] == f"{API_URL}/users/id-utilisateur-123"
        assert kwargs["headers"] == {"Authorization": "Bearer mon.token.admin"}


class TestGetHistory:
    """GET /predictions/history."""

    @patch("tomatoscan.front.utils.api_client.requests.get")
    def test_get_history_retourne_la_liste_des_predictions(self, mock_get):
        mock_get.return_value = _reponse_mock(
            200, [{"id": "1", "classe_predite": "Tomato_healthy", "confiance": 0.95}]
        )

        historique = get_history("mon.token.valide")

        assert len(historique) == 1
        assert historique[0]["classe_predite"] == "Tomato_healthy"
        args, kwargs = mock_get.call_args
        assert args[0] == f"{API_URL}/predictions/history"


class TestGetReports:
    """GET /reports."""

    @patch("tomatoscan.front.utils.api_client.requests.get")
    def test_get_reports_retourne_le_rapport_d_entrainement(self, mock_get):
        mock_get.return_value = _reponse_mock(
            200, {"fichier": "historique.csv", "meilleure_val_accuracy": 0.935}
        )

        rapport = get_reports("mon.token.valide")

        assert rapport["meilleure_val_accuracy"] == 0.935
        args, kwargs = mock_get.call_args
        assert args[0] == f"{API_URL}/reports"


class TestGetEvaluation:
    """GET /reports/evaluation."""

    @patch("tomatoscan.front.utils.api_client.requests.get")
    def test_get_evaluation_retourne_le_rapport(self, mock_get):
        mock_get.return_value = _reponse_mock(
            200, {"accuracy_test": 0.9355, "meilleure_accuracy_validation": 0.9455}
        )

        evaluation = get_evaluation("mon.token.valide")

        assert evaluation["accuracy_test"] == 0.9355
        args, kwargs = mock_get.call_args
        assert args[0] == f"{API_URL}/reports/evaluation"


class TestGetConfusionMatrix:
    """GET /reports/confusion-matrix."""

    @patch("tomatoscan.front.utils.api_client.requests.get")
    def test_get_confusion_matrix_retourne_les_octets_de_l_image(self, mock_get):
        reponse = _reponse_mock(200, {})
        reponse.content = b"\x89PNG\r\n\x1a\nfaux-contenu"
        mock_get.return_value = reponse

        image = get_confusion_matrix("mon.token.valide")

        assert image == b"\x89PNG\r\n\x1a\nfaux-contenu"
        args, kwargs = mock_get.call_args
        assert args[0] == f"{API_URL}/reports/confusion-matrix"


class TestPredict:
    """POST /predict — requête bien formée et réponse interprétée dans le format
    exact attendu par pages/predict.py (resultat["classe"/"confiance"/"message"])."""

    @patch("tomatoscan.front.utils.api_client.requests.post")
    def test_predict_envoie_le_fichier_et_retourne_le_format_attendu(self, mock_post):
        mock_post.return_value = _reponse_mock(
            200,
            {
                "classe": "Tomato_Early_blight",
                "confiance": 0.8734,
                "message": "Maladie détectée : Early blight (confiance : 87.3%)",
            },
        )

        resultat = predict(b"contenu_image_factice", "feuille.jpg", "mon.token.valide")

        assert resultat == {
            "classe": "Tomato_Early_blight",
            "confiance": 0.8734,
            "message": "Maladie détectée : Early blight (confiance : 87.3%)",
        }
        _, kwargs = mock_post.call_args
        assert kwargs["headers"] == {"Authorization": "Bearer mon.token.valide"}
        # L'API FastAPI attend le champ multipart nommé "fichier" (predict.py)
        nom_fichier_envoye, octets_envoyes, type_contenu = kwargs["files"]["fichier"]
        assert nom_fichier_envoye == "feuille.jpg"
        assert octets_envoyes == b"contenu_image_factice"
        assert type_contenu == "image/jpeg"

    @patch("tomatoscan.front.utils.api_client.requests.post")
    def test_predict_401_leve_apierror_avec_le_detail_de_l_api(self, mock_post):
        mock_post.return_value = _reponse_mock(
            401, {"detail": "Token invalide ou expiré"}
        )

        with pytest.raises(ApiError) as erreur:
            predict(b"contenu_image_factice", "feuille.jpg", "token.expire")

        assert erreur.value.status_code == 401
        assert "Token invalide ou expiré" in str(erreur.value)

    @patch("tomatoscan.front.utils.api_client.requests.post")
    def test_predict_erreur_reseau_leve_aussi_apierror(self, mock_post):
        """Une erreur réseau (pas de réponse HTTP du tout) doit aussi être
        transformée en ApiError exploitable, pas remonter comme exception brute."""
        import requests

        mock_post.side_effect = requests.ConnectionError("connexion refusée")

        with pytest.raises(ApiError) as erreur:
            predict(b"contenu_image_factice", "feuille.jpg", "un.token")

        assert erreur.value.status_code is None


class TestRenouvellementToken:
    """POST /auth/refresh — renouvellement proactif du token avant expiration."""

    @patch("tomatoscan.front.utils.api_client.requests.post")
    def test_refresh_token_retourne_le_nouveau_token(self, mock_post):
        mock_post.return_value = _reponse_mock(
            200, {"access_token": "nouveau.jwt.token", "token_type": "bearer"}
        )

        nouveau_token = refresh_token("ancien.jwt.token")

        assert nouveau_token == "nouveau.jwt.token"
        args, kwargs = mock_post.call_args
        assert args[0] == f"{API_URL}/auth/refresh"
        assert kwargs["headers"] == {"Authorization": "Bearer ancien.jwt.token"}

    @patch("tomatoscan.front.utils.api_client.requests.post")
    def test_renouveler_si_necessaire_selon_le_temps_restant(self, mock_post):
        """Les 3 branches de décision explicitement attendues : loin de
        l'expiration → rien ; proche → refresh déclenché ; déjà expiré → rien
        (gerer_erreur_401 prend le relais au prochain appel API)."""
        mock_post.return_value = _reponse_mock(
            200, {"access_token": "nouveau.jwt.token", "token_type": "bearer"}
        )

        token_loin = _fabriquer_jwt(
            {"sub": "admin", "role": "admin", "exp": int(time.time()) + 3600}
        )
        assert renouveler_si_necessaire(token_loin) == token_loin
        mock_post.assert_not_called()

        token_proche = _fabriquer_jwt(
            {"sub": "admin", "role": "admin", "exp": int(time.time()) + 30}
        )
        assert renouveler_si_necessaire(token_proche) == "nouveau.jwt.token"
        mock_post.assert_called_once()

        mock_post.reset_mock()
        token_expire = _fabriquer_jwt({"sub": "admin", "role": "admin", "exp": 1})
        assert renouveler_si_necessaire(token_expire) == token_expire
        mock_post.assert_not_called()


class TestDecodageJWT:
    """Décodage du payload JWT via PyJWT (utilisé par is_token_valid())."""

    def test_decode_et_expiration(self):
        payload = {"sub": "admin", "role": "admin", "exp": 9_999_999_999}
        token = _fabriquer_jwt(payload)

        assert _decoder_payload_token(token) == payload
        assert is_token_valid(token) is True
        assert is_token_valid(_fabriquer_jwt({**payload, "exp": 1})) is False
