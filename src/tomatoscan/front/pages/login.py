"""Page de connexion TomatoScan — authentification JWT via l'API.

Gère le formulaire de connexion, l'appel POST /auth/token,
et le stockage du token JWT en session Streamlit.

Enregistrée par chemin de fichier (comme toutes les autres pages) plutôt que
par fonction, pour que st.page_link() puisse y pointer depuis pages/accueil.py —
la logique du formulaire elle-même est inchangée, seule la structure (fonction
→ script de niveau module) a changé.

Refonte visuelle (issue #33 suite) : formulaire dans une carte
st.container(key="login_card") stylée en CSS scoped — logique d'auth
inchangée. Le logo garde l'emoji 🍅 (identité de marque) plutôt que
l'icône Material Symbols proposée en maquette : Material Symbols n'a
pas d'équivalent "tomate", et le favicon/logo utilisent déjà cet emoji
ailleurs dans le projet.
"""

import streamlit as st

from utils import api_client
from utils.api_client import ApiError

_, centre, _ = st.columns([1, 1.1, 1])
with centre:
    with st.container(key="login_card"):
        st.markdown("### 🍅 TomatoScan")
        st.title("Connexion")
        st.caption("Accédez à votre espace d'analyse des maladies de la tomate.")

        with st.form("login_form"):
            nom_utilisateur = st.text_input(
                "Nom d'utilisateur", placeholder="agriculteur01"
            )
            mot_de_passe = st.text_input(
                "Mot de passe", type="password", placeholder="••••••••"
            )
            soumis = st.form_submit_button(
                "Se connecter", icon=":material/login:", use_container_width=True
            )

        if soumis:
            # Validation basique des champs vides avant d'appeler l'API
            if not nom_utilisateur or not mot_de_passe:
                st.error(
                    "Veuillez renseigner votre nom d'utilisateur et votre mot de passe."
                )
            else:
                try:
                    # Spinner pendant l'appel réseau pour indiquer la progression
                    with st.spinner("Connexion en cours…"):
                        token = api_client.login(nom_utilisateur, mot_de_passe)
                    st.session_state.token = token
                    st.session_state.username = nom_utilisateur
                    # Le rôle n'est jamais stocké séparément : il est recalculé à
                    # la demande depuis le token (api_client.obtenir_role), pour
                    # qu'il ne puisse structurellement pas se désynchroniser du token.
                    # Redirection vers la navigation principale
                    st.rerun()
                except ApiError as erreur:
                    st.error(str(erreur))

        st.caption("Mot de passe oublié ? Contactez votre administrateur.")

st.markdown(
    """<style>
    .st-key-login_card { background:#ffffff; border:1px solid #e8f1ea; border-radius:16px; padding:2.2rem 2.1rem; }
    .st-key-login_card button[kind="formSubmit"] { background:#2d6a4f; color:#ffffff; border:none; }
    .st-key-login_card button[kind="formSubmit"]:hover { background:#1b4332; }
    </style>""",
    unsafe_allow_html=True,
)
