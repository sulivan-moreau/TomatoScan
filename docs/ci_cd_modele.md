# CI/CD Modèle — TomatoScan

Documente la chaîne CI/CD dédiée au modèle MobileNetV2 : entraînement, évaluation,
et déploiement du checkpoint vers le VPS.

Ferme le ticket [#24 — docs: documentation pipeline CI/CD modèle](https://github.com/sulivan-moreau/tomatoscan/issues/24).

Deux workflows distincts, avec des rôles différents :

| Workflow | Fichier | Rôle |
|---|---|---|
| CI Modèle | `.github/workflows/ci-model.yml` | Prouve que la chaîne data → preprocessing → entraînement → évaluation → rapport s'exécute techniquement sans erreur |
| CD Modèle | `.github/workflows/cd-model.yml` | Transporte un checkpoint `.pt` déjà entraîné vers le VPS de préprod et redémarre l'API |

## Sommaire

1. [CI Modèle — entraînement + évaluation](#ci-modèle--entraînement--évaluation)
2. [CD Modèle — déploiement du checkpoint](#cd-modèle--déploiement-du-checkpoint)
3. [Installation](#installation)
4. [Configuration (secrets et variables)](#configuration-secrets-et-variables)
5. [Déclenchement manuel](#déclenchement-manuel)

## CI Modèle — entraînement + évaluation

**Déclencheurs** : push sur une branche `feature/model-*`, ou manuel (`workflow_dispatch`).

**Ce qu'elle prouve** : que le pipeline technique fonctionne de bout en bout — pas la
qualité du modèle. Elle entraîne réellement (aucun mock, contrairement aux tests
unitaires de `tests/test_model/`) mais sur un **mini-dataset de 32 images réelles**
(4 classes Tomato, 8 images chacune, committées dans `tests/fixtures/mini_dataset/`)
sur **2 epochs seulement**. Le dataset complet PlantVillage (~2 Go) n'est jamais
utilisé ici — trop volumineux pour un dépôt Git, absent de la CI. L'accuracy mesurée
sur ce mini-dataset (~20 % lors d'un run de vérification) n'a donc **aucune valeur
prédictive** sur le modèle réel de production (~93.5 % d'accuracy).

**Étapes** (voir `.github/workflows/ci-model.yml`) :

1. Checkout du code (inclut `tests/fixtures/mini_dataset/`).
2. Setup Python 3.11 + uv.
3. Installation de torch/torchvision CPU-only, **avant** `uv sync` — le runner
   GitHub Actions n'a pas de GPU ; installer la variante CPU en premier évite que
   `uv sync` résolve ~1.5 Go de dépendances CUDA/NVIDIA inutiles (même stratégie que
   `Dockerfile.api`).
4. Installation du reste des dépendances (`uv sync --extra dev`).
5. Tests de préparation des données (`tests/test_model/test_donnees.py`,
   `test_preprocessing.py`) — valident la même logique que celle exercée juste après
   sur le mini-dataset réel.
6. **Entraînement + évaluation réels** via `scripts/ci_entrainement_evaluation.py` :
   charge le mini-dataset (`charger_dataset`), entraîne (`entrainer_modele`, 2
   epochs), évalue (`charger_checkpoint`, `executer_inference`, `generer_rapport`).
7. Vérification du seuil de réentraînement (C11) sur ce run — **avertissement
   uniquement** (`::warning::` dans les logs), jamais de déploiement automatique
   déclenché : voir justification ci-dessous.
8. Publication du checkpoint entraîné et du rapport JSON comme artifacts GitHub
   Actions (rétention 14 jours), visibles depuis l'onglet Summary du run.

**Pourquoi aucun déclenchement automatique de déploiement depuis la CI** : le
franchissement du seuil de réentraînement est calculé sur un mini-dataset de smoke-test,
pas sur une évaluation représentative du modèle de production. Brancher un déploiement
automatique sur ce signal enverrait en production un modèle jamais réellement évalué.
Si ce mécanisme doit un jour déclencher un vrai réentraînement/déploiement, il faudra
d'abord le brancher sur une évaluation du modèle de production (dataset complet
PlantVillage), avec une revue humaine avant tout redémarrage du conteneur API — décision
produit volontairement laissée ouverte, pas tranchée dans ce workflow.

## CD Modèle — déploiement du checkpoint

**Déclencheurs** :
- Automatique : push sur `develop` modifiant un fichier `models/**.pt`.
- Manuel (`workflow_dispatch`) avec un input `dry_run` (coché par défaut).

**Ce qu'elle fait** : dépose un checkpoint `.pt` déjà entraîné sur le VPS de préprod
et redémarre le conteneur API pour qu'il le charge. Elle ne réentraîne rien — c'est le
rôle de la CI Modèle (ou d'un entraînement local, voir `just train`). Le modèle reste
en volume Docker monté en lecture seule (`./models:/app/models:ro` dans
`docker-compose.yml`), jamais packagé dans l'image — cohérent avec l'architecture
existante, aucun MLflow utilisé sur ce projet.

**Étapes** (voir `.github/workflows/cd-model.yml`) :

1. Checkout du code.
2. Vérifie la présence d'un fichier `models/mobilenetv2_best_*.pt` dans le commit —
   échoue explicitement (pas silencieusement) si absent.
3. Configure l'accès SSH au VPS via une clé privée chargée dans l'agent SSH (jamais
   affichée en clair dans les logs).
4. Teste la connexion SSH — s'exécute même en dry-run, pour valider les secrets/la
   connexion avant toute action.
5. *(si pas dry-run)* Copie le `.pt` sur le VPS, puis met à jour un lien symbolique
   stable `mobilenetv2_current.pt` pointant vers ce fichier — nécessaire car
   `MODEL_PATH` (`.env` préprod) référence un nom de fichier horodaté fixe.
6. *(si pas dry-run)* Redémarre dynamiquement le conteneur API sur le VPS (le nom du
   conteneur change à chaque redéploiement Coolify, trouvé par filtre plutôt que nom fixe).
7. Résumé du déploiement publié dans l'onglet Summary du run (mode, fichier, taille,
   déclencheur, horodatage, statut).

> **Point d'attention connu** : `models/` est actuellement dans `.gitignore` (voir
> `.gitignore` — la section « Données et modèles »). Le déclencheur automatique sur
> push `develop` ne se déclenchera donc pas tant qu'un `.pt` n'est pas explicitement
> ajouté au dépôt avec `git add -f`, ou que `.gitignore` ne soit changé — décision
> volontairement laissée à Satoshi, non tranchée ici. En attendant, le déploiement
> d'un nouveau modèle se fait via le déclenchement manuel (`workflow_dispatch`).

## Installation

Aucune installation locale n'est nécessaire pour ces deux workflows : ils s'exécutent
exclusivement sur les runners GitHub Actions (`ubuntu-latest`). Pour reproduire
l'entraînement CI en local :

```bash
uv sync --extra dev
CI_DATASET_PATH=tests/fixtures/mini_dataset uv run python scripts/ci_entrainement_evaluation.py
```

Pour un entraînement réel sur le dataset complet (hors CI, en local) :

```bash
just train
```

## Configuration (secrets et variables)

### CI Modèle

Aucun secret requis — le job n'utilise que le mini-dataset versionné, pas de base de
données ni d'accès externe.

| Variable d'environnement (job) | Défaut | Rôle |
|---|---|---|
| `CI_DATASET_PATH` | `tests/fixtures/mini_dataset` | Dossier du mini-dataset |
| `CI_MODEL_DIR` | `ci_artifacts/models` | Dossier de sortie du checkpoint |
| `CI_REPORT_DIR` | `ci_artifacts/reports` | Dossier de sortie du rapport JSON |
| `CI_EPOCHS` | `2` | Nombre d'epochs d'entraînement |
| `CI_BATCH_SIZE` | `4` | Taille de batch (adaptée aux 32 images du mini-dataset) |

### CD Modèle

À configurer dans **GitHub → Settings → Secrets and variables → Actions** :

| Nom | Type | Rôle |
|---|---|---|
| `VPS_SSH_PRIVATE_KEY` | Secret | Clé privée SSH pour se connecter au VPS |
| `VPS_HOST` | Secret | Adresse du VPS |
| `VPS_USER` | Secret | Utilisateur SSH sur le VPS |
| `VPS_MODELS_PATH` | Variable | Chemin du volume `models/` sur le VPS |
| `VPS_COOLIFY_APP_ID` | Variable | Identifiant utilisé pour filtrer le nom du conteneur API à redémarrer |

## Déclenchement manuel

Depuis l'onglet **Actions** du dépôt GitHub :

1. Sélectionner le workflow (« CI — Pipeline modèle » ou « CD — Déploiement modèle »).
2. Cliquer sur **Run workflow**.
3. Pour le CD Modèle : décocher `dry_run` pour un déploiement réel — laissé coché
   par défaut pour ne jamais lancer une copie/redémarrage réel par erreur depuis
   l'interface.

En ligne de commande (si `gh` CLI configuré) :

```bash
gh workflow run ci-model.yml
gh workflow run cd-model.yml -f dry_run=false
```


---

*Accessibilité : document Markdown structuré par hiérarchie de titres (H1→H3), tableaux avec en-têtes de colonnes, aucune information portée uniquement par la couleur ; lisible par un lecteur d'écran et navigable au clavier depuis GitHub.*
