"""Page d'accueil TomatoScan — point d'entrée avant et après connexion.

Non connecté : présentation courte + lien vers la connexion.
Connecté : liens rapides vers les pages disponibles pour l'utilisateur —
le filtrage par rôle réutilise exactement le même test que app.py:123
(st.session_state.get("role") == "admin"), pas de logique dupliquée.

Accueil est désormais la page d'atterrissage non connecté (app.py) : le
message de session expirée (posé par main() dans app.py) est donc affiché
ici plutôt que sur pages/login.py, pour être vu immédiatement.
"""

import streamlit as st

st.title("TomatoScan")
st.caption(
    "Détection des maladies de la tomate à partir d'une photo de feuille, "
    "propulsée par un modèle MobileNetV2."
)

st.divider()

if not st.session_state.get("token"):
    if st.session_state.pop("session_expiree", False):
        st.warning("Session expirée, veuillez vous reconnecter.")

    st.info("Connectez-vous pour accéder à l'analyse et à votre historique.")
    st.page_link("pages/login.py", label="Se connecter", icon=":material/login:")
else:
    st.subheader("Accès rapide")

    st.page_link(
        "pages/predict.py", label="Nouvelle analyse", icon=":material/biotech:"
    )
    st.page_link(
        "pages/history.py", label="Historique de mes analyses", icon=":material/history:"
    )

    if st.session_state.get("role") == "admin":
        st.page_link(
            "pages/dashboard.py",
            label="Tableau de bord (comptes + métriques globales)",
            icon=":material/bar_chart:",
        )
        st.page_link(
            "pages/creer_membre.py",
            label="Créer un membre",
            icon=":material/person_add:",
        )
