"""Tests d'intégration frontend ↔ API (issue #14, compétence C10).

Périmètre : src/tomatoscan/front/utils/api_client.py — le client HTTP utilisé par
les pages Streamlit pour appeler l'API FastAPI. Distinct de tests/test_api/ (qui
teste l'API côté serveur, avec un vrai TestClient FastAPI) et de tests/test_model/
(qui teste le modèle ML). Ici on teste uniquement le CLIENT : est-ce qu'il construit
les bonnes requêtes, et interprète-t-il correctement les réponses (succès et erreur) ?

Stratégie de mock : tous les appels réseau sont interceptés via
unittest.mock.patch("tomatoscan.front.utils.api_client.requests.post") — jamais de
vrai serveur API en cours d'exécution, jamais de vrai réseau. Chaque test construit
un objet Mock qui simule exactement une réponse `requests.Response` (attributs
`status_code`, `ok`, méthode `.json()`) telle que l'API la produirait, puis vérifie
à la fois (a) la requête envoyée par api_client (URL, headers, payload) et (b) la
valeur retournée ou l'exception levée.

Les 4 tâches de l'issue #14 sont couvertes par les classes de tests ci-dessous :
- TestLogin           → tâche 1 (login → récupération du token)
- TestPredictSucces   → tâches 2 et 4 (POST /predict avec token valide + format
                         de réponse attendu par pages/predict.py)
- TestPredictErreur   → tâche 3 (POST /predict avec token expiré → 401)
"""

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from tomatoscan.front.utils.api_client import (
    ApiError,
    API_URL,
    _decoder_payload_token,
    is_token_valid,
    login,
    obtenir_role,
    predict,
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


# --- Tâche 1 : login → récupération du token ---------------------------------------


class TestLogin:
    """POST /auth/token — extraction du token depuis une réponse 200 mockée."""

    @patch("tomatoscan.front.utils.api_client.requests.post")
    def test_login_extrait_bien_le_token_de_la_reponse_200(self, mock_post):
        mock_post.return_value = _reponse_mock(
            200, {"access_token": "faux.jwt.token", "token_type": "bearer"}
        )

        token = login("admin", "motdepasse123")

        assert token == "faux.jwt.token"

    @patch("tomatoscan.front.utils.api_client.requests.post")
    def test_login_envoie_bien_les_identifiants_au_bon_endpoint(self, mock_post):
        mock_post.return_value = _reponse_mock(
            200, {"access_token": "peu.importe", "token_type": "bearer"}
        )

        login("agriculteur01", "secret")

        mock_post.assert_called_once()
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

    @patch("tomatoscan.front.utils.api_client.requests.post")
    def test_login_reponse_sans_token_leve_apierror(self, mock_post):
        """Réponse 200 mais sans access_token dans le corps — cas limite mais réel
        (API mal configurée, proxy qui tronque la réponse...). Ne doit pas planter
        avec un KeyError, doit lever une ApiError explicite."""
        mock_post.return_value = _reponse_mock(200, {"token_type": "bearer"})

        with pytest.raises(ApiError):
            login("admin", "motdepasse123")


# --- Tâches 2 et 4 : POST /predict avec token valide + format de réponse -----------


class TestPredictSucces:
    """POST /predict — requête bien formée avec token valide, et réponse bien
    interprétée dans le format exact attendu par pages/predict.py."""

    @patch("tomatoscan.front.utils.api_client.requests.post")
    def test_predict_envoie_le_header_authorization_correct(self, mock_post):
        mock_post.return_value = _reponse_mock(
            200,
            {"classe": "Tomato_healthy", "confiance": 0.97, "message": "Tomate saine."},
        )

        predict(
            b"\xff\xd8\xff\xe0contenu_image_factice", "feuille.jpg", "mon.token.valide"
        )

        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["headers"] == {"Authorization": "Bearer mon.token.valide"}

    @patch("tomatoscan.front.utils.api_client.requests.post")
    def test_predict_envoie_le_fichier_dans_le_bon_champ_multipart(self, mock_post):
        """L'API FastAPI attend le champ multipart nommé "fichier" (predict.py
        côté API) — vérifie que le client l'envoie sous ce nom exact."""
        mock_post.return_value = _reponse_mock(
            200,
            {"classe": "Tomato_healthy", "confiance": 0.97, "message": "Tomate saine."},
        )

        predict(b"contenu_image_factice", "feuille.jpg", "mon.token.valide")

        _, kwargs = mock_post.call_args
        assert "fichier" in kwargs["files"]
        nom_fichier_envoye, octets_envoyes, type_contenu = kwargs["files"]["fichier"]
        assert nom_fichier_envoye == "feuille.jpg"
        assert octets_envoyes == b"contenu_image_factice"
        assert type_contenu == "image/jpeg"

    @patch("tomatoscan.front.utils.api_client.requests.post")
    def test_predict_reponse_200_retourne_le_format_attendu_par_la_page(
        self, mock_post
    ):
        """pages/predict.py lit resultat.get("classe"), resultat.get("confiance", 0),
        resultat.get("message") (predict.py:80-82,114) — vérifie que predict()
        retourne bien un dict avec exactement ces 3 clés et les bonnes valeurs."""
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
        # Les 3 lectures exactes que fait pages/predict.py doivent fonctionner
        assert resultat.get("classe") == "Tomato_Early_blight"
        assert resultat.get("confiance", 0) == 0.8734
        assert resultat.get("message")

    @patch("tomatoscan.front.utils.api_client.requests.post")
    def test_predict_reponse_tomate_saine_est_distinguee_par_la_page(self, mock_post):
        """pages/predict.py:86 branche sur `classe == "Tomato_healthy"` pour afficher
        le bandeau vert plutôt que le bandeau maladie — vérifie que cette valeur
        transite intacte depuis la réponse API jusqu'au dict retourné par predict()."""
        mock_post.return_value = _reponse_mock(
            200,
            {
                "classe": "Tomato_healthy",
                "confiance": 0.995,
                "message": "Tomate saine.",
            },
        )

        resultat = predict(b"contenu_image_factice", "feuille.jpg", "mon.token.valide")

        assert resultat["classe"] == "Tomato_healthy"

    def test_calcul_pourcentage_confiance_logique_de_predict_py(self):
        """pages/predict.py:81-84 est un script Streamlit (pas une fonction
        importable) — la logique de conversion confiance→pourcentage ne peut donc
        pas être testée en l'important directement. Reproduite ici à l'identique
        (copiée depuis predict.py) pour vérifier son comportement sur des valeurs
        connues, comme demandé par l'issue quand tester l'affichage réel n'est pas
        possible sans navigateur. Si predict.py change cette logique, ce test devra
        être mis à jour en conséquence — il ne l'importe pas, il la duplique."""

        def _pourcentage_confiance(confiance):
            # Copié tel quel depuis pages/predict.py:81-84
            confiance = confiance or 0
            pourcent = confiance * 100 if confiance <= 1 else confiance
            return max(0.0, min(pourcent, 100.0))

        assert _pourcentage_confiance(0.973) == pytest.approx(97.3)
        assert _pourcentage_confiance(0.0) == 0.0
        assert _pourcentage_confiance(None) == 0.0
        assert _pourcentage_confiance(1.0) == 100.0
        # Cas déjà en pourcentage (confiance > 1) — clampé à 100 max
        assert _pourcentage_confiance(150.0) == 100.0


# --- Tâche 3 : POST /predict avec token expiré → 401 -------------------------------


class TestPredictErreur:
    """POST /predict — un token expiré/invalide doit produire une erreur claire,
    jamais un crash silencieux ni un retour de valeur ambiguë."""

    @patch("tomatoscan.front.utils.api_client.requests.post")
    def test_predict_401_leve_apierror_avec_le_bon_status_code(self, mock_post):
        mock_post.return_value = _reponse_mock(
            401, {"detail": "Token invalide ou expiré"}
        )

        with pytest.raises(ApiError) as erreur:
            predict(b"contenu_image_factice", "feuille.jpg", "token.expire")

        assert erreur.value.status_code == 401

    @patch("tomatoscan.front.utils.api_client.requests.post")
    def test_predict_401_le_message_d_erreur_reprend_le_detail_de_l_api(
        self, mock_post
    ):
        """Le message de l'exception doit être exploitable par la page Streamlit
        (pages/predict.py catch ApiError et distingue le cas 401 pour rediriger),
        pas un message générique qui masquerait la vraie cause."""
        mock_post.return_value = _reponse_mock(
            401, {"detail": "Token invalide ou expiré"}
        )

        with pytest.raises(ApiError) as erreur:
            predict(b"contenu_image_factice", "feuille.jpg", "token.expire")

        assert "Token invalide ou expiré" in str(erreur.value)

    @patch("tomatoscan.front.utils.api_client.requests.post")
    def test_predict_401_ne_retourne_jamais_de_dict_ni_none(self, mock_post):
        """Vérifie explicitement l'absence de plantage silencieux : predict() ne
        doit jamais retourner None ou un dict vide en cas d'erreur — uniquement
        lever ApiError, pour forcer l'appelant (pages/predict.py) à la traiter."""
        mock_post.return_value = _reponse_mock(
            401, {"detail": "Token invalide ou expiré"}
        )

        try:
            resultat = predict(b"contenu_image_factice", "feuille.jpg", "token.expire")
            pytest.fail(
                f"predict() aurait dû lever ApiError, a retourné {resultat!r} à la place"
            )
        except ApiError:
            pass  # comportement attendu

    @patch("tomatoscan.front.utils.api_client.requests.post")
    def test_predict_erreur_reseau_leve_aussi_apierror(self, mock_post):
        """Complément : une erreur réseau (pas de réponse HTTP du tout) doit aussi
        être transformée en ApiError exploitable, pas en exception requests brute
        qui remonterait jusqu'à Streamlit sans message utilisateur adapté."""
        import requests

        mock_post.side_effect = requests.ConnectionError("connexion refusée")

        with pytest.raises(ApiError) as erreur:
            predict(b"contenu_image_factice", "feuille.jpg", "un.token")

        assert erreur.value.status_code is None


def _fabriquer_jwt(payload: dict) -> str:
    """Construit un faux JWT (header.payload.signature) pour les tests de décodage.

    Seule la partie payload est lue par _decoder_payload_token — header et
    signature n'ont pas besoin d'être valides cryptographiquement.
    """

    def _b64url(donnees: bytes) -> str:
        return base64.urlsafe_b64encode(donnees).rstrip(b"=").decode()

    entete = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    corps = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64url(b"signature-factice")
    return f"{entete}.{corps}.{signature}"


class TestDecodageJWTBase64Url:
    """Reproduction du bug base64 standard vs base64url (issue décodage JWT).

    Propriété non triviale utilisée pour construire le cas de test : un payload
    JSON purement alphanumérique (lettres/chiffres) ne peut JAMAIS produire de
    caractère '-' ou '_' en base64url — il faut au moins un octet dont le motif
    binaire génère un groupe de 6 bits valant 62 ou 63, ce qu'aucun caractère
    alphanumérique ASCII ne permet (bit de poids fort toujours à 0, séquences
    de 1 consécutifs trop courtes). D'où le choix d'un "sub" contenant des
    caractères spéciaux ci-dessous : c'est le cas réel qui déclenche le bug
    (un username alphanumérique classique, lui, ne le déclencherait jamais).
    """

    PAYLOAD_DECLENCHEUR = {
        "sub": "?9ck|EWrLzwS",
        "role": "admin",
        "exp": 9_999_999_999,
    }

    def test_le_payload_choisi_contient_bien_un_caractere_base64url_specifique(self):
        """Garde-fou : vérifie que le payload de test produit réellement un '-'
        ou un '_' en base64url (sans quoi le test ne reproduirait rien)."""
        corps = json.dumps(self.PAYLOAD_DECLENCHEUR, separators=(",", ":")).encode()
        b64url = base64.urlsafe_b64encode(corps).decode()
        assert "-" in b64url or "_" in b64url

    def test_base64_standard_echoue_sur_ce_payload(self):
        """Preuve du bug : le décodage avec l'alphabet standard (base64.b64decode),
        celui utilisé avant correction, échoue ou produit un résultat corrompu
        sur ce payload précis."""
        token = _fabriquer_jwt(self.PAYLOAD_DECLENCHEUR)
        partie_payload = token.split(".")[1]
        partie_payload += "=" * (4 - len(partie_payload) % 4)

        with pytest.raises(Exception):
            # base64.b64decode (validate=False) ignore silencieusement les
            # caractères hors alphabet standard ('-'/'_'), corrompant les
            # octets décodés — json.loads/UTF-8 échoue en aval.
            json.loads(base64.b64decode(partie_payload))

    def test_urlsafe_b64decode_decode_correctement_ce_meme_payload(self):
        """Le correctif (base64.urlsafe_b64decode, utilisé par
        _decoder_payload_token depuis la correction) doit décoder ce même
        payload sans erreur et retrouver les bonnes valeurs."""
        token = _fabriquer_jwt(self.PAYLOAD_DECLENCHEUR)

        decode = _decoder_payload_token(token)

        assert decode == self.PAYLOAD_DECLENCHEUR

    def test_obtenir_role_lit_le_bon_role_meme_avec_ce_payload_a_risque(self):
        """Test de bout en bout via la fonction publique réellement utilisée par
        pages/login.py : le rôle doit être lu correctement, pas retomber sur le
        défaut "agriculteur" à cause d'un échec de décodage masqué."""
        token = _fabriquer_jwt(self.PAYLOAD_DECLENCHEUR)

        assert obtenir_role(token) == "admin"

    def test_is_token_valid_lit_correctement_l_expiration_avec_ce_payload(self):
        """Même vérification pour is_token_valid() (exp très éloignée → valide)."""
        token = _fabriquer_jwt(self.PAYLOAD_DECLENCHEUR)

        assert is_token_valid(token) is True

    def test_obtenir_role_retombe_sur_le_defaut_si_le_token_est_vraiment_malforme(
        self,
    ):
        """Non-régression : un token réellement invalide (pas seulement un
        payload contenant '-'/'_') doit toujours retomber sur "agriculteur",
        sans lever d'exception jusqu'à la page appelante."""
        assert obtenir_role("token.invalide.non-base64") == "agriculteur"
