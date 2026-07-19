"""Tests unitaires de src/tomatoscan/model/evaluate.py (compétence C12).

Périmètre : evaluate.py uniquement. Un test nominal par fonction, plus les 2
régressions de bugs réels trouvés et corrigés pendant l'écriture des tests
(classe absente des labels réels/prédits → confusion_matrix()/
classification_report() plantaient sans `labels=range(...)` explicite).

Stratégie de mock : charger_checkpoint()/executer_inference() mockent
torch.load/construire_modele/le modèle — aucun poids MobileNetV2 réel chargé.
generer_rapport()/afficher_confusion_matrix() utilisent le vrai calcul
scikit-learn sur des labels connus à l'avance (c'est ce qui doit être vérifié
mathématiquement, donc pas mocké).
"""

import json
from unittest.mock import MagicMock, patch

import torch

from tomatoscan.model.evaluate import (
    SEUIL_ACCURACY_REENTRAINEMENT,
    afficher_confusion_matrix,
    charger_checkpoint,
    executer_inference,
    generer_rapport,
    journaliser_declenchement,
    verifier_seuil_reentrainement,
)

NOMS_CLASSES = [f"classe_{i}" for i in range(10)]


@patch("tomatoscan.model.evaluate.construire_modele")
@patch("tomatoscan.model.evaluate.torch.load")
def test_charger_checkpoint_extrait_les_bons_champs(
    mock_torch_load, mock_construire_modele
):
    faux_checkpoint = {
        "model_state_dict": {"poids": "fictifs"},
        "class_names": NOMS_CLASSES,
        "epoch": 13,
        "val_accuracy": 0.9455,
    }
    mock_torch_load.return_value = faux_checkpoint
    faux_modele = MagicMock()
    mock_construire_modele.return_value = faux_modele

    modele, noms_classes, meilleure_epoch, meilleure_accuracy = charger_checkpoint(
        "chemin/fictif.pt", nombre_classes=10
    )

    assert modele is faux_modele
    assert noms_classes == NOMS_CLASSES
    assert meilleure_epoch == 13
    assert meilleure_accuracy == 0.9455


def test_executer_inference_collecte_labels_reels_et_predictions():
    """Les labels réels et prédictions retournés doivent correspondre exactement
    aux tenseurs fournis et aux logits (connus à l'avance) du modèle mocké."""
    dataloader = [
        (torch.randn(2, 3, 4, 4), torch.tensor([0, 1])),
        (torch.randn(2, 3, 4, 4), torch.tensor([2, 0])),
    ]
    logits_lot_1 = torch.tensor([[5.0, 0.0, 0.0], [0.0, 5.0, 0.0]])
    logits_lot_2 = torch.tensor([[0.0, 0.0, 5.0], [0.0, 0.0, 5.0]])
    modele = MagicMock()
    modele.side_effect = [logits_lot_1, logits_lot_2]

    labels_reels, predictions = executer_inference(
        modele, dataloader, torch.device("cpu")
    )

    assert labels_reels == [0, 1, 2, 0]
    assert predictions == [0, 1, 2, 2]  # une erreur volontaire (lot 2)


def test_confusion_matrix_forme_dix_par_dix_et_somme_egale_au_nombre_d_echantillons():
    """La confusion matrix doit être 10x10 et sa somme égaler le nombre
    d'échantillons, avec des labels réels/prédits fixes couvrant les 10 classes."""
    from sklearn.metrics import confusion_matrix as sk_confusion_matrix

    labels_reels, predictions = [], []
    for classe in range(10):
        labels_reels.extend([classe, classe, classe])
        predictions.extend([classe, classe, classe])
    predictions[1] = 5  # erreur volontaire connue à l'avance

    matrice = sk_confusion_matrix(labels_reels, predictions)

    assert matrice.shape == (10, 10)
    assert matrice.sum() == 30
    assert matrice[0, 5] == 1


@patch("tomatoscan.model.evaluate.plt.show")
def test_afficher_confusion_matrix_classe_absente_ne_plante_plus(mock_show):
    """Régression : avant le fix (labels=range(len(noms_classes)) passé à
    confusion_matrix()), une classe absente des labels réels ET prédits (ici la
    classe 9) produisait une matrice plus petite que (10, 10) et la fonction
    plantait avec un IndexError dans la boucle d'annotation. Doit maintenant
    s'exécuter sans erreur."""
    labels_reels = list(range(9))  # classe 9 jamais présente
    predictions = list(range(9))

    afficher_confusion_matrix(labels_reels, predictions, NOMS_CLASSES)

    mock_show.assert_called_once()


