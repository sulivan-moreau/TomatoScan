"""Test de régression du décodage JWT base64url (compétence C21).

Verrouille la correction de l'incident de préproduction documenté dans
docs/incidents.md § « Rôle admin dégradé — décodage JWT base64 vs base64url »
(commit da4f786, PR #84, branche fix/role-login-decodage).

Le bug : `_decoder_payload_token` décodait la payload JWT avec `base64.b64decode`
(alphabet standard `+/`) au lieu de `base64.urlsafe_b64decode` (alphabet base64url
`-_` imposé par la RFC 7519). Quand la payload encodée contenait `-` ou `_`,
`base64.b64decode` (validate=False) écartait silencieusement ces caractères et
corrompait le décodage : le token levait une exception, `is_token_valid` le
jugeait invalide et `obtenir_role` (fonction de l'époque) retombait sur le rôle
par défaut « agriculteur » — un compte admin se retrouvait donc dégradé.

Pourquoi ce fichier plutôt que le test existant : dans test_api_client.py, le
test de décodage utilise une payload purement alphanumérique, dont l'encodage ne
contient jamais `-`/`_` — il passerait MÊME avec le bug. On force ici une payload
dont l'encodage base64url contient `-` ET `_`, seul cas qui reproduit la panne.

Stratégie : on invoque la VRAIE fonction du projet (`_decoder_payload_token`,
aujourd'hui déléguée à PyJWT, qui gère nativement base64url), jamais une
réimplémentation du décodage. Un test dédié rejoue en local l'ancien décodage
bugué (base64 standard) pour prouver que la payload choisie déclenche bien la
régression — sans modifier api_client.py.
"""

import base64
import json

import jwt
import pytest
from tomatoscan.front.utils.api_client import _decoder_payload_token, is_token_valid

# Payload dont l'encodage base64url contient à la fois `-` et `_` (vérifié par le
# test garde-fou ci-dessous). Le `sub` contient `~` (0x7E) et `?` (0x3F), les seuls
# caractères ASCII imprimables portant six bits à 1 consécutifs — condition
# nécessaire pour qu'un groupe de 6 bits vaille 62 (`-`) ou 63 (`_`) en base64url.
# Un username purement alphanumérique ne peut jamais produire ces caractères : d'où
# le caractère « intermittent » du symptôme, qui ne touchait que certains tokens.
PAYLOAD_DECLENCHEUR = {"sub": "~ferme?", "role": "admin", "exp": 9_999_999_999}


def _forger_jwt(payload: dict) -> str:
    """Construit un vrai JWT via PyJWT — la clé de signature est sans importance,
    _decoder_payload_token ne vérifie jamais la signature (verify_signature=False).

    Aligné sur le helper _fabriquer_jwt de tests/test_frontend/test_api_client.py.
    """
    return jwt.encode(payload, "cle-de-signature-sans-importance", algorithm="HS256")


def _decoder_a_l_ancienne_base64_standard(token: str) -> dict:
    """Rejoue le décodage BUGUÉ d'avant da4f786 (base64 standard, alphabet `+/`).

    Copie locale volontaire de l'ancien code, uniquement pour prouver que la
    payload de test déclenche la régression. N'appelle PAS le code du projet et ne
    le modifie pas — le projet, lui, décode via _decoder_payload_token (PyJWT).
    """
    partie_payload = token.split(".")[1]
    partie_payload += "=" * (4 - len(partie_payload) % 4)
    return json.loads(base64.b64decode(partie_payload))


class TestRegressionDecodageBase64Url:
    """Verrou de non-régression sur le décodage JWT base64url (incident da4f786)."""

    def test_la_payload_de_test_contient_bien_un_caractere_base64url(self):
        """Garde-fou : sans caractère `-`/`_` dans l'encodage, le test ne
        reproduirait rien et passerait à tort même avec le bug présent. On vérifie
        donc que la payload choisie produit réellement ces deux caractères."""
        segment_payload = _forger_jwt(PAYLOAD_DECLENCHEUR).split(".")[1]

        assert "-" in segment_payload
        assert "_" in segment_payload

    def test_la_vraie_fonction_decode_une_payload_base64url(self):
        """Régression principale : la fonction réellement utilisée par le front
        (_decoder_payload_token) doit décoder sans erreur une payload contenant
        `-`/`_` et retrouver exactement les claims — dont role=admin."""
        token = _forger_jwt(PAYLOAD_DECLENCHEUR)

        payload_decode = _decoder_payload_token(token)

        assert payload_decode == PAYLOAD_DECLENCHEUR
        assert payload_decode["role"] == "admin"

    def test_is_token_valid_reste_vrai_sur_une_payload_base64url(self):
        """is_token_valid s'appuie sur _decoder_payload_token : un token valide
        dont la payload contient `-`/`_` ne doit pas être jugé invalide, sinon
        l'admin serait déconnecté au lieu d'être reconnu."""
        token = _forger_jwt(PAYLOAD_DECLENCHEUR)

        assert is_token_valid(token) is True

    def test_l_ancien_decodage_base64_standard_echouait_sur_cette_payload(self):
        """Preuve que le test détecte vraiment la régression : l'ancien décodage
        (base64 standard) échoue sur cette même payload, là où urlsafe_b64decode —
        le correctif de da4f786 — réussit. Confirme que la payload déclenche bien
        le bug et que le code corrigé y est immunisé (sans toucher api_client.py)."""
        token = _forger_jwt(PAYLOAD_DECLENCHEUR)

        # Ancien code (base64 standard) : écarte `-`/`_` → décodage corrompu.
        with pytest.raises(Exception):
            _decoder_a_l_ancienne_base64_standard(token)

        # Correctif da4f786 (base64url) : décode correctement la même payload.
        segment = token.split(".")[1]
        segment += "=" * (4 - len(segment) % 4)
        payload_urlsafe = json.loads(base64.urlsafe_b64decode(segment))
        assert payload_urlsafe == PAYLOAD_DECLENCHEUR

    def test_une_payload_alphanumerique_reste_decodable(self):
        """Non-régression du cas courant : une payload sans `-`/`_` (username
        alphanumérique) doit toujours se décoder — le correctif ne casse pas le
        cas nominal, très majoritaire en production."""
        payload = {"sub": "agri01", "role": "agriculteur", "exp": 9_999_999_999}
        token = _forger_jwt(payload)
        segment = token.split(".")[1]

        assert "-" not in segment and "_" not in segment
        assert _decoder_payload_token(token) == payload
