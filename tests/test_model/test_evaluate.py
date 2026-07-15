"""Tests unitaires de src/tomatoscan/model/evaluate.py (issue #19, compétence C12).

Périmètre : evaluate.py uniquement. Voir l'en-tête de test_train.py pour le
périmètre des issues #20 (préparation des données) et des tests API, non couverts ici.

Stratégie de mock — aucun entraînement/inférence réelle sur un vrai checkpoint :
- charger_checkpoint() : torch.load est mocké pour renvoyer un faux dict de checkpoint
  connu à l'avance (pas de fichier .pt réel lu), et construire_modele (importé depuis
  train.py) est mocké pour éviter tout chargement de poids MobileNetV2 réels.
- executer_inference() : le modèle est un unittest.mock.MagicMock dont le forward
  renvoie de vrais petits tenseurs de logits connus à l'avance, pour que torch.max
  et la collecte des prédictions s'exécutent réellement sur des valeurs maîtrisées.
- afficher_confusion_matrix() / generer_rapport() : utilisent le vrai calcul
  scikit-learn (confusion_matrix, classification_report) sur des labels réels et
  prédits fixes, connus à l'avance — c'est exactement ce qui doit être vérifié
  mathématiquement, donc pas mocké. Seul plt.show() est mocké (pas d'affichage
  bloquant/de fenêtre pendant les tests). generer_rapport écrit son JSON dans
  tmp_path (jamais dans ./docs réel).

Bugs réels identifiés pendant l'écriture de ces tests :

1. Dépendance manquante (corrigé) : evaluate.py fait `import matplotlib.pyplot as plt`
   mais matplotlib n'était déclaré nulle part dans pyproject.toml — le module
   plantait à l'import dans tout environnement neuf (CI, clone frais). Pas un
   fichier modèle, donc corrigé directement (ajout de la dépendance).

2. Labels manquants dans un batch (corrigé) : ni confusion_matrix() (evaluate.py:81)
   ni classification_report() (evaluate.py:134) ne recevaient de paramètre `labels`
   explicite. Si une classe de noms_classes n'apparaissait ni dans labels_reels ni
   dans predictions : generer_rapport() levait un ValueError, et
   afficher_confusion_matrix() plantait avec un IndexError (la matrice réelle étant
   plus petite que (10, 10) alors que la boucle d'annotation itère sur les 10
   indices). Fix appliqué : `labels=range(len(noms_classes))` passé aux deux appels,
   pour forcer une taille de sortie fixe indépendante des classes réellement
   présentes dans le batch. Les deux tests ci-dessous vérifiaient initialement le
   crash (pytest.raises) ; ils vérifient maintenant que le scénario qui plantait
   avant fonctionne correctement après le fix.
"""

import csv
import json
from unittest.mock import MagicMock, patch

import pytest
import torch
from sklearn.metrics import confusion_matrix as sk_confusion_matrix

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


# --- charger_checkpoint ---------------------------------------------------------


@patch("tomatoscan.model.evaluate.construire_modele")
@patch("tomatoscan.model.evaluate.torch.load")
def test_charger_checkpoint_extrait_les_bons_champs(
    mock_torch_load, mock_construire_modele
):
    """Le checkpoint chargé doit renvoyer (modele, noms_classes, epoch, accuracy)
    exactement conformes au contenu (connu à l'avance) du fichier .pt."""
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

    mock_construire_modele.assert_called_once_with(10)
    faux_modele.load_state_dict.assert_called_once_with(
        faux_checkpoint["model_state_dict"]
    )
    faux_modele.eval.assert_called_once()

    assert modele is faux_modele
    assert noms_classes == NOMS_CLASSES
    assert meilleure_epoch == 13
    assert meilleure_accuracy == 0.9455


@patch("tomatoscan.model.evaluate.construire_modele")
@patch("tomatoscan.model.evaluate.torch.load")
def test_charger_checkpoint_relance_l_exception_si_fichier_illisible(
    mock_torch_load, mock_construire_modele
):
    """Si torch.load échoue (fichier corrompu/absent), l'erreur doit être loggée
    puis re-levée — pas avalée silencieusement."""
    mock_torch_load.side_effect = RuntimeError("checkpoint corrompu")

    with pytest.raises(RuntimeError, match="checkpoint corrompu"):
        charger_checkpoint("chemin/corrompu.pt", nombre_classes=10)

    mock_construire_modele.assert_not_called()


