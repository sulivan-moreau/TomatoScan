"""Fixtures partagées pour les tests du modèle (tests/test_model/).

Fournit un dataset factice minimal — jamais le vrai PlantVillage — pour tester
le pipeline de préparation des données (preprocess.py) sans dépendance externe.
"""

import os

import pytest
from PIL import Image

# Classes Tomato factices (le préfixe "Tomato" est ce que le code filtre réellement)
CLASSES_TOMATE = ["Tomato_healthy", "Tomato_Late_blight", "Tomato_Early_blight"]
# Classes non-Tomato factices, pour vérifier qu'elles sont bien exclues
CLASSES_AUTRES = ["Pepper_bell", "Potato_healthy"]

# Nombre d'images par classe — suffisant pour que train_test_split(stratify=...)
# puisse répartir chaque classe sur les 3 splits (train/val/test) sans erreur
IMAGES_PAR_CLASSE = 6


def _creer_image_jpeg(chemin: str, taille=(50, 50), couleur=(120, 160, 90)) -> None:
    """Crée une vraie petite image JPEG valide en mémoire (PIL), écrite sur disque."""
    Image.new("RGB", taille, couleur).save(chemin)


@pytest.fixture
def dossier_dataset_factice(tmp_path) -> str:
    """Crée un dossier dataset factice complet : classes Tomato_* + classes non-Tomato,
    chacune peuplée de vraies petites images JPEG générées en mémoire (PIL.Image.new).

    Structure :
        <tmp>/dataset_factice/Tomato_healthy/image_0.jpg ... image_5.jpg
        <tmp>/dataset_factice/Tomato_Late_blight/...
        <tmp>/dataset_factice/Tomato_Early_blight/...
        <tmp>/dataset_factice/Pepper_bell/...          (non-Tomato, doit être exclu)
        <tmp>/dataset_factice/Potato_healthy/...       (non-Tomato, doit être exclu)

    Retourne le chemin (str) du dossier racine, prêt à passer à charger_dataset()
    ou obtenir_classes_tomates(). Jamais de dépendance au dataset PlantVillage réel.
    """
    racine = tmp_path / "dataset_factice"
    for classe in CLASSES_TOMATE + CLASSES_AUTRES:
        dossier_classe = racine / classe
        dossier_classe.mkdir(parents=True)
        for i in range(IMAGES_PAR_CLASSE):
            _creer_image_jpeg(str(dossier_classe / f"image_{i}.jpg"))
    return str(racine)


@pytest.fixture
def dossier_dataset_avec_fichier_corrompu(dossier_dataset_factice) -> str:
    """Réutilise dossier_dataset_factice et y ajoute un fichier corrompu (bytes
    invalides déguisés en .jpg) dans la première classe Tomato — pour tester le
    comportement réel du chargement face à une image illisible."""
    chemin_corrompu = os.path.join(
        dossier_dataset_factice, CLASSES_TOMATE[0], "corrompu.jpg"
    )
    with open(chemin_corrompu, "wb") as fichier:
        fichier.write(b"ceci n'est pas une image valide, juste des octets quelconques")
    return dossier_dataset_factice
