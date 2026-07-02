"""
Entraînement du modèle MobileNetV2 avec transfer learning (PyTorch).
Support GPU Apple Silicon M5 via MPS.
Sauvegarde le meilleur modèle avec early stopping.
"""

import csv
import os
from datetime import datetime

import torch
import torch.nn as nn
from loguru import logger
from torchvision import models


def selectionner_device() -> torch.device:
    """Retourne MPS si disponible (Mac M5), sinon CPU."""
    if torch.backends.mps.is_available():
        device = torch.device("mps")
        logger.info("Device sélectionné : MPS (Apple Silicon)")
    else:
        device = torch.device("cpu")
        logger.info("Device sélectionné : CPU")
    return device


def construire_modele(nombre_classes: int) -> nn.Module:
    """
    Construit MobileNetV2 avec transfer learning.
    - Base MobileNetV2 pré-entraîné ImageNet, toutes les couches gelées
    - Classifier final remplacé pour nombre_classes classes
    """
    modele = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.IMAGENET1K_V1)

    # Geler toutes les couches de la base — on n'entraîne que le classifier
    for param in modele.parameters():
        param.requires_grad = False

    # Remplacer le classifier final (1280 → nombre_classes)
    nb_features = modele.classifier[1].in_features
    modele.classifier = nn.Sequential(
        nn.Dropout(0.2),
        nn.Linear(nb_features, nombre_classes),
    )

    nb_total = sum(p.numel() for p in modele.parameters())
    nb_entrainables = sum(p.numel() for p in modele.parameters() if p.requires_grad)
    logger.info(
        f"Modèle construit : {nb_total:,} paramètres total, {nb_entrainables:,} entraînables"
    )

    return modele


def executer_epoch(
    modele: nn.Module,
    dataloader,
    criterion,
    device: torch.device,
    entrainement: bool,
    optimizer=None,
) -> tuple[float, float]:
    """
    Exécute une epoch complète (train ou validation).
    Retourne (loss_moyenne, accuracy).
    """
    modele.train(entrainement)

    perte_totale = 0.0
    nb_corrects = 0
    nb_total = 0

    for images, labels in dataloader:
        images = images.to(device)
        labels = labels.to(device).long()

        with torch.set_grad_enabled(entrainement):
            sorties = modele(images)
            perte = criterion(sorties, labels)

            if entrainement:
                optimizer.zero_grad()
                perte.backward()
                optimizer.step()

        perte_totale += perte.item() * images.size(0)
        _, predictions = torch.max(sorties, 1)
        nb_corrects += (predictions == labels).sum().item()
        nb_total += images.size(0)

    loss_moyenne = perte_totale / nb_total
    accuracy = nb_corrects / nb_total

    return loss_moyenne, accuracy


def sauvegarder_historique(
    historique: list[dict], dossier_modele: str, horodatage: str
) -> str:
    """
    Sauvegarde l'historique d'entraînement (loss/accuracy par epoch) dans un CSV.
    Retourne le chemin du fichier créé.
    """
    chemin_csv = os.path.join(dossier_modele, f"historique_{horodatage}.csv")
    colonnes = ["epoch", "train_loss", "train_accuracy", "val_loss", "val_accuracy"]

    try:
        with open(chemin_csv, "w", newline="", encoding="utf-8") as fichier:
            writer = csv.DictWriter(fichier, fieldnames=colonnes)
            writer.writeheader()
            writer.writerows(historique)

        logger.info(f"Historique sauvegardé : {chemin_csv}")
        return chemin_csv

    except Exception as erreur:
        logger.error(f"Erreur lors de la sauvegarde de l'historique : {erreur}")
        raise


def entrainer_modele(
    dataloader_train,
    dataloader_val,
    noms_classes: list,
    epochs: int = 20,
    dossier_modele: str = "./models",
) -> str:
    """
    Entraîne le modèle et sauvegarde le meilleur checkpoint.
    Retourne le chemin du meilleur modèle sauvegardé.

    Inclut :
    - Early stopping (patience=3 sur val_loss)
    - Sauvegarde du meilleur modèle à chaque amélioration
    - Historique CSV par epoch
    - Logs loguru à chaque epoch

    Format du checkpoint :
    {
        "epoch": int,
        "model_state_dict": state_dict,
        "val_accuracy": float,
        "class_names": list[str],
    }
    """
    os.makedirs(dossier_modele, exist_ok=True)

    device = selectionner_device()
    nombre_classes = len(noms_classes)
    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    chemin_meilleur_modele = os.path.join(
        dossier_modele, f"mobilenetv2_best_{horodatage}.pt"
    )

    modele = construire_modele(nombre_classes).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(modele.classifier.parameters(), lr=0.001)
    # Réduit le learning rate de moitié tous les 5 epochs pour affiner la convergence
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=5, gamma=0.5)

    meilleure_val_loss = float("inf")
    epochs_sans_amelioration = 0
    historique = []

    try:
        for epoch in range(1, epochs + 1):
            train_loss, train_acc = executer_epoch(
                modele,
                dataloader_train,
                criterion,
                device,
                entrainement=True,
                optimizer=optimizer,
            )
            val_loss, val_acc = executer_epoch(
                modele,
                dataloader_val,
                criterion,
                device,
                entrainement=False,
            )

            logger.info(
                f"Epoch {epoch}/{epochs} — "
                f"train_loss: {train_loss:.4f} train_acc: {train_acc:.4f} — "
                f"val_loss: {val_loss:.4f} val_acc: {val_acc:.4f}"
            )

            historique.append(
                {
                    "epoch": epoch,
                    "train_loss": round(train_loss, 4),
                    "train_accuracy": round(train_acc, 4),
                    "val_loss": round(val_loss, 4),
                    "val_accuracy": round(val_acc, 4),
                }
            )

            # Sauvegarde si val_loss s'améliore
            if val_loss < meilleure_val_loss:
                meilleure_val_loss = val_loss
                epochs_sans_amelioration = 0

                torch.save(
                    {
                        "epoch": epoch,
                        "model_state_dict": modele.state_dict(),
                        "val_accuracy": val_acc,
                        "class_names": noms_classes,
                    },
                    chemin_meilleur_modele,
                )

                logger.info(f"Meilleur modèle sauvegardé (val_loss: {val_loss:.4f})")
            else:
                epochs_sans_amelioration += 1
                logger.info(
                    f"Pas d'amélioration depuis {epochs_sans_amelioration} epoch(s)"
                )

            scheduler.step()

            # Arrêt anticipé si pas d'amélioration pendant 3 epochs
            if epochs_sans_amelioration >= 3:
                logger.info(f"Early stopping déclenché à l'epoch {epoch}")
                break

        sauvegarder_historique(historique, dossier_modele, horodatage)
        logger.info(
            f"Entraînement terminé — meilleur modèle : {chemin_meilleur_modele}"
        )

    except Exception as erreur:
        logger.error(f"Erreur pendant l'entraînement : {erreur}")
        raise

    return chemin_meilleur_modele


if __name__ == "__main__":
    from tomatoscan.model.preprocess import charger_dataset

    train_loader, val_loader, _, classes = charger_dataset(
        "./PlantVillage/PlantVillage/"
    )
    chemin = entrainer_modele(train_loader, val_loader, classes, epochs=20)
    print(f"Modèle sauvegardé : {chemin}")
