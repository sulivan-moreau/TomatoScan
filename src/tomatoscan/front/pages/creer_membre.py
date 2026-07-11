"""Page Créer un membre — création de comptes agriculteur.

Réservée aux administrateurs. Le rôle du compte créé est toujours
"agriculteur" (imposé côté API, cette page ne permet pas de créer un admin).
"""

import streamlit as st

from utils import api_client
from utils.api_client import ApiError

# --- Garde-fou : token + rôle admin -----------------------------------------
token = st.session_state.get("token")
if not token:
    st.warning("Veuillez vous connecter pour accéder à cette page.")
    st.stop()

if st.session_state.get("role") != "admin":
    st.error("Accès réservé aux administrateurs.")
    st.stop()

st.title("Créer un membre")
st.caption("Crée un nouveau compte agriculteur avec accès à l'application.")

with st.form("creer_membre_form", clear_on_submit=True):
    nom_utilisateur = st.text_input("Nom d'utilisateur", placeholder="agriculteur02")
    mot_de_passe = st.text_input("Mot de passe", type="password", placeholder="••••••••")
    soumis = st.form_submit_button("Créer le compte", use_container_width=True)

if soumis:
    if not nom_utilisateur or not mot_de_passe:
        st.error("Veuillez renseigner un nom d'utilisateur et un mot de passe.")
    else:
        try:
            with st.spinner("Création en cours…"):
                api_client.create_user(nom_utilisateur, mot_de_passe, token)
            st.success(f"Compte « {nom_utilisateur} » créé avec succès.")
        except ApiError as erreur:
            if erreur.status_code == 401:
                st.session_state.clear()
                st.rerun()
            else:
                # Message affiché tel que retourné par l'API (ex. 409 « déjà utilisé »)
                st.error(str(erreur))
