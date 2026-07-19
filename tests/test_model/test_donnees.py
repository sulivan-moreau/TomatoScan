"""Tests unitaires de src/tomatoscan/model/preprocess.py — complétude et
labellisation du dataset (compétence C12).

Périmètre : obtenir_classes_tomates(), le mapping des labels, et le
comportement face à un fichier corrompu. Le format des tensors produits par
les transforms est couvert séparément par test_preprocessing.py.

Stratégie : jamais le dataset PlantVillage réel — fixtures partagées dans
tests/test_model/conftest.py (dossier_dataset_factice, dossier_dataset_avec_
fichier_corrompu), qui génèrent une arborescence temporaire avec de vraies
petites images JPEG créées en mémoire.

Bug documenté (non corrigé, hors périmètre) : un fichier corrompu mais avec
une extension .jpg valide est collecté par ImageFolder (filtrage par
extension uniquement) ; l'erreur ne survient qu'à l'accès réel
(PIL.UnidentifiedImageError), non interceptée par le code du projet.
"""

import pytest
from PIL import UnidentifiedImageError
from torch.utils.data import Subset
from torchvision import datasets

from tests.test_model.conftest import CLASSES_AUTRES, CLASSES_TOMATE, IMAGES_PAR_CLASSE
from tomatoscan.model.preprocess import (
    TransformDataset,
    charger_dataset,
    creer_transforms,
    obtenir_classes_tomates,
)


def test_obtenir_classes_tomates_filtre_correctement(dossier_dataset_factice):
    """Seuls les dossiers dont le nom commence par 'Tomato' doivent être
    retournés — les classes non-Tomato (Pepper_bell, Potato_healthy) exclues."""
    classes = obtenir_classes_tomates(dossier_dataset_factice)

    assert set(classes) == set(CLASSES_TOMATE)
    for classe_exclue in CLASSES_AUTRES:
        assert classe_exclue not in classes


def test_obtenir_classes_tomates_dossier_introuvable(tmp_path):
    """Un dossier dataset inexistant doit lever une FileNotFoundError explicite."""
    with pytest.raises(FileNotFoundError):
        obtenir_classes_tomates(str(tmp_path / "dossier_qui_n_existe_pas"))


def test_dataset_fichier_corrompu_leve_une_erreur_non_geree(
    dossier_dataset_avec_fichier_corrompu,
):
    """Comportement réel (voir en-tête de fichier) : un fichier corrompu déguisé
    en .jpg lève PIL.UnidentifiedImageError au moment de l'accès réel, non
    interceptée par le code du projet — ce test caractérise ce comportement."""
    dataset_base = datasets.ImageFolder(
        root=dossier_dataset_avec_fichier_corrompu, transform=None
    )
    index_corrompu = next(
        i
        for i, (chemin, _) in enumerate(dataset_base.samples)
        if chemin.endswith("corrompu.jpg")
    )
    mapping = {
        dataset_base.class_to_idx[nom]: i for i, nom in enumerate(CLASSES_TOMATE)
    }
    subset = Subset(dataset_base, [index_corrompu])
    dataset_transforme = TransformDataset(
        subset, creer_transforms(augmentation=False), mapping
    )

    with pytest.raises(UnidentifiedImageError):
        dataset_transforme[0]


def test_mapping_labels_est_coherent(dossier_dataset_factice):
    """Le mapping des indices globaux ImageFolder vers les indices relatifs
    Tomato (0 à N-1) ne doit contenir aucun doublon et doit couvrir exactement
    toutes les classes Tomato présentes."""
    noms_classes = obtenir_classes_tomates(dossier_dataset_factice)
    dataset_base = datasets.ImageFolder(root=dossier_dataset_factice, transform=None)

    mapping_labels = {
        dataset_base.class_to_idx[nom]: i for i, nom in enumerate(noms_classes)
    }

    assert len(mapping_labels) == len(noms_classes) == len(CLASSES_TOMATE)
    assert sorted(mapping_labels.values()) == list(range(len(noms_classes)))
    for indice_global in mapping_labels:
        assert dataset_base.classes[indice_global].startswith("Tomato")


def test_charger_dataset_couvre_toutes_les_classes_et_toutes_les_images(
    dossier_dataset_factice,
):
    """Test de bout en bout via charger_dataset() : les labels rencontrés dans
    les dataloaders doivent couvrir exactement 0..N-1, et le total d'images
    réparties dans train+val+test doit correspondre exactement au nombre
    d'images créées (aucune image perdue ou dupliquée)."""
    dataloader_train, dataloader_val, dataloader_test, noms_classes = charger_dataset(
        dossier_dataset_factice, taille_batch=4
    )

    labels_rencontres = set()
    total = 0
    for dataloader in (dataloader_train, dataloader_val, dataloader_test):
        total += len(dataloader.dataset)
        for _, labels in dataloader:
            labels_rencontres.update(labels.tolist())

    assert labels_rencontres == set(range(len(noms_classes)))
    assert total == len(CLASSES_TOMATE) * IMAGES_PAR_CLASSE
