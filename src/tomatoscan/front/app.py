"""Point d'entrée de l'application Streamlit TomatoScan.

- Configuration de la page et thème CSS,
- Sidebar persistante (logo, état API, déconnexion),
- Vérification de la validité du token JWT à chaque re-run Streamlit,
- Routing conditionnel : non connecté → login, connecté → Analyse / Historique
  (+ Tableau de bord / Créer un membre si role="admin").

Lancement : `streamlit run src/tomatoscan/front/app.py`
"""

import streamlit as st
import streamlit.components.v1 as components

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


def forcer_langue_francaise():
    """Force l'attribut HTML `lang="fr"` sur la page (accessibilité C17).

    Streamlit sert son index.html avec `lang="en"` codé en dur et n'expose aucun
    paramètre pour le changer (ni dans st.set_page_config, ni dans config.toml,
    version 1.58). Or l'application est intégralement francophone : sans
    correction, les lecteurs d'écran annoncent le contenu avec une prononciation
    anglaise.

    Contournement documenté : on injecte un court script via components.html
    (rendu dans une iframe de même origine) qui met à jour
    `document.documentElement.lang` de la page parente. C'est la seule voie
    propre disponible tant que Streamlit n'offre pas d'API dédiée ; à
    réévaluer si une option native apparaît dans une version ultérieure.
    Sans effet en environnement de test (AppTest n'exécute pas le JavaScript),
    mais sans danger non plus : l'appel n'échoue pas.
    """
    components.html(
        """
        <script>
        const doc = window.parent.document;
        if (doc && doc.documentElement) { doc.documentElement.lang = "fr"; }
        </script>
        """,
        height=0,
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
    # Accessibilité : force lang="fr" sur la page (app francophone servie en
    # lang="en" par défaut par Streamlit) — voir forcer_langue_francaise().
    forcer_langue_francaise()

    # Vérification du token JWT à chaque re-run : si expiré, vider la session
    token_actuel = st.session_state.get("token")
    if token_actuel and not api_client.is_token_valid(token_actuel):
        st.session_state.clear()
        st.session_state["session_expiree"] = True
        st.rerun()

    # Renouvellement silencieux si le token est encore valide mais expire bientôt
    # (< 2 min) — avant tout appel API de la page, une fois par re-run suffit ici
    if token_actuel:
        st.session_state.token = api_client.renouveler_si_necessaire(token_actuel)

    # Si la session contient un token mais pas de rôle, on considère l'état comme
    # incohérent : le rôle doit toujours être fixé au login. Pas de fallback JWT.
    if token_actuel and "role" not in st.session_state:
        st.session_state.clear()
        st.session_state["session_expiree"] = True
        st.rerun()

    # Sidebar toujours visible : logo TomatoScan + état API + déconnexion si connecté
    sidebar_header()

    if st.session_state.get("token"):
        # Utilisateur connecté : Accueil/Analyse/Historique pour tous, pages admin en plus si role="admin"
        role_actuel = st.session_state.get("role")
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
        if role_actuel == "admin":
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