def _labels_avec_accuracy_connue():
    """10 échantillons (1 par classe), 8 corrects et 2 erreurs connues à
    l'avance → accuracy exacte de 0.8."""
    labels_reels = list(range(10))
    predictions = list(range(10))
    predictions[3] = 4
    predictions[7] = 8
    return labels_reels, predictions


def test_generer_rapport_calcule_l_accuracy_et_liste_les_classes_sous_performantes(
    tmp_path,
):
    """Vérifie en un seul rapport généré : l'accuracy calculée (8/10 = 0.8), une
    entrée par classe dans le détail, et les classes sous-performantes (F1 <
    0.80) détectées correctement — vérifié indépendamment avec sklearn avant
    d'écrire ce test, pas une valeur supposée."""
    labels_reels, predictions = _labels_avec_accuracy_connue()

    chemin_rapport = generer_rapport(
        labels_reels,
        predictions,
        NOMS_CLASSES,
        meilleure_epoch=13,
        meilleure_accuracy=0.9455,
        dossier_rapport=str(tmp_path),
    )

    with open(chemin_rapport, encoding="utf-8") as fichier:
        rapport = json.load(fichier)

    assert rapport["accuracy_test"] == 0.8
    assert rapport["meilleure_epoch"] == 13
    for classe in NOMS_CLASSES:
        assert "f1-score" in rapport["rapport_classification"][classe]
    assert set(rapport["classes_sous_performantes"]) == {
        "classe_3",
        "classe_4",
        "classe_7",
        "classe_8",
    }


def test_generer_rapport_classe_totalement_absente_ne_plante_plus(tmp_path):
    """Régression : avant le fix, classification_report() levait un ValueError
    si une classe n'apparaissait ni dans labels_reels ni dans predictions. Doit
    maintenant générer une entrée pour la classe absente (métriques à 0)."""
    labels_reels = list(range(9))  # classe 9 totalement absente
    predictions = list(range(9))

    chemin_rapport = generer_rapport(
        labels_reels,
        predictions,
        NOMS_CLASSES,
        meilleure_epoch=1,
        meilleure_accuracy=0.5,
        dossier_rapport=str(tmp_path),
    )

    with open(chemin_rapport, encoding="utf-8") as fichier:
        rapport = json.load(fichier)

    assert rapport["rapport_classification"]["classe_9"]["support"] == 0
    assert "classe_9" in rapport["classes_sous_performantes"]


def test_verifier_seuil_reentrainement():
    """Déclenche si accuracy < seuil (comparaison stricte, la limite exacte ne
    déclenche pas), ou si au moins une classe est sous-performante — même avec
    une bonne accuracy globale, c'est le scénario qui justifie ce second
    critère (une dérive sur une classe précise peut être masquée par
    l'accuracy globale)."""
    assert verifier_seuil_reentrainement(0.60, [], seuil_accuracy=0.85) is True
    assert verifier_seuil_reentrainement(0.95, [], seuil_accuracy=0.85) is False
    assert verifier_seuil_reentrainement(0.85, [], seuil_accuracy=0.85) is False
    assert (
        verifier_seuil_reentrainement(0.93, ["classe_3"], seuil_accuracy=0.85) is True
    )
    assert SEUIL_ACCURACY_REENTRAINEMENT == 0.85


def test_journaliser_declenchement_ecrit_puis_accumule_sans_dupliquer_l_en_tete(
    tmp_path,
):
    """Le premier appel crée le fichier avec un en-tête ; les appels suivants
    accumulent des lignes dans le même fichier sans réécrire l'en-tête."""
    journaliser_declenchement(0.60, True, seuil=0.85, dossier_rapport=str(tmp_path))
    chemin_log = journaliser_declenchement(
        0.95, False, seuil=0.85, dossier_rapport=str(tmp_path)
    )

    contenu = (tmp_path / "reentrainement_log.csv").read_text(encoding="utf-8")
    assert contenu.count("accuracy_test") == 1  # en-tête une seule fois

    import csv

    with open(chemin_log, newline="", encoding="utf-8") as fichier:
        lignes = list(csv.DictReader(fichier))
    assert len(lignes) == 2
    assert lignes[0]["declenche"] == "True"
    assert lignes[1]["declenche"] == "False"
