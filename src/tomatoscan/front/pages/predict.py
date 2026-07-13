"""Page d'analyse (prédiction) TomatoScan — Issue #12.

Parcours :
1. l'agriculteur importe une image de feuille (jpg / jpeg / png),
2. il visualise l'aperçu,
3. il lance l'analyse (POST /predict, token Bearer),
4. le diagnostic s'affiche : bandeau vert « Tomate saine » ou bandeau
   rouge avec le nom de la maladie traduit, plus le score de confiance.

Commentaires en français. Contrastes conformes WCAG AA (texte blanc sur
fonds #2d6a4f et #c1121f : ratios respectivement 6.39:1 et 6.22:1 — calculés
précisément par formule de luminance relative WCAG, voir docs/audit_frontend_existant.md).

Refonte visuelle (issue #33 suite) : zone d'upload et bloc de recommandation
mis en avant via st.container(key=...) + CSS scoped, icônes Material Symbols
ajoutées dans les bandeaux résultat (déjà conformes WCAG, non touchés côté
couleurs). Aucune logique d'appel API ni de gestion d'erreur modifiée —
voir docs/brief_design.md.
"""

import streamlit as st

from utils import api_client

# Conseils génériques par maladie détectée (clés = valeurs brutes de l'API,
# les mêmes que api_client.DISEASE_LABELS — pas de nom inventé). Pas de
# conseil pour Tomato_healthy : la recommandation ne s'affiche que si une
# maladie est détectée.
RECOMMANDATIONS = {
    "Tomato_Bacterial_spot": (
        "Retirez et détruisez les feuilles touchées, évitez d'arroser le "
        "feuillage et espacez les plants pour limiter la propagation bactérienne."
    ),
    "Tomato_Early_blight": (
        "Éliminez les feuilles atteintes en partant du bas du plant, "
        "paillez le sol pour éviter les éclaboussures et surveillez l'évolution."
    ),
    "Tomato_Late_blight": (
        "Maladie à propagation rapide : isolez le plant si possible et "
        "consultez un technicien agricole rapidement, les pertes peuvent être importantes."
    ),
    "Tomato_Leaf_Mold": (
        "Améliorez l'aération autour des plants et réduisez l'humidité "
        "ambiante (serre notamment), retirez les feuilles les plus atteintes."
    ),
    "Tomato_Septoria_leaf_spot": (
        "Retirez les feuilles touchées, évitez l'arrosage par aspersion et "
        "assurez une bonne circulation d'air entre les plants."
    ),
    "Tomato_Spider_mites_Two_spotted_spider_mite": (
        "Vérifiez le dessous des feuilles (présence de toiles fines), "
        "augmentez l'humidité ambiante et envisagez un traitement acaricide adapté."
    ),
    "Tomato__Target_Spot": (
        "Retirez les feuilles atteintes et évitez le stress hydrique, "
        "qui favorise l'apparition de cette maladie."
    ),
    "Tomato__Tomato_mosaic_virus": (
        "Aucun traitement curatif : isolez le plant, désinfectez vos outils "
        "après manipulation et évitez de propager le virus aux plants sains."
    ),
    "Tomato__Tomato_YellowLeaf__Curl_Virus": (
        "Ce virus est transmis par les aleurodes (mouches blanches) : "
        "luttez contre ces insectes vecteurs et retirez les plants trop atteints."
    ),
}

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
    with st.container(key="upload_zone"):
        st.markdown("##### :material/add_photo_alternate: Glissez-déposez une photo de feuille")
        st.caption("ou cliquez pour parcourir · JPG, JPEG, PNG")
        fichier = st.file_uploader(
            "Image de la feuille (formats acceptés : JPG, JPEG, PNG)",
            type=["jpg", "jpeg", "png"],
            help="Choisissez une photo nette de la feuille à diagnostiquer.",
            label_visibility="collapsed",
        )

        if fichier is not None:
            # Aperçu de l'image importée.
            st.image(fichier, caption=fichier.name, use_container_width=True)

        analyser = st.button(
            "Analyser",
            icon=":material/biotech:",
            type="primary",
            use_container_width=True,
            disabled=(fichier is None),
        )

    st.markdown(
        """<style>
        .st-key-upload_zone { background:#e8f1ea; border:2px dashed #2d6a4f; border-radius:14px; padding:1.5rem; text-align:center; }
        .st-key-upload_zone section[data-testid="stFileUploaderDropzone"] { background:transparent; border:none; }
        </style>""",
        unsafe_allow_html=True,
    )

# --- Colonne droite : résultat du diagnostic --------------------------------
with colonne_resultat:
    st.subheader("2 · Résultat")

    if analyser and fichier is not None:
        try:
            with st.spinner(
                "Analyse en cours… quelques secondes suffisent, ne fermez pas cette page."
            ):
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
                st.error(
                    "Service temporairement indisponible, réessayez dans quelques instants."
                )
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
                            padding:18px 20px;display:flex;align-items:center;gap:0.6rem;">
                    :material/eco:
                    <span style="font-size:1.25rem;font-weight:700;">Tomate saine</span>
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
                    <div style="display:flex;align-items:center;gap:0.5rem;
                                font-size:0.9rem;font-weight:600;letter-spacing:.04em;
                                text-transform:uppercase;opacity:.95;">
                        <span style="font-size:1.1rem;">:material/warning:</span>
                        Maladie détectée
                    </div>
                    <div style="font-size:1.35rem;font-weight:700;margin-top:2px;">{maladie_fr}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Message optionnel renvoyé par l'API.
        message = resultat.get("message")
        if message:
            st.caption(message)

        # Recommandation générique si une maladie est détectée.
        if classe != "Tomato_healthy" and classe in RECOMMANDATIONS:
            with st.container(key="recommendation"):
                st.markdown(":material/lightbulb: **Recommandation**")
                st.write(RECOMMANDATIONS[classe])

        # Score de confiance : barre + valeur en pourcentage.
        st.markdown("**Confiance**")
        st.progress(int(round(pourcent)))
        st.markdown(f"### {pourcent:.2f} %")
    else:
        st.info(
            "Importez une image puis cliquez sur « Analyser » pour afficher le diagnostic."
        )

st.markdown(
    """<style>
    .st-key-recommendation { background:#ffffff; border:1px solid #e8f1ea; border-left:4px solid #2d6a4f; border-radius:10px; padding:1rem 1.25rem; }
    </style>""",
    unsafe_allow_html=True,
)
