"""Page Tableau de bord — vue d'ensemble des comptes et lien vers le monitoring.

Réservée aux administrateurs : liste des utilisateurs, résumé (nombre
d'agriculteurs, nombre de prédictions), suppression de compte, et accès
direct à Grafana.

Refonte visuelle (issue #33 suite) : les 2 chiffres clés (agriculteurs,
prédictions) mis en avant via des st.container(key=...) colorés façon
"metric card" — mêmes variables nb_agriculteurs/nb_predictions qu'avant,
logique d'appel API/rôle/suppression inchangée.
"""

import os

import pandas as pd
import streamlit as st

from utils import api_client
from utils.api_client import ApiError, fr_label
from utils.session import gerer_erreur_401

# --- Garde-fou : token + rôle admin -----------------------------------------
token = st.session_state.get("token")
if not token:
    st.warning("Veuillez vous connecter pour accéder au tableau de bord.")
    st.stop()

role = st.session_state.get("role")
if role is None:
    st.warning("Session incomplète, veuillez vous reconnecter.")
    st.stop()

if role != "admin":
    st.error("Accès réservé aux administrateurs.")
    st.stop()

st.title("Tableau de bord")
st.caption("Vue d'ensemble des comptes et accès au monitoring.")

# Lien vers l'historique détaillé — cette page (admin uniquement) montre les
# métriques agrégées ; l'historique complet (liste des prédictions) est sur
# pages/history.py, qui affiche déjà tout pour un admin (filtrage par rôle côté API)
st.page_link(
    "pages/history.py",
    label="Voir l'historique détaillé des prédictions",
    icon=":material/history:",
)

# --- Lien vers Grafana --------------------------------------------------------
grafana_url = os.getenv("GRAFANA_URL", "")
if grafana_url:
    st.link_button("Ouvrir le monitoring", grafana_url, icon=":material/open_in_new:")
else:
    st.caption("GRAFANA_URL non configurée dans l'environnement — lien indisponible.")

# --- Rapport d'entraînement du modèle (GET /reports) ---------------------------
# Section isolée dans son propre try/except : un CSV de rapport absent (404) ne
# doit pas empêcher l'affichage du reste du tableau de bord (utilisateurs, etc.).
st.subheader("Entraînement du modèle")
try:
    rapport = api_client.get_reports(token)
except ApiError as erreur:
    gerer_erreur_401(erreur)
    st.caption(f"Rapport d'entraînement indisponible : {erreur}")
else:
    colonne_epochs, colonne_accuracy = st.columns(2)
    colonne_epochs.metric("Epochs entraînées", rapport["nb_epochs"])
    colonne_accuracy.metric(
        "Meilleure précision (val)", f"{rapport['meilleure_val_accuracy']:.1%}"
    )
    with st.expander("Détail par epoch"):
        st.dataframe(
            pd.DataFrame(rapport["historique"]),
            use_container_width=True,
            hide_index=True,
        )

# --- Performance du modèle sur le jeu de test (GET /reports/evaluation) --------
# Section isolée dans son propre try/except, comme celle ci-dessus : un rapport
# d'évaluation pas encore généré (404) ne doit pas casser le reste de la page.
st.subheader("Performance du modèle (jeu de test)")
try:
    evaluation = api_client.get_evaluation(token)
except ApiError as erreur:
    gerer_erreur_401(erreur)
    st.caption(f"Rapport d'évaluation indisponible : {erreur}")
else:
    colonne_test, colonne_val = st.columns(2)
    colonne_test.metric("Test accuracy", f"{evaluation['accuracy_test']:.0%}")
    colonne_val.metric(
        "Val. accuracy", f"{evaluation['meilleure_accuracy_validation']:.0%}"
    )

    # rapport_classification mélange les classes avec les lignes agrégées
    # "accuracy" (un float, pas un dict), "macro avg", "weighted avg" — on ne
    # garde que les vraies classes pour le tableau F1 par classe.
    lignes_classes = [
        {
            "Classe": fr_label(classe),
            "Précision": f"{metriques['precision']:.1%}",
            "Rappel": f"{metriques['recall']:.1%}",
            "F1": f"{metriques['f1-score']:.1%}",
        }
        for classe, metriques in evaluation["rapport_classification"].items()
        if isinstance(metriques, dict)
    ]
    st.dataframe(
        pd.DataFrame(lignes_classes), use_container_width=True, hide_index=True
    )

    if evaluation["classes_sous_performantes"]:
        st.warning(
            "Classes sous-performantes (F1 bas) : "
            + ", ".join(fr_label(c) for c in evaluation["classes_sous_performantes"])
        )

    try:
        image_matrice = api_client.get_confusion_matrix(token)
    except ApiError as erreur:
        st.caption(f"Matrice de confusion indisponible : {erreur}")
    else:
        st.image(image_matrice, caption="Matrice de confusion (normalisée)")

# --- Chargement des données ---------------------------------------------------
try:
    with st.spinner("Chargement des données…"):
        utilisateurs = api_client.list_users(token)
        # Grâce au filtrage par rôle côté API, un admin reçoit l'historique complet
        toutes_predictions = api_client.get_history(token)
except ApiError as erreur:
    gerer_erreur_401(erreur)
    st.error(f"Impossible de charger les données du tableau de bord : {erreur}")
    st.stop()

agriculteurs = [u for u in utilisateurs if u.get("role") != "admin"]
nb_agriculteurs = len(agriculteurs)
nb_predictions = len(toutes_predictions)

# --- Résumé --------------------------------------------------------------------
st.subheader("Résumé")

colonne_a, colonne_b = st.columns(2)
with colonne_a:
    with st.container(key="metric_farmers"):
        st.caption("Agriculteurs")
        st.markdown(f"### {nb_agriculteurs}")
with colonne_b:
    with st.container(key="metric_predictions"):
        st.caption("Prédictions totales")
        st.markdown(f"### {nb_predictions}")

if nb_agriculteurs == 0:
    st.info(
        "Aucun agriculteur inscrit pour le moment — invite tes premiers "
        "utilisateurs via la page **Créer un membre**."
    )

st.markdown(
    """<style>
    .st-key-metric_farmers { background:#2d6a4f; border-radius:12px; padding:1.1rem 1.4rem; }
    .st-key-metric_farmers p, .st-key-metric_farmers h3 { color:#ffffff !important; }
    .st-key-metric_predictions { background:#1b4332; border-radius:12px; padding:1.1rem 1.4rem; }
    .st-key-metric_predictions p, .st-key-metric_predictions h3 { color:#ffffff !important; }
    </style>""",
    unsafe_allow_html=True,
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

        if colonne_bouton.button(
            "Supprimer", icon=":material/delete:", key=f"supprimer_{u['id']}"
        ):
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