# --- executer_inference ----------------------------------------------------------


def test_executer_inference_collecte_labels_reels_et_predictions():
    """Les labels réels et prédictions retournés doivent correspondre exactement
    aux tenseurs fournis par le dataloader et aux logits (connus à l'avance)
    renvoyés par le modèle mocké."""
    # 2 batches de 2 images — logits construits pour que l'argmax soit connu à l'avance
    lot_1 = (
        torch.randn(2, 3, 4, 4),
        torch.tensor([0, 1]),
    )
    lot_2 = (
        torch.randn(2, 3, 4, 4),
        torch.tensor([2, 0]),
    )
    dataloader = [lot_1, lot_2]

    # Logits construits pour prédire respectivement [0, 1] puis [2, 2] (une erreur)
    logits_lot_1 = torch.tensor([[5.0, 0.0, 0.0], [0.0, 5.0, 0.0]])
    logits_lot_2 = torch.tensor([[0.0, 0.0, 5.0], [0.0, 0.0, 5.0]])

    modele = MagicMock()
    modele.side_effect = [logits_lot_1, logits_lot_2]

    labels_reels, predictions = executer_inference(
        modele, dataloader, torch.device("cpu")
    )

    modele.eval.assert_called_once()
    assert labels_reels == [0, 1, 2, 0]
    assert predictions == [0, 1, 2, 2]


def test_executer_inference_relance_l_exception_en_cas_d_echec():
    """Si le forward du modèle échoue, l'erreur doit être loggée puis re-levée."""
    dataloader = [(torch.randn(1, 3, 4, 4), torch.tensor([0]))]
    modele = MagicMock()
    modele.side_effect = RuntimeError("erreur d'inférence")

    with pytest.raises(RuntimeError, match="erreur d'inférence"):
        executer_inference(modele, dataloader, torch.device("cpu"))


# --- Confusion matrix : correctness mathématique -------------------------------


def test_confusion_matrix_forme_dix_par_dix_et_somme_egale_au_nombre_d_echantillons():
    """Avec des labels réels/prédits fixes couvrant les 10 classes, la confusion
    matrix générée par le même appel que celui utilisé dans afficher_confusion_matrix
    (evaluate.py:81) doit être 10x10 et sa somme doit égaler le nombre d'échantillons."""
    # 3 échantillons par classe (30 au total), quelques erreurs de classification
    labels_reels = []
    predictions = []
    for classe in range(10):
        labels_reels.extend([classe, classe, classe])
        predictions.extend([classe, classe, classe])
    # Introduit 2 erreurs de classification connues à l'avance
    predictions[1] = 5  # un échantillon de la classe 0 prédit comme classe 5
    predictions[10] = 2  # un échantillon de la classe 3 prédit comme classe 2

    matrice = sk_confusion_matrix(labels_reels, predictions)

    assert matrice.shape == (10, 10)
    assert matrice.sum() == len(labels_reels) == 30
    # Les 2 erreurs volontaires doivent apparaître hors diagonale
    assert matrice[0, 5] == 1
    assert matrice[3, 2] == 1


@patch("tomatoscan.model.evaluate.plt.show")
def test_afficher_confusion_matrix_ne_plante_pas_avec_toutes_les_classes_presentes(
    mock_show,
):
    """afficher_confusion_matrix() doit s'exécuter sans erreur quand toutes les
    classes sont représentées (scénario réaliste d'un vrai jeu de test)."""
    labels_reels = list(range(10))
    predictions = list(range(10))

    afficher_confusion_matrix(labels_reels, predictions, NOMS_CLASSES)

    mock_show.assert_called_once()


