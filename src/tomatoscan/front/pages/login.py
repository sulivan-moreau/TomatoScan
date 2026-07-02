"""Page de connexion TomatoScan — authentification JWT via l'API.

Gère le formulaire de connexion, l'appel POST /auth/token,
et le stockage du token JWT en session Streamlit.
"""

import streamlit as st

from utils import api_client
from utils.api_client import ApiError


def page_connexion() -> None:
    """Affiche le formulaire de connexion et gère l'authentification JWT.

    En cas de succès, stocke le token et le nom d'utilisateur en session
    puis redirige vers la navigation principale via st.rerun().
    En cas d'échec (401, réseau), affiche un message d'erreur lisible.
    """
    _, centre, _ = st.columns([1, 1.1, 1])
    with centre:
        st.markdown("### 🍅 TomatoScan")
        st.title("Connexion")
        st.caption("Accédez à votre espace d'analyse des maladies de la tomate.")

        # Message affiché uniquement si la session a expiré (flag posé par main())
        if st.session_state.pop("session_expiree", False):
            st.warning("Session expirée, veuillez vous reconnecter.")

        with st.form("login_form"):
            nom_utilisateur = st.text_input(
                "Nom d'utilisateur", placeholder="agriculteur01"
            )
            mot_de_passe = st.text_input(
                "Mot de passe", type="password", placeholder="••••••••"
            )
            soumis = st.form_submit_button("Se connecter", use_container_width=True)

        if soumis:
            # Validation basique des champs vides avant d'appeler l'API
            if not nom_utilisateur or not mot_de_passe:
                st.error(
                    "Veuillez renseigner votre nom d'utilisateur et votre mot de passe."
                )
                return
            try:
                # Spinner pendant l'appel réseau pour indiquer la progression
                with st.spinner("Connexion en cours…"):
                    token = api_client.login(nom_utilisateur, mot_de_passe)
                st.session_state.token = token
                st.session_state.username = nom_utilisateur
                # Redirection vers la navigation principale
                st.rerun()
            except ApiError as erreur:
                st.error(str(erreur))

        st.caption("Mot de passe oublié ? Contactez votre administrateur.")
