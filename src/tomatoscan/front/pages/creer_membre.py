"""Page Créer un membre — création de comptes agriculteur.

Réservée aux administrateurs. Le rôle du compte créé est toujours
"agriculteur" (imposé côté API, cette page ne permet pas de créer un admin).

Refonte visuelle (issue #33 suite) : formulaire dans une carte
st.container(key="creer_membre_card") à accent vert foncé #1b4332 (distinct
du vert #2d6a4f de login_card, pour signaler visuellement un contexte
admin-only sans introduire de nouvelle couleur) — logique de création
inchangée. Badge "🛡 Admin" de la maquette d'origine remplacé par l'icône
Material équivalente (:material/admin_panel_settings:),
cohérent avec le principe "emoji → icônes Material" et avec le même badge
utilisé sur pages/accueil.py.
"""

import streamlit as st

from utils import api_client
from utils.api_client import ApiError
from utils.session import gerer_erreur_401

# --- Garde-fou : token + rôle admin -----------------------------------------
token = st.session_state.get("token")
if not token:
    st.warning("Veuillez vous connecter pour accéder à cette page.")
    st.stop()

if api_client.obtenir_role(token) != "admin":
    st.error("Accès réservé aux administrateurs.")
    st.stop()

st.title("Créer un membre")
st.caption("Crée un nouveau compte agriculteur avec accès à l'application.")

with st.container(key="creer_membre_card"):
    st.markdown(":material/admin_panel_settings: Admin")
    with st.form("creer_membre_form", clear_on_submit=True):
        nom_utilisateur = st.text_input(
            "Nom d'utilisateur", placeholder="agriculteur02"
        )
        mot_de_passe = st.text_input(
            "Mot de passe", type="password", placeholder="••••••••"
        )
        soumis = st.form_submit_button(
            "Créer le compte",
            icon=":material/person_add:",
            use_container_width=True,
        )

    if soumis:
        if not nom_utilisateur or not mot_de_passe:
            st.error("Veuillez renseigner un nom d'utilisateur et un mot de passe.")
        else:
            try:
                with st.spinner("Création en cours…"):
                    api_client.create_user(nom_utilisateur, mot_de_passe, token)
                st.success(f"Compte « {nom_utilisateur} » créé avec succès.")
            except ApiError as erreur:
                gerer_erreur_401(erreur)
                # Message affiché tel que retourné par l'API (ex. 409 « déjà utilisé »)
                st.error(str(erreur))

st.markdown(
    """<style>
    .st-key-creer_membre_card { background:#ffffff; border:1px solid #1b4332; border-radius:14px; padding:2rem 2.1rem; }
    .st-key-creer_membre_card button[kind="formSubmit"] { background:#1b4332; color:#ffffff; border:none; }
    .st-key-creer_membre_card button[kind="formSubmit"]:hover { background:#2d6a4f; }
    </style>""",
    unsafe_allow_html=True,
)
