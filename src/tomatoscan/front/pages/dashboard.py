"""Page Tableau de bord — vue d'ensemble des comptes et lien vers le monitoring.

Réservée aux administrateurs : liste des utilisateurs, résumé (nombre
d'agriculteurs, nombre de prédictions), suppression de compte, et accès
direct à Grafana.
"""

import os

import pandas as pd
import streamlit as st

from utils import api_client
from utils.api_client import ApiError

# --- Garde-fou : token + rôle admin -----------------------------------------
token = st.session_state.get("token")
if not token:
    st.warning("Veuillez vous connecter pour accéder au tableau de bord.")
    st.stop()

if st.session_state.get("role") != "admin":
    st.error("Accès réservé aux administrateurs.")
    st.stop()

st.title("Tableau de bord")
st.caption("Vue d'ensemble des comptes et accès au monitoring.")

# --- Lien vers Grafana --------------------------------------------------------
grafana_url = os.getenv("GRAFANA_URL", "")
if grafana_url:
    st.link_button("Ouvrir le monitoring", grafana_url)
else:
    st.caption("GRAFANA_URL non configurée dans l'environnement — lien indisponible.")

# --- Chargement des données ---------------------------------------------------
try:
    with st.spinner("Chargement des données…"):
        utilisateurs = api_client.list_users(token)
        # Grâce au filtrage par rôle côté API, un admin reçoit l'historique complet
        toutes_predictions = api_client.get_history(token)
except ApiError as erreur:
    if erreur.status_code == 401:
        st.session_state.clear()
        st.rerun()
    else:
        st.error(f"Impossible de charger les données du tableau de bord : {erreur}")
    st.stop()

agriculteurs = [u for u in utilisateurs if u.get("role") != "admin"]
nb_agriculteurs = len(agriculteurs)
nb_predictions = len(toutes_predictions)

# --- Résumé --------------------------------------------------------------------
st.subheader("Résumé")
if nb_agriculteurs == 0:
    st.info(
        "Aucun agriculteur inscrit pour le moment — invite tes premiers "
        "utilisateurs via la page **Créer un membre**."
    )
else:
    st.markdown(
        f"**{nb_agriculteurs}** agriculteur(s) actif(s), **{nb_predictions}** prédiction(s) au total."
    )

# --- Liste des utilisateurs -----------------------------------------------------
st.subheader("Utilisateurs")
lignes = [
    {
        "Nom d'utilisateur": u["username"],
        "Rôle": u["role"],
        "Créé le": u.get("created_at", "")[:19].replace("T", " "),
    }
    for u in utilisateurs
]
st.dataframe(pd.DataFrame(lignes), use_container_width=True, hide_index=True)

# --- Suppression de compte (agriculteurs uniquement) ----------------------------
st.subheader("Supprimer un compte agriculteur")
if not agriculteurs:
    st.caption("Aucun agriculteur à supprimer.")
else:
    for u in agriculteurs:
        colonne_nom, colonne_bouton = st.columns([3, 1])
        colonne_nom.write(u["username"])

        cle_confirmation = f"confirmer_suppression_{u['id']}"

        if colonne_bouton.button("Supprimer", key=f"supprimer_{u['id']}"):
            st.session_state[cle_confirmation] = True

        if st.session_state.get(cle_confirmation):
            st.warning(f"Confirmer la suppression du compte « {u['username']} » ?")
            colonne_oui, colonne_non = st.columns(2)
            if colonne_oui.button("Oui, supprimer", key=f"confirme_oui_{u['id']}"):
                try:
                    api_client.delete_user(u["id"], token)
                    st.success(f"Compte « {u['username']} » supprimé.")
                    st.session_state.pop(cle_confirmation, None)
                    st.rerun()
                except ApiError as erreur:
                    st.error(str(erreur))
            if colonne_non.button("Annuler", key=f"confirme_non_{u['id']}"):
                st.session_state.pop(cle_confirmation, None)
                st.rerun()
