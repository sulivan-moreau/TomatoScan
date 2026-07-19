"""Tests unitaires de src/tomatoscan/model/train.py (compétence C12).

Périmètre : train.py uniquement. Un test nominal par fonction/comportement
distinct — pas de variantes multiples d'un même scénario.

Stratégie de mock — aucun entraînement réel n'est jamais exécuté :
- construire_modele() : la base MobileNetV2 réelle est remplacée par un faux
  nn.Module minimal (mêmes attributs utilisés par le code), pour éviter tout
  téléchargement de poids ImageNet réels.
- executer_epoch() : modèle/criterion/optimizer mockés (aucun vrai calcul de
  gradient), mais le dataloader fournit de vrais petits tenseurs pour que
  torch.max/l'accuracy s'exécutent réellement.
- entrainer_modele() : testée à un niveau orchestration — executer_epoch,
  construire_modele, torch.save, l'optimizer et le scheduler sont tous mockés.

Note : la sauvegarde du meilleur modèle se déclenche sur l'amélioration de
val_loss (pas val_accuracy) — voir train.py:201.
"""

import math
import os
from unittest.mock import MagicMock, patch

import torch
import torch.nn as nn

from tomatoscan.model.train import (
    construire_modele,
    entrainer_modele,
    executer_epoch,
    sauvegarder_historique,
    selectionner_device,
)


class _FausseBaseMobileNet(nn.Module):
    """Remplace models.mobilenet_v2 réel — même structure minimale que le code
    manipule (.parameters(), .classifier[1].in_features), sans poids réels."""

    def __init__(self):
        super().__init__()
        self.base = nn.Linear(4, 4)
        self.classifier = nn.Sequential(nn.Dropout(0.2), nn.Linear(8, 1000))

    def forward(self, x):
        return x


def _fabriquer_dataloader(nb_batches: int, taille_batch: int, nb_classes: int):
    return [
        (
            torch.randn(taille_batch, 3, 4, 4),
            torch.randint(0, nb_classes, (taille_batch,)),
        )
        for _ in range(nb_batches)
    ]


@patch("tomatoscan.model.train.torch.backends.mps.is_available", return_value=True)
def test_selectionner_device_mps_disponible(mock_dispo):
    assert selectionner_device().type == "mps"


@patch("tomatoscan.model.train.torch.backends.mps.is_available", return_value=False)
def test_selectionner_device_cpu_par_defaut(mock_dispo):
    assert selectionner_device().type == "cpu"


@patch("tomatoscan.model.train.models.mobilenet_v2")
def test_construire_modele_gele_la_base_et_remplace_le_classifier(mock_mobilenet_v2):
    """La base pré-entraînée doit être gelée (requires_grad=False), le classifier
    final remplacé par Sequential(Dropout, Linear) vers nombre_classes sorties,
    et seuls les paramètres du nouveau classifier comptent comme entraînables."""
    mock_mobilenet_v2.return_value = _FausseBaseMobileNet()

    modele = construire_modele(nombre_classes=7)

    assert isinstance(modele.classifier, nn.Sequential)
    assert modele.classifier[1].out_features == 7
    assert modele.base.weight.requires_grad is False
    assert modele.classifier[1].weight.requires_grad is True

    nb_entrainables = sum(p.numel() for p in modele.parameters() if p.requires_grad)
    nb_attendu = sum(p.numel() for p in modele.classifier.parameters())
    assert nb_entrainables == nb_attendu > 0


def test_executer_epoch_entrainement_appelle_forward_backward_step_par_batch():
    """En mode entraînement, chaque batch déclenche un forward/backward/step, et
    les métriques retournées restent dans des bornes cohérentes (jamais NaN,
    accuracy dans [0, 1])."""
    nb_batches = 4
    dataloader = _fabriquer_dataloader(nb_batches, taille_batch=2, nb_classes=3)
    modele = MagicMock()
    modele.side_effect = lambda images: torch.randn(images.size(0), 3)
    perte_mock = MagicMock()
    perte_mock.item.return_value = 0.42
    criterion = MagicMock(return_value=perte_mock)
    optimizer = MagicMock()

    loss_moyenne, accuracy = executer_epoch(
        modele,
        dataloader,
        criterion,
        torch.device("cpu"),
        entrainement=True,
        optimizer=optimizer,
    )

    assert criterion.call_count == nb_batches
    assert perte_mock.backward.call_count == nb_batches
    assert optimizer.step.call_count == nb_batches
    assert not math.isnan(loss_moyenne) and loss_moyenne >= 0.0
    assert not math.isnan(accuracy) and 0.0 <= accuracy <= 1.0


