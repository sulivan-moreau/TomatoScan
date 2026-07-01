"""Point d'entrée de l'application Streamlit TomatoScan.

Passe 1 — structure de base :
- configuration de la page,
- CSS personnalisé (thème vert / blanc / rouge tomate),
- sidebar avec logo + navigation,
- affichage conditionné par l'authentification :
    * non connecté  -> page de connexion uniquement,
    * connecté      -> Analyse / Historique / Tableau de bord.

Note : l'authentification réelle (JWT) et la page d'analyse sont des
placeholders à ce stade ; elles seront implémentées dans les passes 2 et 3.

Lancement : `streamlit run src/tomatoscan/front/app.py`
"""

import streamlit as st

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


# --- Pages (placeholders de la passe 1) -------------------------------------

def page_login():
    """Page de connexion (placeholder).

    L'authentification JWT sera branchée en passe 2. Pour l'instant, le
    bouton simule une connexion afin de tester la navigation.
    """
    _, centre, _ = st.columns([1, 1.1, 1])
    with centre:
        st.markdown("### 🍅 TomatoScan")
        st.title("Connexion")
        st.caption("Accédez à votre espace d'analyse des maladies de la tomate.")
        with st.form("login_form"):
            st.text_input("Nom d'utilisateur", placeholder="agriculteur01")
            st.text_input("Mot de passe", type="password", placeholder="••••••••")
            soumis = st.form_submit_button("Se connecter", use_container_width=True)
        if soumis:
            # Placeholder : la vraie vérification arrive en passe 2.
            st.session_state.token = "placeholder"
            st.rerun()


def page_predict():
    """Page Analyse (placeholder, implémentée en passe 3)."""
    st.title("Nouvelle analyse")
    st.info("Page d'analyse à venir (passe 3).")


def page_history():
    """Page Historique (placeholder)."""
    st.title("Historique des analyses")
    st.info("Page d'historique à venir.")


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
            if st.button("Déconnexion", use_container_width=True):
                st.session_state.pop("token", None)
                st.rerun()


def main():
    """Point d'entrée principal — gère l'état de session et orchestre la navigation."""
    # Initialisation de l'état d'authentification
    if "token" not in st.session_state:
        st.session_state.token = None

    inject_css()

    # Sidebar toujours visible : logo TomatoScan + état API + déconnexion si connecté
    sidebar_header()

    if st.session_state.token:
        # Utilisateur connecté : navigation complète (Analyse / Historique / Tableau de bord)
        navigation = st.navigation(
            {
                "TomatoScan": [
                    st.Page(page_predict, title="Analyse", icon=":material/biotech:", default=True),
                    st.Page(page_history, title="Historique", icon=":material/history:"),
                    st.Page(page_dashboard, title="Tableau de bord", icon=":material/bar_chart:"),
                ]
            }
        )
    else:
        # Non connecté : page de connexion seule, liens de navigation masqués dans la sidebar
        navigation = st.navigation(
            [st.Page(page_login, title="Connexion")],
            position="hidden",
        )

    navigation.run()


if __name__ == "__main__":
    main()
