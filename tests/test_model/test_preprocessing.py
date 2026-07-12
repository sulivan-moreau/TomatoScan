"""Tests unitaires de src/tomatoscan/model/preprocess.py — format des images (issue #19/#20,
compétence C12).

Périmètre : creer_transforms() uniquement — le format de sortie des transformations
appliquées à une image PIL. La complétude/labellisation du dataset (obtenir_classes_tomates,
mapping des labels, gestion des fichiers corrompus) est couverte séparément par
test_donnees.py. Les tests d'entraînement/évaluation (train.py/evaluate.py) ne sont
pas concernés — voir tests/test_model/test_train.py et test_evaluate.py.

Stratégie : jamais le dataset PlantVillage réel — chaque test construit une image
PIL en mémoire (PIL.Image.new) de taille/mode arbitraire, et vérifie le tensor produit
par creer_transforms(). Aucun fichier disque nécessaire pour ce fichier de tests.

Bug documenté (non corrigé — hors périmètre, preprocess.py non modifié) :
creer_transforms() ne fait AUCUNE conversion vers RGB avant Normalize(mean=[3 valeurs]).
Testé empiriquement avant d'écrire ces tests : passer une image en niveaux de gris (mode
"L", 1 canal) ou RGBA (4 canaux) directement à creer_transforms() lève un RuntimeError
("doesn't match the broadcast shape" / "size of tensor a (4) must match... (3)"), pas une
conversion silencieuse vers 3 canaux. En production ce n'est pas un problème observable :
torchvision.datasets.folder.default_loader (utilisé en interne par ImageFolder, donc par
charger_dataset()) fait systématiquement `.convert("RGB")` AVANT que creer_transforms()
ne voie l'image — la fonction n'est donc jamais appelée directement sur une image non-RGB
dans le pipeline réel. Mais creer_transforms() n'est pas robuste en isolation, et le
deviendrait si elle était un jour appelée hors de ce pipeline précis (ex. un futur script
d'inférence qui ouvrirait une image sans passer par ImageFolder).
"""

import pytest
import torch
from PIL import Image

from tomatoscan.model.preprocess import creer_transforms


def _image(taille=(300, 200), mode="RGB", couleur=(120, 80, 40)):
    """Construit une image PIL en mémoire — jamais de fichier disque, jamais PlantVillage."""
    return Image.new(mode, taille, couleur)


# --- Format de sortie -----------------------------------------------------------


def test_resize_224x224():
    """Une image de taille arbitraire doit ressortir en 224x224 après transform."""
    transform = creer_transforms(augmentation=False)
    tensor = transform(_image(taille=(500, 137)))
    assert tensor.shape[1] == 224
    assert tensor.shape[2] == 224


def test_type_de_sortie_est_tensor():
    """La sortie doit être un torch.Tensor, jamais une PIL.Image."""
    transform = creer_transforms(augmentation=False)
    resultat = transform(_image())
    assert isinstance(resultat, torch.Tensor)
    assert not isinstance(resultat, Image.Image)


def test_canaux_rgb_image_source_rgb():
    """Cas nominal : une image source RGB doit produire un tensor à 3 canaux."""
    transform = creer_transforms(augmentation=False)
    tensor = transform(_image(mode="RGB"))
    assert tensor.shape[0] == 3


def test_canaux_rgb_image_source_niveaux_de_gris_non_geree():
    """Bug documenté en en-tête de fichier : creer_transforms() ne convertit pas une
    image en niveaux de gris (mode "L", 1 canal) vers RGB — elle plante au lieu de
    produire un tensor à 3 canaux. Ce test caractérise ce comportement réel."""
    transform = creer_transforms(augmentation=False)

    with pytest.raises(RuntimeError):
        transform(_image(mode="L", couleur=128))


def test_canaux_rgb_image_source_rgba_non_geree():
    """Bug documenté en en-tête de fichier : idem pour une image RGBA (4 canaux) —
    creer_transforms() plante au lieu de convertir vers 3 canaux RGB."""
    transform = creer_transforms(augmentation=False)

    with pytest.raises(RuntimeError):
        transform(_image(mode="RGBA", couleur=(10, 20, 30, 255)))


# --- Normalisation ImageNet -------------------------------------------------------


def test_normalisation_imagenet():
    """Le tensor de sortie doit être normalisé (statistiques ImageNet), pas des
    valeurs brutes 0-255. Vérifié avec une image de couleur unie et connue à
    l'avance : la valeur normalisée attendue est calculable analytiquement."""
    transform = creer_transforms(augmentation=False)
    # Couleur unie connue : R=120, G=80, B=40 (sur 0-255)
    tensor = transform(_image(couleur=(120, 80, 40)))

    # Le tensor ne doit surtout pas contenir de valeurs brutes 0-255
    assert tensor.max() <= 10.0
    assert tensor.min() >= -10.0

    mean = [0.485, 0.456, 0.406]
    std = [0.229, 0.224, 0.225]
    valeurs_brutes = [120 / 255, 80 / 255, 40 / 255]

    for canal in range(3):
        valeur_attendue = (valeurs_brutes[canal] - mean[canal]) / std[canal]
        # Une image de couleur unie donne un tensor constant par canal (aux bords
        # de redimensionnement/interpolation près, négligeables ici) — on compare
        # la valeur moyenne du canal à la valeur normalisée calculée analytiquement
        valeur_obtenue = tensor[canal].mean().item()
        assert valeur_obtenue == pytest.approx(valeur_attendue, abs=0.05)


# --- Déterminisme / augmentation --------------------------------------------------


def test_transform_sans_augmentation_est_deterministe():
    """Deux passages sur la même image (sans augmentation) doivent donner un
    résultat strictement identique — pas de composante aléatoire."""
    transform = creer_transforms(augmentation=False)
    image = _image()

    resultat_1 = transform(image)
    resultat_2 = transform(image)

    assert torch.equal(resultat_1, resultat_2)


def test_transform_avec_augmentation_produit_un_tensor_valide():
    """Avec augmentation (flip/rotation/color jitter aléatoires), la forme de
    sortie doit rester (3, 224, 224) — l'aléatoire ne doit jamais casser le format."""
    transform = creer_transforms(augmentation=True)
    tensor = transform(_image())

    assert isinstance(tensor, torch.Tensor)
    assert tensor.shape == (3, 224, 224)
    assert tensor.dtype == torch.float32
