# CI Application — TomatoScan

Documente la chaîne d'intégration continue de l'application (API + frontend + base
de données), définie dans `.github/workflows/ci-app.yml`.

Ferme le ticket [#38 — docs: documentation pipeline CI application](https://github.com/sulivan-moreau/tomatoscan/issues/38).

## Sommaire

1. [Outils utilisés](#outils-utilisés)
2. [Déclencheurs](#déclencheurs)
3. [Étapes du pipeline](#étapes-du-pipeline)
4. [Installation](#installation)
5. [Configuration (secrets et variables)](#configuration-secrets-et-variables)
6. [Déclenchement manuel](#déclenchement-manuel)
7. [Tester la chaîne en local](#tester-la-chaîne-en-local)

## Outils utilisés

| Outil | Rôle |
|---|---|
| GitHub Actions | Orchestrateur CI |
| [uv](https://docs.astral.sh/uv/) | Gestionnaire de dépendances/environnements Python |
| pytest + pytest-cov | Tests et couverture |
| ruff | Lint et formatage |
| pip-audit | Audit de sécurité des dépendances installées |
| Alembic | Migrations de base de données |
| PostgreSQL 16 (service GitHub Actions) | Base de données réelle pour les tests — pas de substitut SQLite, l'application cible exclusivement `create_async_engine`/asyncpg |
| Docker | Build de validation des deux images (API, frontend) |
| `docker/login-action` + `docker/build-push-action` | Livraison des images vers `ghcr.io` (job `livraison`, voir [docs/cd_application.md](cd_application.md)) |

## Déclencheurs

```yaml
on:
  push:
    branches: [develop, main]
  pull_request:
    branches: [develop, main]
```

Toute PR vers `develop` ou `main`, et tout push direct sur ces deux branches,
déclenchent le pipeline.

## Étapes du pipeline

Job unique `test`, sur `ubuntu-latest`, timeout 10 minutes. Un service PostgreSQL 16
réel démarre en parallèle du job (healthcheck `pg_isready`, GitHub Actions attend
qu'il soit prêt avant d'exécuter les étapes).

| # | Étape | Détail |
|---|---|---|
| 1 | Checkout du code | `actions/checkout@v4` |
| 2 | Setup Python 3.11 | `actions/setup-python@v5` |
| 3 | Setup uv | `astral-sh/setup-uv@v3`, cache activé |
| 4 | Installation des dépendances | `uv sync --extra dev` |
| 4bis | Audit de sécurité (pip-audit) | `uv run --with pip-audit pip-audit -l` — scanne l'environnement réellement installé contre la base OSV/PyPI Advisory |
| 5 | Lint (ruff) | `uv run ruff check src/ tests/` — couvre le code applicatif ET les tests (périmètre annoncé dans les rapports) |
| 6 | Format check (ruff) | `uv run ruff format --check src/ tests/` — même périmètre |
| 6ter | Filet de sécurité base de données | Crée `tomatoscan_test` si absente — contourne une fenêtre de flakiness connue des images PostgreSQL officielles sous GitHub Actions (redémarrage interne après `initdb`) |
| 6bis | Migrations (`alembic upgrade head`) | Vérifie à chaque run que les migrations s'appliquent sur un vrai PostgreSQL |
| 7 | Tests + couverture API | `pytest tests/ --cov=src/tomatoscan/api --cov-fail-under=75` |
| 7bis | Couverture modèle (seuil dédié) | `pytest tests/test_model/ --cov=src/tomatoscan/model --cov-fail-under=80` — étape séparée car `--cov-fail-under` s'applique à l'ensemble des `--cov` d'une même invocation ; deux seuils par composant demandent deux invocations |
| 8 | Build Docker de validation | `docker build -f Dockerfile.api` et `-f Dockerfile.front`, sans push ni registre — prouve que les deux Dockerfile restent valides à chaque push/PR |

Le workflow `ci-app.yml` contient un **second job, `livraison`** (`needs: test`), qui
n'appartient pas au job `test` ci-dessus : sur push `develop`/`main` uniquement, une
fois le job `test` vert, il build et pousse les images API/frontend sur `ghcr.io`
(taguées par le SHA). C'est l'étape de livraison applicative (compétence C19),
documentée en détail dans [docs/cd_application.md](cd_application.md).

Détail du plan de tests (cas testés, stratégie de mock) : voir
[docs/tests.md](tests.md).

## Installation

Aucune installation locale requise — le pipeline s'exécute intégralement sur les
runners GitHub Actions. Pour reproduire les mêmes étapes en local, voir
[Tester la chaîne en local](#tester-la-chaîne-en-local) ci-dessous.

## Configuration (secrets et variables)

À configurer dans **GitHub → Settings → Secrets and variables → Actions** :

| Nom | Type | Rôle |
|---|---|---|
| `SECRET_KEY` | Secret | Clé de signature JWT utilisée pendant les tests |
| `ADMIN_USERNAME` | Secret | Compte admin de test (bootstrap) |
| `ADMIN_PASSWORD` | Secret | Mot de passe du compte admin de test |

Variables d'environnement fixées directement dans le workflow (non sensibles) :

| Nom | Valeur | Rôle |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://test:test@localhost:5432/tomatoscan_test` | Pointe vers le service PostgreSQL du job |
| `MODEL_PATH` | `./models/non_existant.pt` | Le `.pt` réel est absent du dépôt — les tests mockent `model_service`, aucun checkpoint requis |
| `REPORTS_PATH` | `models/historique_test.csv` | Les tests qui en ont besoin utilisent `tmp_path`, pas ce chemin directement |
| `APP_ENV` | `test` | Signale à l'application qu'elle tourne en environnement de test |

## Déclenchement manuel

Ce workflow n'a pas de `workflow_dispatch` : il se déclenche uniquement sur push/PR
(voir [Déclencheurs](#déclencheurs)). Pour le relancer sans nouveau commit, utiliser
« Re-run jobs » depuis l'onglet **Actions** du run concerné sur GitHub, ou :

```bash
gh run rerun <run-id>
```

## Tester la chaîne en local

```bash
# Dépendances
uv sync --extra dev

# Lint + format
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# Audit de sécurité des dépendances
uv run --with pip-audit pip-audit -l

# Tests + couverture (une base PostgreSQL locale ou SQLite via DATABASE_URL suffit,
# voir docs/tests.md pour la configuration complète)
uv run pytest tests/ --cov=src/tomatoscan/api --cov-fail-under=75
uv run pytest tests/test_model/ --cov=src/tomatoscan/model --cov-fail-under=80

# Build Docker de validation
docker build -f Dockerfile.api -t tomatoscan-api:local .
docker build -f Dockerfile.front -t tomatoscan-front:local .
```

`just test` (voir `justfile`) exécute une variante équivalente de l'étape 7, sans le
seuil de couverture strict. L'étape 7bis (couverture modèle) n'a pas d'équivalent
`just` dédié — la commande `uv run pytest ...` ci-dessus est utilisée directement,
déjà documentée telle quelle dans [docs/tests.md](tests.md).


---

*Accessibilité : document Markdown structuré par hiérarchie de titres (H1→H3), tableaux avec en-têtes de colonnes, aucune information portée uniquement par la couleur ; lisible par un lecteur d'écran et navigable au clavier depuis GitHub. Le Markdown brut est le format standard de la documentation technique développeur — aucune mise en forme visuelle propriétaire (police, couleur de fond, contraste personnalisé) à justifier séparément : le rendu (contraste, navigation clavier, lecteur d'écran) est entièrement délégué à la plateforme d'hébergement (GitHub), déjà conforme aux standards d'accessibilité web usuels.*
