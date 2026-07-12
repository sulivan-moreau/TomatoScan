"""Tests unitaires de src/tomatoscan/model/preprocess.py — complétude et labellisation
du dataset (issue #19/#20, compétence C12).

Périmètre : obtenir_classes_tomates(), le mapping des labels et le comportement face
à un fichier corrompu (charger_dataset() / TransformDataset). Le format des tensors
produits par les transforms est couvert séparément par test_preprocessing.py.

Stratégie : jamais le dataset PlantVillage réel — fixtures partagées dans
tests/test_model/conftest.py (dossier_dataset_factice, dossier_dataset_avec_fichier_corrompu),
qui génèrent une arborescence temporaire (tmp_path) avec de vraies petites images JPEG
créées en mémoire (PIL.Image.new). 6 images par classe : suffisant pour que le split
stratifié 70/15/15 de charger_dataset() (train_test_split avec stratify=) puisse
répartir chaque classe sur les 3 sous-ensembles sans erreur sklearn.

Bug documenté (non corrigé — hors périmètre, preprocess.py non modifié) : voir
test_dataset_fichier_corrompu_leve_une_erreur_non_geree ci-dessous. Comportement réel
vérifié empiriquement avant d'écrire ce test (pas une supposition) : un fichier corrompu
mais avec une extension .jpg valide est bien collecté par torchvision.datasets.ImageFolder
(le filtrage ne porte que sur l'extension, jamais sur le contenu), et l'erreur ne survient
que lors de l'accès réel à l'image (TransformDataset.__getitem__ → pil_loader → PIL lève
PIL.UnidentifiedImageError). Cette exception n'est PAS interceptée par le code du projet
(ni try/except dédié, ni log loguru) — elle remonte telle quelle. Le message PIL
("cannot identify image file ...") reste compréhensible, mais rien dans preprocess.py
ne l'anticipe ou ne l'enrichit.
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


# --- obtenir_classes_tomates ------------------------------------------------------


def test_obtenir_classes_tomates_filtre_correctement(dossier_dataset_factice):
    """Seuls les dossiers dont le nom commence par 'Tomato' doivent être retournés,
    les classes non-Tomato (Pepper_bell, Potato_healthy) doivent être exclues."""
    classes = obtenir_classes_tomates(dossier_dataset_factice)

    assert set(classes) == set(CLASSES_TOMATE)
    for classe_exclue in CLASSES_AUTRES:
        assert classe_exclue not in classes


def test_obtenir_classes_tomates_dossier_introuvable(tmp_path):
    """Un dossier dataset inexistant doit lever une FileNotFoundError explicite."""
    dossier_absent = str(tmp_path / "dossier_qui_n_existe_pas")

    with pytest.raises(FileNotFoundError):
        obtenir_classes_tomates(dossier_absent)


def test_charger_dataset_relance_l_exception_si_dossier_introuvable(tmp_path):
    """charger_dataset() doit logger puis relancer l'erreur si le dossier dataset
    n'existe pas — pas l'avaler silencieusement (bloc except de charger_dataset)."""
    dossier_absent = str(tmp_path / "dossier_qui_n_existe_pas")

    with pytest.raises(FileNotFoundError):
        charger_dataset(dossier_absent)


# --- Fichier corrompu --------------------------------------------------------------


def test_dataset_fichier_corrompu_leve_une_erreur_non_geree(
    dossier_dataset_avec_fichier_corrompu,
):
    """Comportement réel (voir en-tête de fichier) : un fichier corrompu déguisé en
    .jpg est collecté par ImageFolder (filtrage par extension uniquement), puis lève
    PIL.UnidentifiedImageError au moment de l'accès réel — non intercepté par le code
    du projet. Ce test caractérise ce comportement, il ne le "corrige" pas."""
    dataset_base = datasets.ImageFolder(root=dossier_dataset_avec_fichier_corrompu, transform=None)

    # Retrouve l'index du fichier corrompu dans dataset_base.samples
    index_corrompu = next(
        i for i, (chemin, _) in enumerate(dataset_base.samples) if chemin.endswith("corrompu.jpg")
    )

    mapping = {
        dataset_base.class_to_idx[nom]: i for i, nom in enumerate(CLASSES_TOMATE)
    }
    subset = Subset(dataset_base, [index_corrompu])
    dataset_transforme = TransformDataset(subset, creer_transforms(augmentation=False), mapping)

    with pytest.raises(UnidentifiedImageError):
        dataset_transforme[0]


def test_dataset_image_valide_a_cote_du_fichier_corrompu_se_charge_normalement(
    dossier_dataset_avec_fichier_corrompu,
):
    """Complément du test précédent : les images valides du même dossier que le
    fichier corrompu doivent continuer à se charger normalement (le problème est
    localisé au fichier corrompu, pas à tout le dossier)."""
    dataset_base = datasets.ImageFolder(root=dossier_dataset_avec_fichier_corrompu, transform=None)

    index_valide = next(
        i
        for i, (chemin, _) in enumerate(dataset_base.samples)
        if chemin.endswith("image_0.jpg") and CLASSES_TOMATE[0] in chemin
    )

    mapping = {
        dataset_base.class_to_idx[nom]: i for i, nom in enumerate(CLASSES_TOMATE)
    }
    subset = Subset(dataset_base, [index_valide])
    dataset_transforme = TransformDataset(subset, creer_transforms(augmentation=False), mapping)

    image, label = dataset_transforme[0]
    assert image.shape == (3, 224, 224)
    assert label == 0


# --- Mapping des labels -------------------------------------------------------------


def test_mapping_labels_est_coherent(dossier_dataset_factice):
    """Le mapping des indices globaux ImageFolder vers les indices relatifs Tomato
    (0 à N-1) ne doit contenir aucun doublon et doit couvrir exactement toutes les
    classes Tomato présentes — reproduit la logique exacte de charger_dataset()."""
    noms_classes = obtenir_classes_tomates(dossier_dataset_factice)
    dataset_base = datasets.ImageFolder(root=dossier_dataset_factice, transform=None)

    mapping_labels = {
        dataset_base.class_to_idx[nom]: i for i, nom in enumerate(noms_classes)
    }

    # Autant d'entrées dans le mapping que de classes Tomato — pas de doublon de clé
    assert len(mapping_labels) == len(noms_classes) == len(CLASSES_TOMATE)

    # Les valeurs (indices relatifs) doivent couvrir exactement 0..N-1, sans doublon
    valeurs = sorted(mapping_labels.values())
    assert valeurs == list(range(len(noms_classes)))

    # Les clés (indices globaux ImageFolder) doivent toutes être des classes Tomato
    for indice_global in mapping_labels:
        nom_classe_globale = dataset_base.classes[indice_global]
        assert nom_classe_globale.startswith("Tomato")


def test_aucun_label_manquant(dossier_dataset_factice):
    """Chaque classe Tomato présente dans le dossier factice doit avoir au moins un
    label mappé — aucune classe orpheline sans indice relatif."""
    noms_classes = obtenir_classes_tomates(dossier_dataset_factice)
    dataset_base = datasets.ImageFolder(root=dossier_dataset_factice, transform=None)

    mapping_labels = {
        dataset_base.class_to_idx[nom]: i for i, nom in enumerate(noms_classes)
    }

    for nom_classe in noms_classes:
        indice_global = dataset_base.class_to_idx[nom_classe]
        assert indice_global in mapping_labels, f"{nom_classe} n'a aucun label mappé"


def test_mapping_labels_via_charger_dataset_couvre_toutes_les_classes(
    dossier_dataset_factice,
):
    """Test de bout en bout via charger_dataset() (pas juste la logique reproduite) :
    les labels rencontrés dans les dataloaders doivent couvrir exactement 0..N-1,
    sans classe manquante ni index hors bornes."""
    dataloader_train, dataloader_val, dataloader_test, noms_classes = charger_dataset(
        dossier_dataset_factice, taille_batch=4
    )

    labels_rencontres = set()
    for dataloader in (dataloader_train, dataloader_val, dataloader_test):
        for _, labels in dataloader:
            labels_rencontres.update(labels.tolist())

    assert labels_rencontres == set(range(len(noms_classes)))
    assert len(noms_classes) == len(CLASSES_TOMATE)


def test_charger_dataset_repartit_bien_toutes_les_images(dossier_dataset_factice):
    """Le total d'images réparties dans train+val+test doit correspondre exactement
    au nombre d'images Tomato créées par la fixture (aucune image perdue ou dupliquée)."""
    dataloader_train, dataloader_val, dataloader_test, noms_classes = charger_dataset(
        dossier_dataset_factice, taille_batch=4
    )

    total = len(dataloader_train.dataset) + len(dataloader_val.dataset) + len(dataloader_test.dataset)
    assert total == len(CLASSES_TOMATE) * IMAGES_PAR_CLASSE
