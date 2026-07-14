"""Utilitaires de session Streamlit partagés entre plusieurs pages.

Séparé de utils/api_client.py, qui reste un client HTTP pur sans dépendance
à Streamlit (testable sans lancer l'application) — ce module-ci, lui,
dépend délibérément de streamlit puisqu'il agit directement sur
st.session_state et déclenche des reruns.
"""

import streamlit as st

from utils.api_client import ApiError


def gerer_erreur_401(erreur: ApiError) -> None:
    """Si l'erreur correspond à un token expiré/invalide (401), nettoie la
    session et redirige vers la connexion (st.session_state.clear() + rerun).

    Ne fait rien si l'erreur n'est pas un 401 — à l'appelant de traiter les
    autres codes d'erreur ensuite. Factorise un bloc auparavant dupliqué à
    l'identique dans pages/creer_membre.py, pages/dashboard.py,
    pages/history.py et pages/predict.py.
    """
    if erreur.status_code == 401:
        st.session_state.clear()
        st.rerun()
