"""Tests unitaires de src/tomatoscan/model/preprocess.py — format des images
produites par creer_transforms() (compétence C12).

Périmètre : creer_transforms() uniquement. La complétude/labellisation du
dataset est couverte séparément par test_donnees.py.

Stratégie : jamais le dataset PlantVillage réel — chaque test construit une
image PIL en mémoire et vérifie le tensor produit.
"""

import pytest
import torch
from PIL import Image

from tomatoscan.model.preprocess import creer_transforms


def _image(taille=(300, 200), couleur=(120, 80, 40)):
    return Image.new("RGB", taille, couleur)


def test_transform_nominal_produit_un_tensor_224x224_deterministe():
    """Sortie 224x224, 3 canaux, torch.Tensor (pas PIL.Image), et déterministe
    sans augmentation (deux passages sur la même image → résultat identique)."""
    transform = creer_transforms(augmentation=False)
    image = _image(taille=(500, 137))

    resultat_1 = transform(image)
    resultat_2 = transform(image)

    assert isinstance(resultat_1, torch.Tensor)
    assert resultat_1.shape == (3, 224, 224)
    assert torch.equal(resultat_1, resultat_2)


def test_normalisation_imagenet():
    """Le tensor de sortie doit être normalisé (statistiques ImageNet), pas des
    valeurs brutes 0-255 — vérifié avec une couleur unie connue à l'avance,
    la valeur normalisée attendue étant calculable analytiquement."""
    transform = creer_transforms(augmentation=False)
    tensor = transform(_image(couleur=(120, 80, 40)))

    assert tensor.max() <= 10.0 and tensor.min() >= -10.0

    mean = [0.485, 0.456, 0.406]
    std = [0.229, 0.224, 0.225]
    valeurs_brutes = [120 / 255, 80 / 255, 40 / 255]
    for canal in range(3):
        valeur_attendue = (valeurs_brutes[canal] - mean[canal]) / std[canal]
        assert tensor[canal].mean().item() == pytest.approx(valeur_attendue, abs=0.05)


def test_transform_avec_augmentation_produit_un_tensor_valide():
    """Avec augmentation (flip/rotation/color jitter aléatoires), la forme de
    sortie doit rester (3, 224, 224) — l'aléatoire ne doit jamais casser le format."""
    transform = creer_transforms(augmentation=True)
    tensor = transform(_image())

    assert tensor.shape == (3, 224, 224)
    assert tensor.dtype == torch.float32
