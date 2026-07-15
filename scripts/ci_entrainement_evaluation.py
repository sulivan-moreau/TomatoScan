"""Script d'orchestration CI — entraînement + évaluation réels sur un mini-dataset.

Utilisé par .github/workflows/ci-model.yml (issue #22, compétence C13) pour prouver
que la chaîne data → preprocessing → entraînement → évaluation → rapport s'exécute
sans erreur technique, dans les contraintes de la CI (pas de GPU, dataset complet
absent du dépôt). N'utilise QUE les fonctions réelles de train.py/evaluate.py —
aucun mock ici, contrairement aux tests unitaires de l'issue #19 (tests/test_model/).

N'a pas vocation à produire un modèle utilisable : le mini-dataset (32 images, 4
classes) et le nombre d'epochs (2) sont bien trop réduits pour un entraînement
sérieux — c'est un test de fonctionnement du pipeline, pas une évaluation de
performance. Aucun seuil d'accuracy n'est vérifié par ce script.

Usage : uv run python scripts/ci_entrainement_evaluation.py
Variables d'environnement (toutes non sensibles, avec défauts raisonnables) :
    CI_DATASET_PATH   — dossier du mini-dataset (défaut : tests/fixtures/mini_dataset)
    CI_MODEL_DIR      — dossier de sortie pour le checkpoint (défaut : ci_artifacts/models)
    CI_REPORT_DIR     — dossier de sortie pour le rapport JSON (défaut : ci_artifacts/reports)
    CI_EPOCHS         — nombre d'epochs (défaut : 2)
    CI_BATCH_SIZE     — taille de batch (défaut : 4, adapté à un mini-dataset de 32 images)
"""

import json
import os
import sys

from loguru import logger

from tomatoscan.model.evaluate import (
    charger_checkpoint,
    executer_inference,
    generer_rapport,
    journaliser_declenchement,
    verifier_seuil_reentrainement,
)
from tomatoscan.model.preprocess import charger_dataset
from tomatoscan.model.train import entrainer_modele, selectionner_device

DATASET_PATH = os.getenv("CI_DATASET_PATH", "tests/fixtures/mini_dataset")
MODEL_DIR = os.getenv("CI_MODEL_DIR", "ci_artifacts/models")
REPORT_DIR = os.getenv("CI_REPORT_DIR", "ci_artifacts/reports")
EPOCHS = int(os.getenv("CI_EPOCHS", "2"))
BATCH_SIZE = int(os.getenv("CI_BATCH_SIZE", "4"))


def main() -> None:
    logger.info(f"=== Pipeline CI modèle — dataset : {DATASET_PATH} ===")

    if not os.path.isdir(DATASET_PATH):
        logger.error(f"Mini-dataset introuvable : {DATASET_PATH}")
        sys.exit(1)

    logger.info("--- Étape 1/3 : chargement + préparation des données ---")
    dataloader_train, dataloader_val, dataloader_test, noms_classes = charger_dataset(
        DATASET_PATH, taille_batch=BATCH_SIZE
    )
    logger.info(f"{len(noms_classes)} classes détectées : {noms_classes}")

    logger.info(f"--- Étape 2/3 : entraînement réel ({EPOCHS} epoch(s)) ---")
    chemin_modele = entrainer_modele(
        dataloader_train,
        dataloader_val,
        noms_classes,
        epochs=EPOCHS,
        dossier_modele=MODEL_DIR,
    )
    logger.info(f"Checkpoint entraîné : {chemin_modele}")

    logger.info("--- Étape 3/3 : évaluation sur le jeu de test ---")
    modele, noms_classes_ckpt, meilleure_epoch, meilleure_accuracy = charger_checkpoint(
        chemin_modele, len(noms_classes)
    )
    device = selectionner_device()
    modele = modele.to(device)

    labels_reels, predictions = executer_inference(modele, dataloader_test, device)

    chemin_rapport = generer_rapport(
        labels_reels,
        predictions,
        noms_classes_ckpt,
        meilleure_epoch,
        meilleure_accuracy,
        dossier_rapport=REPORT_DIR,
    )
    logger.info(f"Rapport généré : {chemin_rapport}")

    # Vérification du seuil de réentraînement (C11) — relit accuracy_test depuis
    # le rapport tout juste écrit plutôt que de la recalculer, pour ne jamais
    # diverger de la valeur qui y est réellement consignée.
    with open(chemin_rapport, encoding="utf-8") as fichier_rapport:
        accuracy_test = json.load(fichier_rapport)["accuracy_test"]
    declenche = verifier_seuil_reentrainement(accuracy_test)
    journaliser_declenchement(accuracy_test, declenche, dossier_rapport=REPORT_DIR)

    logger.info("=== Pipeline CI modèle terminé sans erreur ===")


if __name__ == "__main__":
    main()
