"""Point d'entrée de l'application Streamlit TomatoScan.

- Configuration de la page et thème CSS,
- Sidebar persistante (logo, état API, déconnexion),
- Vérification de la validité du token JWT à chaque re-run Streamlit,
- Routing conditionnel : non connecté → login, connecté → Analyse / Historique / Tableau de bord.

Lancement : `streamlit run src/tomatoscan/front/app.py`
"""

import streamlit as st

from pages.login import page_connexion
from utils import api_client

# Palette TomatoScan (réutilisée dans le CSS).
VERT = "#2d6a4f"
VERT_FONCE = "#1b4332"
ROUGE = "#c1121f"

st.set_page_config(
    page_title="TomatoScan",
    page_icon="🍅",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_css():
    """Injecte le style personnalisé via st.markdown (thème sobre desktop)."""
    st.markdown(
        f"""
        <style>
        /* Fond général */
        .stApp {{ background: #f6f8f6; }}

        /* Sidebar vert profond */
        section[data-testid="stSidebar"] {{ background: {VERT_FONCE}; }}
        section[data-testid="stSidebar"] * {{ color: #e8f1ea; }}
        .ts-logo {{
            display: flex; align-items: center; gap: 10px;
            font-size: 20px; font-weight: 700; color: #ffffff;
            padding: 6px 4px 16px 4px;
        }}
        .ts-dot {{
            width: 16px; height: 16px; border-radius: 50%;
            background: {ROUGE}; display: inline-block;
        }}

        /* Titres */
        h1, h2, h3 {{ color: #1b2420; letter-spacing: -0.01em; }}

        /* Boutons primaires */
        .stButton > button {{
            background: {VERT}; color: #ffffff; border: none;
            border-radius: 9px; padding: 0.55rem 1.1rem; font-weight: 600;
        }}
        .stButton > button:hover {{ background: {VERT_FONCE}; color: #fff; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# --- Page placeholder (Tableau de bord — issue dédiée) ----------------------


def page_dashboard():
    """Page Tableau de bord (placeholder)."""
    st.title("Tableau de bord")
    st.info("Tableau de bord à venir.")


def sidebar_header():
    """Affiche le logo, l'état de l'API et la déconnexion (si connecté)."""
    with st.sidebar:
        st.markdown(
            '<div class="ts-logo"><span class="ts-dot"></span>TomatoScan</div>',
            unsafe_allow_html=True,
        )
        # Indicateur d'état de l'API (utilise api_client.ping).
        if api_client.ping():
            st.caption("🟢 API connectée")
        else:
            st.caption("🔴 API injoignable")

        if st.session_state.get("token"):
            # Affiche le nom de l'utilisateur connecté
            st.caption(
                f"Connecté : **{st.session_state.get('username', 'utilisateur')}**"
            )
            if st.button("Déconnexion", use_container_width=True):
                # Vider toute la session (token + username) et rediriger vers login
                st.session_state.clear()
                st.rerun()


def main():
    """Point d'entrée principal — gère l'état de session et orchestre la navigation."""
    # Initialisation de l'état d'authentification au premier démarrage
    if "token" not in st.session_state:
        st.session_state.token = None

    inject_css()

    # Vérification du token JWT à chaque re-run : si expiré, vider la session
    token_actuel = st.session_state.get("token")
    if token_actuel and not api_client.is_token_valid(token_actuel):
        st.session_state.clear()
        st.session_state["session_expiree"] = True
        st.rerun()

    # Sidebar toujours visible : logo TomatoScan + état API + déconnexion si connecté
    sidebar_header()

    if st.session_state.get("token"):
        # Utilisateur connecté : navigation complète (Analyse / Historique / Tableau de bord)
        navigation = st.navigation(
            {
                "TomatoScan": [
                    st.Page(
                        "pages/predict.py",
                        title="Analyse",
                        icon=":material/biotech:",
                        default=True,
                    ),
                    st.Page(
                        "pages/history.py",
                        title="Historique",
                        icon=":material/history:",
                    ),
                    st.Page(
                        page_dashboard,
                        title="Tableau de bord",
                        icon=":material/bar_chart:",
                    ),
                ]
            }
        )
    else:
        # Non connecté : page de connexion seule, liens de navigation masqués dans la sidebar
        navigation = st.navigation(
            [st.Page(page_connexion, title="Connexion")],
            position="hidden",
        )

    navigation.run()


if __name__ == "__main__":
    main()
