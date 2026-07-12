"""
Évaluation du modèle MobileNetV2 et génération des rapports de performance (PyTorch).
Produit un rapport JSON avec métriques par classe et affiche la matrice de confusion.
"""

import glob
import json
import os
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
import torch
from loguru import logger
from sklearn.metrics import classification_report, confusion_matrix

from tomatoscan.model.train import construire_modele, selectionner_device


def charger_checkpoint(chemin_modele: str, nombre_classes: int) -> tuple:
    """
    Charge le checkpoint PyTorch.
    Retourne (modele, noms_classes, meilleure_epoch, meilleure_accuracy).
    """
    try:
        # weights_only=False nécessaire car le checkpoint contient des listes Python
        checkpoint = torch.load(chemin_modele, map_location="cpu", weights_only=False)

        modele = construire_modele(nombre_classes)
        modele.load_state_dict(checkpoint["model_state_dict"])
        modele.eval()

        noms_classes = checkpoint["class_names"]
        meilleure_epoch = checkpoint["epoch"]
        meilleure_accuracy = checkpoint["val_accuracy"]

        logger.info(
            f"Checkpoint chargé : {chemin_modele} "
            f"(epoch {meilleure_epoch}, val_acc={meilleure_accuracy:.4f})"
        )

        return modele, noms_classes, meilleure_epoch, meilleure_accuracy

    except Exception as erreur:
        logger.error(f"Impossible de charger le checkpoint : {erreur}")
        raise


def executer_inference(modele, dataloader, device) -> tuple[list, list]:
    """
    Exécute l'inférence sur tout le dataloader.
    Retourne (labels_reels, predictions).
    """
    modele.eval()
    labels_reels = []
    predictions = []

    try:
        with torch.no_grad():
            for images, labels in dataloader:
                images = images.to(device)
                sorties = modele(images)
                _, preds = torch.max(sorties, 1)

                labels_reels.extend(labels.numpy())
                predictions.extend(preds.cpu().numpy())

        logger.info(f"Inférence terminée sur {len(labels_reels)} images")
        return labels_reels, predictions

    except Exception as erreur:
        logger.error(f"Erreur pendant l'inférence : {erreur}")
        raise


def afficher_confusion_matrix(
    labels_reels: list,
    predictions: list,
    noms_classes: list,
):
    """Affiche la confusion matrix normalisée avec matplotlib."""
    # labels=range(...) force une matrice de taille fixe (len(noms_classes)) même si
    # une classe n'apparaît ni dans labels_reels ni dans predictions pour ce batch —
    # sans ça, la matrice se réduit aux classes réellement présentes et désynchronise
    # les axes (IndexError plus loin, car noms_classes garde toujours sa taille complète)
    matrice = confusion_matrix(
        labels_reels, predictions, labels=range(len(noms_classes))
    )

    # Normalisation pour afficher des proportions plutôt que des comptages bruts.
    # np.divide(..., where=...) évite la division par zéro sur une ligne à somme
    # nulle (classe absente de labels_reels pour ce batch) — ces lignes restent à 0
    # plutôt que de produire un RuntimeWarning et des NaN.
    sommes_lignes = matrice.sum(axis=1, keepdims=True)
    matrice_normalisee = np.divide(
        matrice.astype(float),
        sommes_lignes,
        out=np.zeros_like(matrice, dtype=float),
        where=sommes_lignes != 0,
    )

    fig, ax = plt.subplots(figsize=(12, 10))
    image_matrice = ax.imshow(
        matrice_normalisee, interpolation="nearest", cmap=plt.cm.Blues
    )
    plt.colorbar(image_matrice, ax=ax)

    ax.set_xticks(range(len(noms_classes)))
    ax.set_yticks(range(len(noms_classes)))
    ax.set_xticklabels(noms_classes, rotation=45, ha="right")
    ax.set_yticklabels(noms_classes)

    # Valeur dans chaque cellule, couleur adaptée au fond
    seuil = matrice_normalisee.max() / 2
    for i in range(len(noms_classes)):
        for j in range(len(noms_classes)):
            valeur = matrice_normalisee[i, j]
            couleur_texte = "white" if valeur > seuil else "black"
            ax.text(
                j, i, f"{valeur:.2f}", ha="center", va="center", color=couleur_texte
            )

    ax.set_xlabel("Classe prédite")
    ax.set_ylabel("Classe réelle")
    ax.set_title("Matrice de confusion — MobileNetV2 TomatoScan")

    plt.tight_layout()
    plt.show()
    logger.info("Matrice de confusion affichée")