@patch("tomatoscan.model.evaluate.plt.show")
def test_afficher_confusion_matrix_classe_absente_ne_plante_plus(mock_show):
    """Ex-bug (voir en-tête de fichier), maintenant corrigé par labels=range(...) :
    avant le fix, une classe absente de labels_reels ET predictions (ici la classe 9)
    produisait une matrice sklearn plus petite que (10, 10), et la fonction plantait
    avec un IndexError dans la boucle d'annotation des cellules. Avec le fix,
    confusion_matrix() force la taille (10, 10) même si la classe 9 n'apparaît nulle
    part dans ce batch — la fonction doit maintenant s'exécuter sans erreur."""
    labels_reels = list(range(9))  # classes 0 à 8 uniquement, jamais la classe 9
    predictions = list(range(9))

    # Sans labels= explicite, sklearn réduirait la matrice aux classes présentes (9x9)
    matrice_sans_fix = sk_confusion_matrix(labels_reels, predictions)
    assert matrice_sans_fix.shape == (9, 9)

    # Avec labels=range(len(noms_classes)) (le fix appliqué dans evaluate.py), la
    # taille reste fixe à 10x10 même si la classe 9 est absente de ce batch
    matrice_avec_fix = sk_confusion_matrix(labels_reels, predictions, labels=range(10))
    assert matrice_avec_fix.shape == (10, 10)

    # La fonction réelle ne doit plus lever d'IndexError
    afficher_confusion_matrix(labels_reels, predictions, NOMS_CLASSES)
    mock_show.assert_called_once()


# --- generer_rapport : correctness mathématique --------------------------------


def _labels_avec_accuracy_connue():
    """Construit 10 échantillons (1 par classe), 8 corrects et 2 erreurs connues
    à l'avance → accuracy exacte de 0.8."""
    labels_reels = list(range(10))
    predictions = list(range(10))
    predictions[3] = 4  # classe 3 mal prédite comme 4
    predictions[7] = 8  # classe 7 mal prédite comme 8
    return labels_reels, predictions


def test_generer_rapport_calcule_l_accuracy_correctement(tmp_path):
    """accuracy_test doit correspondre exactement au nombre de prédictions
    correctes / nombre total, avec des labels fixes connus à l'avance (8/10 = 0.8)."""
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
    assert rapport["meilleure_accuracy_validation"] == 0.9455


def test_generer_rapport_contient_une_entree_par_classe(tmp_path):
    """Le rapport de classification doit contenir une entrée pour chacune des
    10 classes attendues (pas seulement celles présentes dans le sous-échantillon)."""
    labels_reels, predictions = _labels_avec_accuracy_connue()

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

    for classe in NOMS_CLASSES:
        assert classe in rapport["rapport_classification"]
        assert "f1-score" in rapport["rapport_classification"][classe]


def test_generer_rapport_detecte_les_classes_sous_performantes(tmp_path):
    """classes_sous_performantes doit lister exactement les classes dont le f1-score
    calculé est < 0.80. Avec ce jeu de données (2 erreurs sur 10 échantillons, 1 par
    classe), le calcul sklearn produit f1=0.0 pour classe_3 et classe_7 (jamais
    retrouvées, leur seul échantillon étant mal prédit) et f1=0.667 pour classe_4 et
    classe_8 (leur précision est dégradée car elles récupèrent aussi la prédiction
    erronée destinée à classe_3/classe_7) — vérifié indépendamment avec sklearn
    directement avant d'écrire ce test, pas une valeur supposée."""
    labels_reels, predictions = _labels_avec_accuracy_connue()

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

    assert set(rapport["classes_sous_performantes"]) == {
        "classe_3",
        "classe_4",
        "classe_7",
        "classe_8",
    }


def test_generer_rapport_relance_l_exception_en_cas_d_echec_ecriture(tmp_path):
    """Si l'écriture du JSON échoue (ex. disque plein), l'erreur doit être loggée
    puis re-levée — pas avalée silencieusement."""
    labels_reels, predictions = _labels_avec_accuracy_connue()

    with patch("tomatoscan.model.evaluate.open", side_effect=OSError("disque plein")):
        with pytest.raises(OSError, match="disque plein"):
            generer_rapport(
                labels_reels,
                predictions,
                NOMS_CLASSES,
                meilleure_epoch=1,
                meilleure_accuracy=0.5,
                dossier_rapport=str(tmp_path),
            )


def test_generer_rapport_ecrit_bien_un_fichier_json_valide(tmp_path):
    """Le chemin retourné doit exister et contenir un JSON valide et complet."""
    labels_reels, predictions = _labels_avec_accuracy_connue()

    chemin_rapport = generer_rapport(
        labels_reels,
        predictions,
        NOMS_CLASSES,
        meilleure_epoch=1,
        meilleure_accuracy=0.5,
        dossier_rapport=str(tmp_path),
    )

    assert chemin_rapport.startswith(str(tmp_path))
    assert chemin_rapport.endswith(".json")

    with open(chemin_rapport, encoding="utf-8") as fichier:
        rapport = json.load(fichier)

    for cle in (
        "date",
        "modele",
        "meilleure_epoch",
        "meilleure_accuracy_validation",
        "accuracy_test",
        "classes_sous_performantes",
        "rapport_classification",
    ):
        assert cle in rapport


