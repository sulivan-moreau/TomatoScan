"""Page d'accueil TomatoScan — point d'entrée avant et après connexion.

Non connecté : présentation courte + lien vers la connexion.
Connecté : liens rapides vers les pages disponibles pour l'utilisateur —
le filtrage par rôle réutilise exactement le même test que app.py
(api_client.obtenir_role(token) == "admin", jamais session_state.role,
qui n'est jamais stocké séparément).

Accueil est la page d'atterrissage non connecté (app.py) : le message de
session expirée (posé par main() dans app.py) est donc affiché ici plutôt
que sur pages/login.py, pour être vu immédiatement.

Refonte visuelle (issue #33 suite) : mise en avant via des blocs
st.container(key=...) stylés en CSS scoped à cette page (.st-key-*) —
palette et logique de navigation/rôle inchangées.
"""

import streamlit as st

from utils import api_client

st.title("TomatoScan")
st.caption(
    "Détection des maladies de la tomate à partir d'une photo de feuille, "
    "propulsée par un modèle MobileNetV2."
)

st.divider()

if not st.session_state.get("token"):
    if st.session_state.pop("session_expiree", False):
        st.warning("Session expirée, veuillez vous reconnecter.")

    with st.container(key="hero_primary"):
        st.markdown(":material/biotech:")
        st.markdown("#### Diagnostiquez une feuille en quelques secondes")
        st.caption(
            "Importez une photo, obtenez un résultat immédiat sur l'état "
            "sanitaire de votre plant."
        )

    with st.container(key="hero_secondary"):
        st.write(":material/eco: Détection saine ou malade")
        st.write(":material/history: Historique conservé")

    with st.container(key="cta_login"):
        colonne_message, colonne_bouton = st.columns([3, 1])
        with colonne_message:
            st.write(
                ":material/info: Connectez-vous pour analyser une feuille "
                "et retrouver votre historique."
            )
        with colonne_bouton:
            st.page_link(
                "pages/login.py", label="Se connecter", icon=":material/login:"
            )

    st.markdown(
        """<style>
        .st-key-hero_primary { background:#2d6a4f; border-radius:14px; padding:1.75rem; }
        .st-key-hero_primary p, .st-key-hero_primary h4 { color:#ffffff !important; }
        .st-key-hero_secondary { background:#ffffff; border:1px solid #e8f1ea; border-radius:14px; padding:1.25rem 1.5rem; }
        .st-key-cta_login { background:#ffffff; border:1px solid #d9e3dc; border-radius:12px; padding:0.9rem 1.25rem; }
        .st-key-cta_login div[data-testid="stPageLink"] a {
            background:#2d6a4f; color:#ffffff !important; padding:0.55rem 1.1rem;
            border-radius:8px; font-weight:600; justify-content:center;
        }
        </style>""",
        unsafe_allow_html=True,
    )
else:
    st.subheader("Accès rapide")

    with st.container(key="card_primary"):
        st.page_link(
            "pages/predict.py", label="Nouvelle analyse", icon=":material/biotech:"
        )
        st.caption("Photographiez une feuille et obtenez un diagnostic immédiat.")

    with st.container(key="card_secondary"):
        st.page_link(
            "pages/history.py",
            label="Historique de mes analyses",
            icon=":material/history:",
        )
        st.caption("Retrouvez vos diagnostics passés et leur score de confiance.")

    if api_client.obtenir_role(st.session_state.get("token")) == "admin":
        with st.container(key="card_admin_group"):
            st.markdown(":material/admin_panel_settings: **Administration**")
            colonne_a, colonne_b = st.columns(2)
            with colonne_a:
                with st.container(key="card_admin_a"):
                    st.page_link(
                        "pages/dashboard.py",
                        label="Tableau de bord",
                        icon=":material/bar_chart:",
                    )
            with colonne_b:
                with st.container(key="card_admin_b"):
                    st.page_link(
                        "pages/creer_membre.py",
                        label="Créer un membre",
                        icon=":material/person_add:",
                    )

    st.markdown(
        """<style>
        .st-key-card_primary { background:#2d6a4f; border-radius:14px; padding:1.4rem 1.6rem; }
        .st-key-card_primary p, .st-key-card_primary a, .st-key-card_primary span { color:#ffffff !important; }
        .st-key-card_secondary { background:#ffffff; border:1px solid #e8f1ea; border-radius:14px; padding:1.1rem 1.5rem; }
        .st-key-card_admin_group { background:#e8f1ea; border-radius:14px; padding:1.1rem 1.5rem; }
        .st-key-card_admin_a, .st-key-card_admin_b { background:#ffffff; border-radius:10px; padding:0.6rem 1rem; }
        </style>""",
        unsafe_allow_html=True,
    )
