"""Page d'analyse (prédiction) TomatoScan — Issue #12.

Parcours :
1. l'agriculteur importe une image de feuille (jpg / jpeg / png),
2. il visualise l'aperçu,
3. il lance l'analyse (POST /predict, token Bearer),
4. le diagnostic s'affiche : bandeau vert « Tomate saine » ou bandeau
   rouge avec le nom de la maladie traduit, plus le score de confiance.

Commentaires en français. Contrastes conformes WCAG AA (texte blanc sur
fonds #2d6a4f et #c1121f : ratios respectivement ≈ 5.6:1 et ≈ 6.5:1).
"""

import streamlit as st

from utils import api_client

# --- Garde-fou d'authentification -------------------------------------------
# Sans token en session, on ne peut pas appeler l'API : retour à la connexion.
token = st.session_state.get("token")
if not token:
    st.warning("Veuillez vous connecter pour accéder à l'analyse.")
    st.stop()

st.title("Nouvelle analyse")
st.caption("Importez une photo de feuille de tomate, puis lancez la détection.")

colonne_image, colonne_resultat = st.columns(2, gap="large")

# --- Colonne gauche : upload + aperçu + bouton ------------------------------
with colonne_image:
    st.subheader("1 · Image à analyser")
    fichier = st.file_uploader(
        "Image de la feuille (formats acceptés : JPG, JPEG, PNG)",
        type=["jpg", "jpeg", "png"],
        help="Choisissez une photo nette de la feuille à diagnostiquer.",
    )

    if fichier is not None:
        # Aperçu de l'image importée.
        st.image(fichier, caption=fichier.name, use_container_width=True)

    analyser = st.button(
        "Analyser",
        type="primary",
        use_container_width=True,
        disabled=(fichier is None),
    )

# --- Colonne droite : résultat du diagnostic --------------------------------
with colonne_resultat:
    st.subheader("2 · Résultat")

    if analyser and fichier is not None:
        try:
            with st.spinner("Analyse en cours…"):
                image_bytes = fichier.getvalue()
                resultat = api_client.predict(image_bytes, fichier.name, token)
            # On mémorise le résultat pour qu'il survive au rerun de Streamlit.
            st.session_state.dernier_resultat = resultat
        except api_client.ApiError as erreur:
            # Traitement des codes HTTP significatifs.
            if erreur.status_code == 401:
                # Token expiré / invalide : on nettoie la session et on redirige.
                st.session_state.clear()
                st.rerun()
            elif erreur.status_code == 400:
                st.error("Image invalide — vérifiez le format (jpg/png).")
            elif erreur.status_code == 503:
                st.error("Service temporairement indisponible, réessayez dans quelques instants.")
            else:
                # Autres erreurs (réseau, 500…) : message générique.
                st.error(str(erreur))

    # Affichage du dernier résultat disponible.
    resultat = st.session_state.get("dernier_resultat")
    if resultat:
        classe = resultat.get("classe")
        confiance = resultat.get("confiance", 0) or 0
        # La confiance peut arriver en 0-1 (proba) ou déjà en pourcentage.
        pourcent = confiance * 100 if confiance <= 1 else confiance
        pourcent = max(0.0, min(pourcent, 100.0))

        if classe == "Tomato_healthy":
            # Bandeau vert : plante saine (texte blanc sur #2d6a4f, WCAG AA).
            st.markdown(
                """
                <div style="background:#2d6a4f;color:#ffffff;border-radius:12px;
                            padding:18px 20px;font-size:1.25rem;font-weight:700;">
                    🍅 Tomate saine
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption("Aucune maladie détectée sur la feuille analysée.")
        else:
            # Bandeau rouge : maladie détectée (texte blanc sur #c1121f, WCAG AA).
            maladie_fr = api_client.fr_label(classe)
            st.markdown(
                f"""
                <div style="background:#c1121f;color:#ffffff;border-radius:12px;
                            padding:18px 20px;">
                    <div style="font-size:0.9rem;font-weight:600;letter-spacing:.04em;
                                text-transform:uppercase;opacity:.95;">Maladie détectée</div>
                    <div style="font-size:1.35rem;font-weight:700;margin-top:2px;">{maladie_fr}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Message optionnel renvoyé par l'API.
        message = resultat.get("message")
        if message:
            st.caption(message)

        # Score de confiance : barre + valeur en pourcentage.
        st.markdown("**Confiance**")
        st.progress(int(round(pourcent)))
        st.markdown(f"### {pourcent:.2f} %")
    else:
        st.info("Importez une image puis cliquez sur « Analyser » pour afficher le diagnostic.")