# --- Bug documenté : classe totalement absente du test set ----------------------


def test_generer_rapport_classe_totalement_absente_ne_plante_plus(tmp_path):
    """Ex-bug (voir en-tête de fichier), maintenant corrigé par labels=range(...) :
    avant le fix, classification_report levait un ValueError si une classe de
    noms_classes n'apparaissait ni dans labels_reels ni dans predictions. Le rapport
    doit maintenant se générer normalement, avec une entrée pour la classe absente
    (métriques à 0, faute d'échantillon)."""
    # Classe 9 (noms_classes[9]) totalement absente — ni réelle, ni prédite
    labels_reels = list(range(9))
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

    # La classe absente doit quand même avoir une entrée (métriques à 0)
    assert "classe_9" in rapport["rapport_classification"]
    assert rapport["rapport_classification"]["classe_9"]["support"] == 0
    assert "classe_9" in rapport["classes_sous_performantes"]
    # Les 9 échantillons présents sont tous corrects → accuracy 1.0 malgré l'absence
    assert rapport["accuracy_test"] == 1.0


# --- Déclencheur de réentraînement (C11) -----------------------------------------


def test_verifier_seuil_reentrainement_declenche_si_accuracy_basse():
    """Une accuracy nettement sous le seuil doit déclencher (True)."""
    assert verifier_seuil_reentrainement(0.60, seuil=0.85) is True


def test_verifier_seuil_reentrainement_ne_declenche_pas_si_accuracy_haute():
    """Une accuracy nettement au-dessus du seuil ne doit pas déclencher (False)."""
    assert verifier_seuil_reentrainement(0.95, seuil=0.85) is False


def test_verifier_seuil_reentrainement_cas_limite_exactement_au_seuil():
    """Comparaison stricte (<) : une accuracy exactement égale au seuil ne doit
    PAS déclencher — seul un passage EN DESSOUS du seuil déclenche."""
    assert verifier_seuil_reentrainement(0.85, seuil=0.85) is False


def test_verifier_seuil_reentrainement_utilise_le_seuil_par_defaut():
    """Sans seuil explicite, la constante SEUIL_ACCURACY_REENTRAINEMENT (0.85)
    doit être utilisée."""
    assert SEUIL_ACCURACY_REENTRAINEMENT == 0.85
    assert verifier_seuil_reentrainement(0.84) is True
    assert verifier_seuil_reentrainement(0.86) is False


def test_journaliser_declenchement_ecrit_un_csv_avec_en_tete(tmp_path):
    """Le premier appel doit créer le fichier avec un en-tête et une ligne de données."""
    chemin_log = journaliser_declenchement(
        accuracy_test=0.60, declenche=True, seuil=0.85, dossier_rapport=str(tmp_path)
    )

    assert chemin_log == str(tmp_path / "reentrainement_log.csv")

    with open(chemin_log, newline="", encoding="utf-8") as fichier:
        lignes = list(csv.DictReader(fichier))

    assert len(lignes) == 1
    assert lignes[0]["accuracy_test"] == "0.6"
    assert lignes[0]["seuil"] == "0.85"
    assert lignes[0]["declenche"] == "True"
    assert "date" in lignes[0]


def test_journaliser_declenchement_ajoute_les_lignes_sans_dupliquer_l_en_tete(
    tmp_path,
):
    """Plusieurs appels successifs doivent accumuler des lignes dans le même
    fichier (log cumulatif), avec un en-tête écrit une seule fois."""
    journaliser_declenchement(0.60, True, seuil=0.85, dossier_rapport=str(tmp_path))
    journaliser_declenchement(0.95, False, seuil=0.85, dossier_rapport=str(tmp_path))

    chemin_log = tmp_path / "reentrainement_log.csv"
    contenu = chemin_log.read_text(encoding="utf-8")

    # L'en-tête ("date,accuracy_test,...") ne doit apparaître qu'une seule fois
    assert contenu.count("accuracy_test") == 1

    with open(chemin_log, newline="", encoding="utf-8") as fichier:
        lignes = list(csv.DictReader(fichier))

    assert len(lignes) == 2
    assert lignes[0]["declenche"] == "True"
    assert lignes[1]["declenche"] == "False"
