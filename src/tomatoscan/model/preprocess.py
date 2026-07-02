"""
Chargement et préparation du dataset PlantVillage pour l'entraînement MobileNetV2 (PyTorch).
Filtre uniquement les 10 classes Tomato, applique augmentation et normalisation ImageNet.
"""

import os

from loguru import logger
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset, Subset
from torchvision import datasets, transforms


def obtenir_classes_tomates(dossier_dataset: str) -> list[str]:
    """Retourne uniquement les dossiers qui commencent par 'Tomato'."""
    try:
        tous_les_dossiers = sorted(os.listdir(dossier_dataset))
        classes_tomates = [d for d in tous_les_dossiers if d.startswith("Tomato")]
        logger.info(
            f"{len(classes_tomates)} classes Tomate trouvées : {classes_tomates}"
        )
        return classes_tomates
    except FileNotFoundError:
        logger.error(f"Dossier dataset introuvable : {dossier_dataset}")
        raise


def creer_transforms(augmentation: bool = True):
    """
    Crée les transformations pour le dataset.

    Avec augmentation (train) :
    - RandomHorizontalFlip()
    - RandomRotation(15)
    - ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2)
    - Resize((224, 224))
    - ToTensor()
    - Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])

    Sans augmentation (val/test) :
    - Resize((224, 224))
    - ToTensor()
    - Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    """
    # Normalisation ImageNet : valeurs utilisées lors du pré-entraînement de MobileNetV2
    normalisation = transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225],
    )

    if augmentation:
        # Simule les conditions terrain : lumière variable, angles différents, photos à la main
        return transforms.Compose(
            [
                transforms.Resize((224, 224)),
                transforms.RandomHorizontalFlip(),
                transforms.RandomRotation(15),
                transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
                transforms.ToTensor(),
                normalisation,
            ]
        )
    else:
        return transforms.Compose(
            [
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                normalisation,
            ]
        )


class TransformDataset(Dataset):
    """Wrapper qui applique des transforms différentes sur un Subset existant."""

    def __init__(self, subset: Subset, transform, mapping_labels: dict):
        """Initialise avec un sous-ensemble, ses transformations et le mapping des labels."""
        self.subset = subset
        self.transform = transform
        self.mapping_labels = mapping_labels

    def __len__(self):
        return len(self.subset)

    def __getitem__(self, idx):
        image, label = self.subset[idx]
        # Remappage des labels globaux (5-14) vers les indices relatifs Tomato (0-9)
        label = self.mapping_labels[label]
        if self.transform:
            image = self.transform(image)
        return image, label


def charger_dataset(
    dossier_dataset: str,
    taille_batch: int = 32,
) -> tuple:
    """
    Charge le dataset et retourne 4 éléments :
    (dataloader_train, dataloader_val, dataloader_test, noms_classes)

    Split stratifié : 70% train / 15% val / 15% test
    Utilise train_test_split de sklearn avec stratify pour équilibrer les classes.
    """
    try:
        noms_classes = obtenir_classes_tomates(dossier_dataset)

        # Charge toutes les images sans transform (les PIL Images seront transformées ensuite)
        dataset_base = datasets.ImageFolder(root=dossier_dataset, transform=None)

        # Mapping des indices globaux ImageFolder (5-14) vers les indices relatifs Tomato (0-9)
        mapping_labels = {
            dataset_base.class_to_idx[nom]: i for i, nom in enumerate(noms_classes)
        }
        logger.info(f"Mapping labels : {mapping_labels}")

        # Collecte uniquement les indices des classes Tomato
        indices_tomato = []
        labels_tomato = []
        for i, (_, label) in enumerate(dataset_base.samples):
            nom_classe = dataset_base.classes[label]
            if nom_classe in noms_classes:
                indices_tomato.append(i)
                labels_tomato.append(label)

        # Split stratifié 70% train / 30% reste
        indices_train, indices_reste, _, labels_reste = train_test_split(
            indices_tomato,
            labels_tomato,
            test_size=0.30,
            stratify=labels_tomato,
            random_state=42,
        )

        # Coupe le reste en 15% val / 15% test
        indices_val, indices_test = train_test_split(
            indices_reste,
            test_size=0.50,
            stratify=labels_reste,
            random_state=42,
        )

        # Création des sous-ensembles avec les transforms appropriées et le mapping
        dataset_train = TransformDataset(
            Subset(dataset_base, indices_train),
            creer_transforms(augmentation=True),
            mapping_labels,
        )
        dataset_val = TransformDataset(
            Subset(dataset_base, indices_val),
            creer_transforms(augmentation=False),
            mapping_labels,
        )
        dataset_test = TransformDataset(
            Subset(dataset_base, indices_test),
            creer_transforms(augmentation=False),
            mapping_labels,
        )

        dataloader_train = DataLoader(
            dataset_train, batch_size=taille_batch, shuffle=True, num_workers=0
        )
        dataloader_val = DataLoader(
            dataset_val, batch_size=taille_batch, shuffle=False, num_workers=0
        )
        dataloader_test = DataLoader(
            dataset_test, batch_size=taille_batch, shuffle=False, num_workers=0
        )

        logger.info(
            f"Dataset chargé : {len(noms_classes)} classes, split 70/15/15 — "
            f"{len(dataset_train)} train, {len(dataset_val)} val, {len(dataset_test)} test"
        )

        return dataloader_train, dataloader_val, dataloader_test, noms_classes

    except Exception as erreur:
        logger.error(f"Erreur lors du chargement du dataset : {erreur}")
        raise


if __name__ == "__main__":
    train_loader, val_loader, test_loader, classes = charger_dataset(
        "./PlantVillage/PlantVillage/"
    )
    print(f"Classes : {classes}")
    print(f"Batches train : {len(train_loader)}")
    imgs, labels = next(iter(train_loader))
    print(f"Shape batch : {imgs.shape}")
