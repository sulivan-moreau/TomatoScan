"""Page d'analyse (prédiction) TomatoScan — Issue #12.

Parcours :
1. l'agriculteur importe une image de feuille (jpg / jpeg / png),
2. il visualise l'aperçu,
3. il lance l'analyse (POST /predict, token Bearer),
4. le diagnostic s'affiche : bandeau vert « Tomate saine » ou bandeau
   rouge avec le nom de la maladie traduit, plus le score de confiance.

Commentaires en français. Contrastes conformes WCAG AA (texte blanc sur
fonds #2d6a4f et #c1121f : ratios respectivement 6.39:1 et 6.22:1, calculés
par formule de luminance relative WCAG).

Refonte visuelle (issue #33 suite) : zone d'upload et bloc de recommandation
mis en avant via st.container(key=...) + CSS scoped, icônes Material Symbols
ajoutées dans les bandeaux résultat (déjà conformes WCAG, non touchés côté
couleurs). Aucune logique d'appel API ni de gestion d'erreur modifiée.

Éco-conception (C17) : l'image est redimensionnée et recompressée côté client
AVANT l'envoi réseau (_compresser_image) — le modèle infère en 224x224, il est
inutile de transférer une photo de plusieurs mégapixels. Voir aussi
.streamlit/config.toml ([server] maxUploadSize = 5) qui borne l'upload sur les
5 Mo acceptés par l'API.

Accessibilité (C17) : l'aperçu de l'image porte un texte alternatif descriptif
(caption), et les icônes des bandeaux résultat sont des SVG inline (et non des
directives :material/... qui s'affichaient en texte brut dans le HTML injecté).
"""

import io

import streamlit as st
from PIL import Image

from utils import api_client
from utils.session import gerer_erreur_401

# Éco-conception : borne du plus grand côté de l'image (en pixels) et qualité JPEG
# utilisées par _compresser_image avant l'envoi à l'API. 1024 px reste très
# supérieur au 224x224 attendu par le modèle : marge confortable sans transférer
# de photo inutilement lourde.
TAILLE_MAX_COTE_PX = 1024
QUALITE_JPEG = 85


def _compresser_image(octets_image: bytes, nom_fichier: str) -> bytes:
    """Redimensionne et recompresse l'image avant l'envoi à l'API (éco-conception).

    Borne le plus grand côté de l'image à TAILLE_MAX_COTE_PX : une photo de
    smartphone (souvent 4000x3000) est ainsi ramenée à ~1024 px de côté, ce qui
    réduit fortement le volume transféré (bande passante, énergie) sans impact
    sur le diagnostic — le modèle travaille de toute façon en 224x224.

    Le format d'origine est préservé pour ne pas casser le contrat multipart avec
    l'API (un JPEG reste un JPEG, un PNG reste un PNG) : api_client.predict()
    déduit le type MIME de l'extension du fichier, qui n'est pas modifiée ici.
    Une image déjà raisonnable (côté <= TAILLE_MAX_COTE_PX) est renvoyée telle
    quelle. En cas d'erreur (image illisible, Pillow indisponible), on renvoie les
    octets d'origine pour ne jamais empêcher l'analyse.
    """
    try:
        with Image.open(io.BytesIO(octets_image)) as image:
            format_origine = (image.format or "").upper()
            plus_grand_cote = max(image.size)

            # Image déjà légère : aucune retouche (choix conservateur).
            if plus_grand_cote <= TAILLE_MAX_COTE_PX:
                return octets_image

            ratio = TAILLE_MAX_COTE_PX / plus_grand_cote
            nouvelle_taille = (
                round(image.width * ratio),
                round(image.height * ratio),
            )
            image_reduite = image.resize(nouvelle_taille, Image.Resampling.LANCZOS)

            tampon = io.BytesIO()
            if format_origine == "PNG":
                image_reduite.save(tampon, format="PNG", optimize=True)
            else:
                # JPEG n'accepte pas la transparence : conversion RGB au besoin.
                if image_reduite.mode != "RGB":
                    image_reduite = image_reduite.convert("RGB")
                image_reduite.save(
                    tampon, format="JPEG", quality=QUALITE_JPEG, optimize=True
                )
            return tampon.getvalue()
    except Exception:
        # Robustesse : toute erreur de traitement renvoie l'image brute d'origine
        # — l'analyse reste possible, le format étant validé côté API.
        return octets_image


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
        st.markdown(
            "##### :material/add_photo_alternate: Glissez-déposez une photo de feuille"
        )
        st.caption("ou cliquez pour parcourir · JPG, JPEG, PNG")
        fichier = st.file_uploader(
            "Image de la feuille (formats acceptés : JPG, JPEG, PNG)",
            type=["jpg", "jpeg", "png"],
            help="Choisissez une photo nette de la feuille à diagnostiquer.",
            label_visibility="collapsed",
        )

        if fichier is not None:
            # Aperçu de l'image importée. La légende sert aussi de texte
            # alternatif descriptif (accessibilité C17) : st.image n'expose pas de
            # paramètre alt, la caption est donc le seul texte associé à l'image.
            st.image(
                fichier,
                caption=f"Aperçu de la feuille de tomate à analyser ({fichier.name})",
                use_container_width=True,
            )

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
                # Éco-conception : compression/redimensionnement côté client avant
                # l'envoi réseau (le modèle infère en 224x224).
                image_bytes = _compresser_image(fichier.getvalue(), fichier.name)
                resultat = api_client.predict(image_bytes, fichier.name, token)
            # On mémorise le résultat pour qu'il survive au rerun de Streamlit.
            st.session_state.dernier_resultat = resultat
        except api_client.ApiError as erreur:
            # Traitement des codes HTTP significatifs.
            # Token expiré / invalide : on nettoie la session et on redirige.
            gerer_erreur_401(erreur)
            if erreur.status_code == 400:
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
            # Icône en SVG inline (fill blanc) plutôt qu'une directive
            # :material/eco: : à l'intérieur d'un bloc unsafe_allow_html, la
            # directive Material n'est pas interprétée et s'afficherait en texte
            # brut « :material/eco: ». Le SVG est décoratif (aria-hidden), le sens
            # est porté par le libellé « Tomate saine ».
            st.markdown(
                """
                <div style="background:#2d6a4f;color:#ffffff;border-radius:12px;
                            padding:18px 20px;display:flex;align-items:center;gap:0.6rem;">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="#ffffff" aria-hidden="true"><path d="M6.05 8.05c-2.73 2.73-2.73 7.15-.02 9.88 1.47-3.4 4.09-6.24 7.36-7.93-2.77 2.34-4.71 5.61-5.39 9.32 2.6 1.23 5.8.78 7.95-1.37C19.43 14.47 20 4 20 4S9.53 4.57 6.05 8.05z"/></svg>
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
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="#ffffff" aria-hidden="true"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>
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
