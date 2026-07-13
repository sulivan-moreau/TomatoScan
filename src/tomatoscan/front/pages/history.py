"""Page Historique des analyses — affiche les prédictions passées de l'utilisateur.

Appelle GET /predictions/history avec le token Bearer et présente les résultats
dans un tableau : date, fichier analysé, maladie détectée (en français), confiance.

Refonte visuelle (issue #33 suite) : état vide mis en avant via un
st.container(key="history_empty") avec lien direct vers l'analyse, et
coloration de la colonne "Maladie détectée" via un Styler pandas (vert si
"Tomate saine", rouge sinon) — pandas.Styler.map (pas .applymap, déprécié
depuis pandas 2.1). Logique d'appel API et de filtrage par rôle inchangée,
voir docs/brief_design.md.
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

# Lien vers les métriques globales — réservé admin, même test de rôle que app.py:123
if st.session_state.get("role") == "admin":
    st.page_link(
        "pages/dashboard.py",
        label="Voir les métriques globales (tous utilisateurs) dans le Tableau de bord",
        icon=":material/bar_chart:",
    )

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
    with st.container(key="history_empty"):
        st.write(":material/eco: **Pas encore d'analyse enregistrée**")
        st.caption(
            "Lancez votre première analyse pour commencer à suivre l'état de vos plants."
        )
        st.page_link(
            "pages/predict.py", label="Nouvelle analyse", icon=":material/biotech:"
        )
    st.markdown(
        """<style>
        .st-key-history_empty { background:#e8f1ea; border-radius:12px; padding:1.4rem 1.5rem; }
        </style>""",
        unsafe_allow_html=True,
    )
    st.stop()

st.caption(f"{len(entrees)} analyse(s) enregistrée(s).")

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


def _couleur_maladie(valeur: str) -> str:
    """Vert si tomate saine, rouge sinon — même logique de couleur que predict.py."""
    couleur = "#2d6a4f" if valeur == "Tomate saine" else "#c1121f"
    return f"color: {couleur}; font-weight: 600;"


tableau_style = tableau.style.map(_couleur_maladie, subset=["Maladie détectée"])

st.dataframe(
    tableau_style,
    use_container_width=True,
    hide_index=True,
)

st.markdown(
    """<style>
    div[data-testid="stDataFrame"] thead tr th { background:#e8f1ea !important; color:#1b4332 !important; }
    </style>""",
    unsafe_allow_html=True,
)