def generer_rapport(
    labels_reels: list,
    predictions: list,
    noms_classes: list,
    meilleure_epoch: int,
    meilleure_accuracy: float,
    dossier_rapport: str = "./docs",
) -> str:
    """
    Génère un rapport JSON avec :
    - accuracy globale sur le test set
    - meilleure accuracy de validation et epoch correspondante
    - métriques par classe (precision, recall, f1)
    - classes sous-performantes (f1 < 0.80)
    Retourne le chemin du rapport généré.
    """
    os.makedirs(dossier_rapport, exist_ok=True)

    # labels=range(...) évite un ValueError si une classe n'apparaît ni dans
    # labels_reels ni dans predictions pour ce batch (le nombre de classes déduit
    # des données ne correspondrait alors plus à len(target_names))
    rapport_classification = classification_report(
        labels_reels,
        predictions,
        labels=range(len(noms_classes)),
        target_names=noms_classes,
        output_dict=True,
    )

    accuracy_test = rapport_classification["accuracy"]

    classes_sous_performantes = [
        classe
        for classe in noms_classes
        if rapport_classification[classe]["f1-score"] < 0.80
    ]

    rapport_complet = {
        "date": datetime.now().isoformat(),
        "modele": "MobileNetV2",
        "meilleure_epoch": meilleure_epoch,
        "meilleure_accuracy_validation": round(float(meilleure_accuracy), 4),
        "accuracy_test": round(float(accuracy_test), 4),
        "classes_sous_performantes": classes_sous_performantes,
        "rapport_classification": rapport_classification,
    }

    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    chemin_rapport = os.path.join(
        dossier_rapport, f"rapport_evaluation_{horodatage}.json"
    )

    try:
        with open(chemin_rapport, "w", encoding="utf-8") as fichier:
            json.dump(rapport_complet, fichier, indent=2, ensure_ascii=False)

        logger.info(f"Rapport sauvegardé : {chemin_rapport}")
        logger.info(f"Accuracy test : {accuracy_test:.4f}")

        if classes_sous_performantes:
            logger.warning(
                f"Classes sous-performantes (F1 < 80%) : {classes_sous_performantes}"
            )

        return chemin_rapport

    except Exception as erreur:
        logger.error(f"Erreur lors de la génération du rapport : {erreur}")
        raise


if __name__ == "__main__":
    from tomatoscan.model.preprocess import charger_dataset

    _, _, test_loader, classes = charger_dataset("./PlantVillage/PlantVillage/")

    # Trouve automatiquement le checkpoint le plus récent dans ./models/
    checkpoints = glob.glob("./models/mobilenetv2_best_*.pt")
    if not checkpoints:
        raise FileNotFoundError("Aucun checkpoint trouvé dans ./models/")
    chemin_modele = max(checkpoints)

    modele, noms_classes, meilleure_epoch, meilleure_accuracy = charger_checkpoint(
        chemin_modele, len(classes)
    )

    device = selectionner_device()
    modele = modele.to(device)

    # Évaluation sur ds_test — données jamais vues pendant l'entraînement ni le monitoring
    labels_reels, predictions = executer_inference(modele, test_loader, device)

    chemin_rapport = generer_rapport(
        labels_reels,
        predictions,
        noms_classes,
        meilleure_epoch,
        meilleure_accuracy,
    )
    print(f"Rapport généré : {chemin_rapport}")
    afficher_confusion_matrix(labels_reels, predictions, noms_classes)
