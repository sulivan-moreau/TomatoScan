"""Tests unitaires de src/tomatoscan/model/train.py (issue #19, compétence C12).

Périmètre : train.py uniquement. La préparation des données (preprocess.py) est
couverte par l'issue #20 (tests/test_model/test_preprocessing.py, test_donnees.py),
et l'évaluation par test_evaluate.py — aucun des deux n'est testé ici.

Stratégie de mock — aucun entraînement réel n'est jamais exécuté :
- construire_modele() : la base MobileNetV2 réelle (torchvision.models.mobilenet_v2)
  est remplacée par un faux nn.Module minimal (mêmes attributs utilisés par le code :
  .parameters() et .classifier[1].in_features) pour éviter tout téléchargement/chargement
  de poids ImageNet réels. La logique testée (gel des poids, remplacement du classifier)
  reste donc bien celle du vrai code, seule la base pré-entraînée est substituée.
- executer_epoch() : testée à un niveau "batch" — le modèle, le criterion et l'optimizer
  sont des unittest.mock.MagicMock (aucun vrai calcul de gradient), mais le dataloader
  fournit de vrais petits tenseurs pour que torch.max/comparaisons/accuracy s'exécutent
  réellement et produisent des métriques cohérentes.
- entrainer_modele() : testée à un niveau "orchestration" — executer_epoch,
  construire_modele, selectionner_device, torch.save, sauvegarder_historique,
  torch.optim.Adam et torch.optim.lr_scheduler.StepLR sont tous mockés. Ça isole la
  logique de boucle (nombre d'epochs, early stopping, sauvegarde du meilleur checkpoint)
  de la mécanique interne de chaque epoch, déjà couverte par les tests d'executer_epoch.

Note sur l'énoncé de tâche : la sauvegarde du meilleur modèle dans le code réel se
déclenche sur l'amélioration de val_loss (pas val_accuracy, malgré la formulation de
la consigne) — voir train.py:201 `if val_loss < meilleure_val_loss`. Le scénario
d'early stopping ci-dessous simule donc une séquence de val_loss décroissante puis
croissante (avec des val_accuracy correspondantes fournies à titre indicatif), pour
coller exactement au critère réellement implémenté.

Pas de fonction séparée pour l'optimizer/le scheduler dans train.py : ils sont
construits en ligne dans entrainer_modele() (torch.optim.Adam, torch.optim.lr_scheduler.
StepLR). Leur configuration est donc vérifiée en mockant ces deux constructeurs
directement dans le test d'orchestration, plutôt que via une fonction dédiée.
"""

import math
import os
from unittest.mock import MagicMock, patch

import pytest

import torch
import torch.nn as nn

from tomatoscan.model.train import (
    construire_modele,
    entrainer_modele,
    executer_epoch,
    sauvegarder_historique,
    selectionner_device,
)


# --- Fixtures / faux objets réutilisés ---------------------------------------


class _FausseBaseMobileNet(nn.Module):
    """Remplace models.mobilenet_v2 réel — même structure minimale que le code
    a besoin de manipuler (.parameters(), .classifier étant un Sequential dont
    l'index 1 a .in_features), sans les poids ImageNet réels."""

    def __init__(self):
        super().__init__()
        self.base = nn.Linear(4, 4)
        self.classifier = nn.Sequential(nn.Dropout(0.2), nn.Linear(8, 1000))

    def forward(self, x):
        return x


def _fabriquer_dataloader(nb_batches: int, taille_batch: int, nb_classes: int):
    """Construit une liste de (images, labels) — un faux DataLoader itérable,
    avec de vrais petits tenseurs (pas de mock) pour que le calcul d'accuracy
    dans executer_epoch s'exécute réellement."""
    lots = []
    for _ in range(nb_batches):
        images = torch.randn(taille_batch, 3, 4, 4)
        labels = torch.randint(0, nb_classes, (taille_batch,))
        lots.append((images, labels))
    return lots


# --- selectionner_device ------------------------------------------------------


@patch("tomatoscan.model.train.torch.backends.mps.is_available", return_value=True)
def test_selectionner_device_mps_disponible(mock_dispo):
    """Si MPS est disponible, le device retourné doit être 'mps'."""
    device = selectionner_device()
    assert device.type == "mps"


@patch("tomatoscan.model.train.torch.backends.mps.is_available", return_value=False)
def test_selectionner_device_cpu_par_defaut(mock_dispo):
    """Si MPS n'est pas disponible, le device retourné doit être 'cpu'."""
    device = selectionner_device()
    assert device.type == "cpu"


