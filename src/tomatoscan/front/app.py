"""Point d'entrée de l'application Streamlit TomatoScan.

- Configuration de la page et thème CSS,
- Sidebar persistante (logo, état API, déconnexion),
- Vérification de la validité du token JWT à chaque re-run Streamlit,
- Routing conditionnel : non connecté → login, connecté → Analyse / Historique
  (+ Tableau de bord / Créer un membre si role="admin").

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

        /* Sidebar vert profond — texte clair limité aux éléments de texte réels
           (paragraphes, légendes, libellés, conteneurs markdown) plutôt qu'un
           sélecteur universel qui déborderait sur tout élément (icônes, bordures,
           états focus...) sans qu'on le voie dans ce fichier */
        section[data-testid="stSidebar"] {{ background: {VERT_FONCE}; }}
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] small,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] .stMarkdown {{ color: #e8f1ea; }}
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


def sidebar_header():
    """Affiche le logo et la déconnexion (si connecté)."""
    with st.sidebar:
        st.markdown(
            '<div class="ts-logo"><span class="ts-dot"></span>TomatoScan</div>',
            unsafe_allow_html=True,
        )

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
        # Utilisateur connecté : Accueil/Analyse/Historique pour tous, pages admin en plus si role="admin"
        pages = [
            st.Page(
                "pages/accueil.py",
                title="Accueil",
                icon=":material/home:",
            ),
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
        ]
        if st.session_state.get("role") == "admin":
            pages.append(
                st.Page(
                    "pages/dashboard.py",
                    title="Tableau de bord",
                    icon=":material/bar_chart:",
                )
            )
            pages.append(
                st.Page(
                    "pages/creer_membre.py",
                    title="Créer un membre",
                    icon=":material/person_add:",
                )
            )
        navigation = st.navigation({"TomatoScan": pages})
    else:
        # Non connecté : Accueil (avec lien vers connexion) + page de connexion,
        # liens de navigation masqués dans la sidebar (position="hidden")
        navigation = st.navigation(
            [
                st.Page("pages/accueil.py", title="Accueil", icon=":material/home:"),
                st.Page("pages/login.py", title="Connexion", icon=":material/login:"),
            ],
            position="hidden",
        )

    navigation.run()


if __name__ == "__main__":
    main()
