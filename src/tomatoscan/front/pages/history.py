"""Page Historique des analyses — affiche les prédictions passées de l'utilisateur.

Appelle GET /predictions/history avec le token Bearer et présente les résultats
dans un tableau : date, fichier analysé, maladie détectée (en français), confiance.
"""

import pandas as pd
import streamlit as st

from utils import api_client
from utils.api_client import ApiError

# Garde-fou d'authentification — redirige vers la connexion si aucun token
token = st.session_state.get("token")
if not token:
    st.warning("Veuillez vous connecter pour accéder à l'historique.")
    st.stop()

st.title("Historique des analyses")
st.caption("Retrouvez toutes vos analyses de feuilles de tomate.")

try:
    with st.spinner("Chargement de l'historique…"):
        entrees = api_client.get_history(token)
except ApiError as erreur:
    # Token expiré : nettoyage de la session et redirection
    if erreur.status_code == 401:
        st.session_state.clear()
        st.rerun()
    else:
        st.error(f"Impossible de charger l'historique : {erreur}")
    st.stop()

if not entrees:
    st.info(
        "Aucune analyse enregistrée pour l'instant. Lancez votre première analyse !"
    )
    st.stop()

# Construction du DataFrame pour l'affichage
lignes = []
for entree in entrees:
    lignes.append(
        {
            "Date": entree.get("created_at", "")[:19].replace("T", " "),
            "Fichier": entree.get("nom_fichier", ""),
            "Maladie détectée": api_client.fr_label(entree.get("classe_predite", "")),
            "Confiance": f"{entree.get('confiance', 0) * 100:.1f} %",
        }
    )

tableau = pd.DataFrame(lignes)

st.dataframe(
    tableau,
    use_container_width=True,
    hide_index=True,
)

st.caption(f"{len(entrees)} analyse(s) enregistrée(s).")