# --- construire_modele --------------------------------------------------------


@patch("tomatoscan.model.train.models.mobilenet_v2")
def test_construire_modele_gele_la_base_et_remplace_le_classifier(mock_mobilenet_v2):
    """La base pré-entraînée doit être gelée (requires_grad=False) et le classifier
    final remplacé par un Sequential(Dropout, Linear) vers nombre_classes sorties."""
    mock_mobilenet_v2.return_value = _FausseBaseMobileNet()

    modele = construire_modele(nombre_classes=7)

    # Le mock a bien été appelé avec des poids ImageNet (comportement du vrai code) —
    # mais mocké, donc aucun téléchargement réel n'a lieu.
    mock_mobilenet_v2.assert_called_once()

    # Le classifier a été remplacé : Sequential(Dropout, Linear(8, 7))
    assert isinstance(modele.classifier, nn.Sequential)
    assert len(modele.classifier) == 2
    assert isinstance(modele.classifier[0], nn.Dropout)
    assert isinstance(modele.classifier[1], nn.Linear)
    assert modele.classifier[1].out_features == 7

    # La base (self.base) doit être gelée, le nouveau classifier entraînable
    assert modele.base.weight.requires_grad is False
    assert modele.classifier[1].weight.requires_grad is True


@patch("tomatoscan.model.train.models.mobilenet_v2")
def test_construire_modele_compte_correctement_les_parametres_entrainables(
    mock_mobilenet_v2,
):
    """Seuls les paramètres du nouveau classifier doivent être comptés comme
    entraînables — la base gelée ne doit pas y contribuer."""
    mock_mobilenet_v2.return_value = _FausseBaseMobileNet()

    modele = construire_modele(nombre_classes=3)

    nb_entrainables = sum(p.numel() for p in modele.parameters() if p.requires_grad)
    nb_attendu = sum(p.numel() for p in modele.classifier.parameters())
    assert nb_entrainables == nb_attendu
    assert nb_entrainables > 0


# --- executer_epoch : mode entraînement ---------------------------------------


def test_executer_epoch_entrainement_appelle_forward_backward_step_par_batch():
    """En mode entraînement, chaque batch doit déclencher un forward (appel au
    modèle), un backward et un optimizer.step() — sans vrai calcul de gradient
    (modèle/criterion/optimizer entièrement mockés)."""
    nb_batches = 4
    dataloader = _fabriquer_dataloader(nb_batches, taille_batch=2, nb_classes=3)

    modele = MagicMock()
    # Le forward doit renvoyer un vrai tenseur pour que torch.max/accuracy fonctionnent
    modele.side_effect = lambda images: torch.randn(images.size(0), 3)

    perte_mock = MagicMock()
    perte_mock.item.return_value = 0.42
    criterion = MagicMock(return_value=perte_mock)

    optimizer = MagicMock()

    loss_moyenne, accuracy = executer_epoch(
        modele, dataloader, criterion, torch.device("cpu"), entrainement=True, optimizer=optimizer
    )

    modele.train.assert_called_once_with(True)
    assert criterion.call_count == nb_batches
    assert perte_mock.backward.call_count == nb_batches
    assert optimizer.zero_grad.call_count == nb_batches
    assert optimizer.step.call_count == nb_batches

    assert isinstance(loss_moyenne, float)
    assert isinstance(accuracy, float)


# --- executer_epoch : mode validation ------------------------------------------


def test_executer_epoch_validation_n_appelle_jamais_backward_ni_optimizer():
    """En mode validation (entrainement=False), aucun backward ni optimizer.step()
    ne doit être déclenché — seul le forward et le calcul de perte/accuracy."""
    dataloader = _fabriquer_dataloader(nb_batches=3, taille_batch=2, nb_classes=3)

    modele = MagicMock()
    modele.side_effect = lambda images: torch.randn(images.size(0), 3)

    perte_mock = MagicMock()
    perte_mock.item.return_value = 0.1
    criterion = MagicMock(return_value=perte_mock)

    loss_moyenne, accuracy = executer_epoch(
        modele, dataloader, criterion, torch.device("cpu"), entrainement=False
    )

    modele.train.assert_called_once_with(False)
    assert perte_mock.backward.call_count == 0

    assert isinstance(loss_moyenne, float)
    assert isinstance(accuracy, float)


# --- executer_epoch : bornes des métriques -------------------------------------