def test_executer_epoch_validation_n_appelle_jamais_backward_ni_optimizer():
    """En mode validation, aucun backward ni optimizer.step() ne doit être
    déclenché — seuls le forward et le calcul de perte/accuracy."""
    dataloader = _fabriquer_dataloader(nb_batches=3, taille_batch=2, nb_classes=3)
    modele = MagicMock()
    modele.side_effect = lambda images: torch.randn(images.size(0), 3)
    perte_mock = MagicMock()
    perte_mock.item.return_value = 0.1
    criterion = MagicMock(return_value=perte_mock)

    executer_epoch(
        modele, dataloader, criterion, torch.device("cpu"), entrainement=False
    )

    modele.train.assert_called_once_with(False)
    assert perte_mock.backward.call_count == 0


def test_sauvegarder_historique_ecrit_un_csv_correct(tmp_path):
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
    assert lignes[1]["val_accuracy"] == "0.75"


def _config_mocks_orchestration(mock_construire_modele, mock_selectionner_device):
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
def test_entrainer_modele_orchestration_complete(
    mock_selectionner_device,
    mock_construire_modele,
    mock_executer_epoch,
    mock_adam,
    mock_scheduler,
    mock_torch_save,
    mock_sauvegarder_historique,
    tmp_path,
):
    """Un seul test d'orchestration couvre : le nombre d'appels à executer_epoch
    (2 par epoch), la configuration de l'optimizer/scheduler (Adam lr=0.001,
    StepLR step_size=5/gamma=0.5), et le contenu du checkpoint sauvegardé
    (epoch, model_state_dict, val_accuracy, class_names)."""
    faux_modele = _config_mocks_orchestration(
        mock_construire_modele, mock_selectionner_device
    )
    mock_adam.return_value = MagicMock()
    mock_scheduler.return_value = MagicMock()
    mock_sauvegarder_historique.return_value = str(tmp_path / "historique.csv")
    mock_executer_epoch.side_effect = [
        (0.9, 0.5),
        (0.8, 0.6321),
    ]  # 1 epoch : train, val

    noms_classes = ["Tomato_healthy", "Tomato_Early_blight"]
    chemin = entrainer_modele(
        dataloader_train=MagicMock(),
        dataloader_val=MagicMock(),
        noms_classes=noms_classes,
        epochs=1,
        dossier_modele=str(tmp_path),
    )

    assert mock_executer_epoch.call_count == 2
    assert chemin.endswith(".pt")

    args_adam, kwargs_adam = mock_adam.call_args
    assert args_adam[0] == faux_modele.classifier.parameters.return_value
    assert kwargs_adam["lr"] == 0.001
    _, kwargs_scheduler = mock_scheduler.call_args
    assert kwargs_scheduler["step_size"] == 5
    assert kwargs_scheduler["gamma"] == 0.5

    checkpoint_sauvegarde = mock_torch_save.call_args[0][0]
    assert checkpoint_sauvegarde["epoch"] == 1
    assert checkpoint_sauvegarde["val_accuracy"] == 0.6321
    assert checkpoint_sauvegarde["class_names"] == noms_classes


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
    """val_loss s'améliore 3 fois puis empire 3 fois de suite (patience=3) →
    early stopping déclenché à l'epoch 6 même si epochs=20 est demandé ;
    torch.save appelé uniquement aux 3 epochs où val_loss s'est améliorée."""
    _config_mocks_orchestration(mock_construire_modele, mock_selectionner_device)
    mock_adam.return_value = MagicMock()
    mock_scheduler.return_value = MagicMock()
    mock_sauvegarder_historique.return_value = str(tmp_path / "historique.csv")

    val_loss_sequence = [0.8, 0.6, 0.5, 0.55, 0.7, 0.9]
    sequence = []
    for val_loss in val_loss_sequence:
        sequence.append((0.9, 0.5))  # train, peu importe
        sequence.append((val_loss, 0.6))  # val
    mock_executer_epoch.side_effect = sequence

    entrainer_modele(
        dataloader_train=MagicMock(),
        dataloader_val=MagicMock(),
        noms_classes=[f"classe_{i}" for i in range(10)],
        epochs=20,
        dossier_modele=str(tmp_path),
    )

    assert mock_executer_epoch.call_count == 6 * 2
    assert mock_torch_save.call_count == 3
