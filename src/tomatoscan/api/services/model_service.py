"""
Service de prédiction MobileNetV2 — chargement unique du modèle au démarrage (singleton).
Expose predire(image_bytes) pour l'endpoint POST /predict.
"""

import io
import os

import torch
from loguru import logger
from PIL import Image
from torchvision import transforms

from tomatoscan.model.train import construire_modele

# Chemin du modèle — configurable via MODEL_PATH dans .env
CHEMIN_MODELE_PAR_DEFAUT = "./models/mobilenetv2_best_20260624_161841.pt"

# État global du service (singleton)
_etat: dict = {
    "modele": None,
    "noms_classes": None,
    "device": None,
}

# Transformations identiques à celles utilisées pendant l'évaluation (sans augmentation)
_transform = transforms.Compose(
    [
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ]
)


def initialiser_modele() -> None:
    """
    Charge le modèle MobileNetV2 depuis le checkpoint.
    À appeler une seule fois au démarrage de l'application (lifespan).
    """
    chemin = os.getenv("MODEL_PATH", CHEMIN_MODELE_PAR_DEFAUT)

    if not os.path.exists(chemin):
        logger.error(
            f"Checkpoint introuvable : {chemin} — endpoint /predict retournera 503"
        )
        return

    try:
        # Sélection du device : MPS (Apple Silicon) ou CPU
        if torch.backends.mps.is_available():
            device = torch.device("mps")
        else:
            device = torch.device("cpu")

        checkpoint = torch.load(chemin, map_location=device, weights_only=False)
        noms_classes = checkpoint["class_names"]

        modele = construire_modele(len(noms_classes))
        modele.load_state_dict(checkpoint["model_state_dict"])
        modele.to(device)
        modele.eval()

        _etat["modele"] = modele
        _etat["noms_classes"] = noms_classes
        _etat["device"] = device

        logger.info(
            f"Modèle chargé : {chemin} — "
            f"{len(noms_classes)} classes sur {device} "
            f"(epoch {checkpoint['epoch']}, val_acc={checkpoint['val_accuracy']:.4f})"
        )

    except Exception as erreur:
        logger.error(f"Erreur lors du chargement du modèle : {erreur}")


def modele_disponible() -> bool:
    """Retourne True si le modèle est chargé et prêt."""
    return _etat["modele"] is not None


def predire(image_bytes: bytes) -> tuple[str, float]:
    """
    Prédit la maladie sur une image fournie en bytes.
    Retourne (nom_classe, score_confiance).
    Lève RuntimeError si le modèle n'est pas chargé.
    """
    if not modele_disponible():
        raise RuntimeError("Modèle non disponible")

    try:
        # Décodage et préparation de l'image
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        tenseur = _transform(image).unsqueeze(0).to(_etat["device"])

        with torch.no_grad():
            sorties = _etat["modele"](tenseur)
            probas = torch.softmax(sorties, dim=1)
            confiance, indice = torch.max(probas, dim=1)

        classe = _etat["noms_classes"][indice.item()]
        score = round(confiance.item(), 4)

        logger.info(f"Prédiction : {classe} ({score:.2%})")
        return classe, score

    except Exception as erreur:
        logger.error(f"Erreur pendant la prédiction : {erreur}")
        raise