def test_executer_epoch_metriques_dans_des_bornes_coherentes():
    """loss_moyenne doit être >= 0, accuracy doit être dans [0, 1], jamais NaN —
    quel que soit le contenu (mocké) des sorties du modèle."""
    dataloader = _fabriquer_dataloader(nb_batches=5, taille_batch=4, nb_classes=10)

    modele = MagicMock()
    modele.side_effect = lambda images: torch.randn(images.size(0), 10)

    perte_mock = MagicMock()
    perte_mock.item.return_value = 1.2345
    criterion = MagicMock(return_value=perte_mock)

    optimizer = MagicMock()

    loss_moyenne, accuracy = executer_epoch(
        modele, dataloader, criterion, torch.device("cpu"), entrainement=True, optimizer=optimizer
    )

    assert not math.isnan(loss_moyenne)
    assert not math.isnan(accuracy)
    assert loss_moyenne >= 0.0
    assert 0.0 <= accuracy <= 1.0


# --- sauvegarder_historique -----------------------------------------------------


def test_sauvegarder_historique_ecrit_un_csv_correct(tmp_path):
    """Le CSV généré doit contenir une ligne par epoch avec les bonnes colonnes."""
    historique = [
        {
            "epoch": 1,
            "train_loss": 0.9,
            "train_accuracy": 0.5,
            "val_loss": 0.8,
            "val_accuracy": 0.55,
        },
        {
            "epoch": 2,
            "train_loss": 0.6,
            "train_accuracy": 0.7,
            "val_loss": 0.5,
            "val_accuracy": 0.75,
        },
    ]

    chemin = sauvegarder_historique(historique, str(tmp_path), "20260101_000000")

    assert os.path.exists(chemin)

    import csv

    with open(chemin, newline="", encoding="utf-8") as fichier:
        lignes = list(csv.DictReader(fichier))

    assert len(lignes) == 2
    assert set(lignes[0].keys()) == {
        "epoch",
        "train_loss",
        "train_accuracy",
        "val_loss",
        "val_accuracy",
    }
    assert lignes[0]["epoch"] == "1"
    assert lignes[1]["val_accuracy"] == "0.75"


def test_sauvegarder_historique_relance_l_exception_en_cas_d_echec_ecriture():
    """Si l'écriture du CSV échoue (ex. disque plein), l'erreur doit être loggée
    puis re-levée — pas avalée silencieusement."""
    historique = [
        {
            "epoch": 1,
            "train_loss": 0.9,
            "train_accuracy": 0.5,
            "val_loss": 0.8,
            "val_accuracy": 0.55,
        }
    ]

    with patch("tomatoscan.model.train.open", side_effect=OSError("disque plein")):
        with pytest.raises(OSError):
            sauvegarder_historique(historique, "/chemin/quelconque", "20260101_000000")


# --- entrainer_modele : orchestration complète ----------------------------------


def _config_mocks_orchestration(mock_construire_modele, mock_selectionner_device):
    """Configure les mocks communs à tous les tests d'orchestration
    d'entrainer_modele : device CPU déterministe, faux modèle construit."""
    mock_selectionner_device.return_value = torch.device("cpu")
    faux_modele = MagicMock()
    faux_modele.to.return_value = faux_modele
    faux_modele.state_dict.return_value = {"faux": "state_dict"}
    mock_construire_modele.return_value = faux_modele
    return faux_modele


@patch("tomatoscan.model.train.sauvegarder_historique")
@patch("tomatoscan.model.train.torch.save")
@patch("torch.optim.lr_scheduler.StepLR")
@patch("torch.optim.Adam")
@patch("tomatoscan.model.train.executer_epoch")
@patch("tomatoscan.model.train.construire_modele")
@patch("tomatoscan.model.train.selectionner_device")
def test_entrainer_modele_boucle_sur_le_nombre_d_epochs_configure(
    mock_selectionner_device,
    mock_construire_modele,
    mock_executer_epoch,
    mock_adam,
    mock_scheduler,
    mock_torch_save,
    mock_sauvegarder_historique,
    tmp_path,
):
    """Sans early stopping (val_loss toujours meilleure), executer_epoch doit être
    appelé exactement 2 fois par epoch (train + val) pour le nombre d'epochs configuré,
    et torch.save doit être déclenché à chaque epoch puisque val_loss s'améliore
    à chaque fois."""
    _config_mocks_orchestration(mock_construire_modele, mock_selectionner_device)
    mock_adam.return_value = MagicMock()
    mock_scheduler.return_value = MagicMock()
    mock_sauvegarder_historique.return_value = str(tmp_path / "historique.csv")

    epochs = 4
    # val_loss strictement décroissante à chaque epoch → amélioration systématique
    sequence = []
    for epoch in range(epochs):
        sequence.append((0.9 - epoch * 0.01, 0.5))  # train
        sequence.append((0.8 - epoch * 0.05, 0.6))  # val
    mock_executer_epoch.side_effect = sequence

    chemin = entrainer_modele(
        dataloader_train=MagicMock(),
        dataloader_val=MagicMock(),
        noms_classes=[f"classe_{i}" for i in range(10)],
        epochs=epochs,
        dossier_modele=str(tmp_path),
    )

    assert mock_executer_epoch.call_count == epochs * 2
    assert mock_torch_save.call_count == epochs
    assert chemin.endswith(".pt")
    mock_sauvegarder_historique.assert_called_once()


@patch("tomatoscan.model.train.sauvegarder_historique")
@patch("tomatoscan.model.train.torch.save")
@patch("torch.optim.lr_scheduler.StepLR")
@patch("torch.optim.Adam")
@patch("tomatoscan.model.train.executer_epoch")
@patch("tomatoscan.model.train.construire_modele")
@patch("tomatoscan.model.train.selectionner_device")
def test_entrainer_modele_early_stopping_sauvegarde_uniquement_aux_ameliorations(
    mock_selectionner_device,
    mock_construire_modele,
    mock_executer_epoch,
    mock_adam,
    mock_scheduler,
    mock_torch_save,
    mock_sauvegarder_historique,
    tmp_path,
):
    """Scénario : val_loss s'améliore 3 fois puis stagne/empire 3 fois de suite
    (patience=3) → early stopping déclenché à l'epoch 6 même si epochs=20 est demandé.
    torch.save ne doit être appelé qu'aux 3 epochs où val_loss s'est réellement
    améliorée, pas aux 6 epochs exécutées."""
    _config_mocks_orchestration(mock_construire_modele, mock_selectionner_device)
    mock_adam.return_value = MagicMock()
    mock_scheduler.return_value = MagicMock()
    mock_sauvegarder_historique.return_value = str(tmp_path / "historique.csv")

    # val_loss : 0.8, 0.6, 0.5 (améliorations) puis 0.55, 0.7, 0.9
    # (dégradations, patience=3 épuisée à la 3e)
    val_loss_sequence = [0.8, 0.6, 0.5, 0.55, 0.7, 0.9]
    val_acc_sequence = [0.5, 0.6, 0.7, 0.68, 0.6, 0.5]  # fournie à titre indicatif

    sequence = []
    for val_loss, val_acc in zip(val_loss_sequence, val_acc_sequence):
        sequence.append((0.9, 0.5))  # train (peu importe pour ce scénario)
        sequence.append((val_loss, val_acc))  # val
    mock_executer_epoch.side_effect = sequence

    entrainer_modele(
        dataloader_train=MagicMock(),
        dataloader_val=MagicMock(),
        noms_classes=[f"classe_{i}" for i in range(10)],
        epochs=20,  # bien plus que ce que l'early stopping va réellement exécuter
        dossier_modele=str(tmp_path),
    )

    # 6 epochs exécutées (pas 20) : early stopping a coupé la boucle
    assert mock_executer_epoch.call_count == 6 * 2
    # Sauvegarde uniquement aux 3 améliorations (val_loss 0.8 → 0.6 → 0.5)
    assert mock_torch_save.call_count == 3


@patch("tomatoscan.model.train.sauvegarder_historique")
@patch("tomatoscan.model.train.torch.save")
@patch("torch.optim.lr_scheduler.StepLR")
@patch("torch.optim.Adam")
@patch("tomatoscan.model.train.executer_epoch")
@patch("tomatoscan.model.train.construire_modele")
@patch("tomatoscan.model.train.selectionner_device")
def test_entrainer_modele_configure_optimizer_et_scheduler(
    mock_selectionner_device,
    mock_construire_modele,
    mock_executer_epoch,
    mock_adam,
    mock_scheduler,
    mock_torch_save,
    mock_sauvegarder_historique,
    tmp_path,
):
    """Pas de fonction séparée pour l'optimizer/le scheduler dans train.py (ils sont
    construits en ligne) : on vérifie donc leur configuration exacte en mockant
    directement torch.optim.Adam et torch.optim.lr_scheduler.StepLR."""
    faux_modele = _config_mocks_orchestration(mock_construire_modele, mock_selectionner_device)
    mock_adam.return_value = MagicMock()
    mock_scheduler.return_value = MagicMock()
    mock_sauvegarder_historique.return_value = str(tmp_path / "historique.csv")
    mock_executer_epoch.side_effect = [(0.9, 0.5), (0.8, 0.6)]  # 1 epoch, val s'améliore

    entrainer_modele(
        dataloader_train=MagicMock(),
        dataloader_val=MagicMock(),
        noms_classes=["a", "b"],
        epochs=1,
        dossier_modele=str(tmp_path),
    )

    # Adam configuré sur les paramètres du classifier uniquement, lr=0.001
    mock_adam.assert_called_once()
    args_adam, kwargs_adam = mock_adam.call_args
    assert args_adam[0] == faux_modele.classifier.parameters.return_value
    assert kwargs_adam["lr"] == 0.001

    # StepLR configuré avec step_size=5, gamma=0.5
    mock_scheduler.assert_called_once()
    _, kwargs_scheduler = mock_scheduler.call_args
    assert kwargs_scheduler["step_size"] == 5
    assert kwargs_scheduler["gamma"] == 0.5


@patch("tomatoscan.model.train.sauvegarder_historique")
@patch("tomatoscan.model.train.torch.save")
@patch("torch.optim.lr_scheduler.StepLR")
@patch("torch.optim.Adam")
@patch("tomatoscan.model.train.executer_epoch")
@patch("tomatoscan.model.train.construire_modele")
@patch("tomatoscan.model.train.selectionner_device")
def test_entrainer_modele_checkpoint_contient_les_bons_champs(
    mock_selectionner_device,
    mock_construire_modele,
    mock_executer_epoch,
    mock_adam,
    mock_scheduler,
    mock_torch_save,
    mock_sauvegarder_historique,
    tmp_path,
):
    """Le dict passé à torch.save doit contenir epoch, model_state_dict, val_accuracy
    et class_names, conformément au format documenté dans entrainer_modele()."""
    faux_modele = _config_mocks_orchestration(mock_construire_modele, mock_selectionner_device)
    mock_adam.return_value = MagicMock()
    mock_scheduler.return_value = MagicMock()
    mock_sauvegarder_historique.return_value = str(tmp_path / "historique.csv")
    mock_executer_epoch.side_effect = [(0.9, 0.5), (0.8, 0.6321)]  # 1 epoch

    noms_classes = ["Tomato_healthy", "Tomato_Early_blight"]
    entrainer_modele(
        dataloader_train=MagicMock(),
        dataloader_val=MagicMock(),
        noms_classes=noms_classes,
        epochs=1,
        dossier_modele=str(tmp_path),
    )

    checkpoint_sauvegarde = mock_torch_save.call_args[0][0]
    assert checkpoint_sauvegarde["epoch"] == 1
    assert checkpoint_sauvegarde["model_state_dict"] == faux_modele.state_dict.return_value
    assert checkpoint_sauvegarde["val_accuracy"] == 0.6321
    assert checkpoint_sauvegarde["class_names"] == noms_classes


@patch("tomatoscan.model.train.sauvegarder_historique")
@patch("tomatoscan.model.train.torch.save")
@patch("torch.optim.lr_scheduler.StepLR")
@patch("torch.optim.Adam")
@patch("tomatoscan.model.train.executer_epoch")
@patch("tomatoscan.model.train.construire_modele")
@patch("tomatoscan.model.train.selectionner_device")
def test_entrainer_modele_relance_l_exception_survenue_pendant_la_boucle(
    mock_selectionner_device,
    mock_construire_modele,
    mock_executer_epoch,
    mock_adam,
    mock_scheduler,
    mock_torch_save,
    mock_sauvegarder_historique,
    tmp_path,
):
    """Si une erreur survient pendant la boucle d'entraînement (ex. executer_epoch
    plante), elle doit être loggée puis re-levée — pas avalée silencieusement."""
    _config_mocks_orchestration(mock_construire_modele, mock_selectionner_device)
    mock_adam.return_value = MagicMock()
    mock_scheduler.return_value = MagicMock()
    mock_executer_epoch.side_effect = RuntimeError("erreur simulée pendant l'entraînement")

    with pytest.raises(RuntimeError, match="erreur simulée"):
        entrainer_modele(
            dataloader_train=MagicMock(),
            dataloader_val=MagicMock(),
            noms_classes=["a", "b"],
            epochs=1,
            dossier_modele=str(tmp_path),
        )

    mock_sauvegarder_historique.assert_not_called()
