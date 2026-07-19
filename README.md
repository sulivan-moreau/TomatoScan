# TomatoScan — Détection de maladies sur tomates

Détection de maladies sur feuilles de tomates par deep learning (transfer learning
MobileNetV2, PyTorch). L'utilisateur envoie une photo de feuille via une interface
web, reçoit la maladie détectée et le score de confiance associé.

Projet de certification individuel — DevIA Simplon (candidat Sulivan Moreau).

## Stack technique

| Domaine | Choix |
|---|---|
| Modèle | PyTorch / torchvision — MobileNetV2 (transfer learning) |
| API | FastAPI, authentification JWT (python-jose) |
| Frontend | Streamlit |
| Base de données | PostgreSQL (SQLAlchemy async, asyncpg, Alembic) |
| Monitoring | Prometheus + Grafana |
| Conteneurisation | Docker, déploiement automatique via Coolify (VPS OVH) |
| CI/CD | GitHub Actions |
| Gestionnaire de paquets | [uv](https://docs.astral.sh/uv/) |

## Installation

```bash
# Cloner le repo
git clone https://github.com/sulivan-moreau/tomatoscan.git
cd tomatoscan

# Copier et remplir les variables d'environnement (voir .env.example pour le détail)
cp .env.example .env

# Installer les dépendances (API + modèle + outils de dev)
just install
```

## Lancer le projet

```bash
# API FastAPI — http://localhost:8000 (docs interactives sur /docs)
just api

# Frontend Streamlit — http://localhost:8501
just app

# Stack Docker complète (API + frontend + PostgreSQL + Prometheus + Grafana)
just up
```

Toutes les commandes disponibles sont listées dans le [`justfile`](justfile)
(`just --list`).

## Tests

```bash
just test
```

Détail du plan de tests (cas testés, stratégie de mock, couverture) :
[docs/tests.md](docs/tests.md).

## Structure du projet

```
src/tomatoscan/
├── api/            # API FastAPI (routes, schémas, sécurité JWT, métriques Prometheus)
├── database/        # Modèles SQLAlchemy, connexion async, bootstrap du compte admin
├── model/           # Prétraitement, entraînement et évaluation du modèle MobileNetV2
└── front/            # Application Streamlit (pages, client API, gestion de session)

tests/                # Suite de tests — un dossier par domaine (api, model, frontend, database)
monitoring/           # Configuration Prometheus + dashboards/alertes Grafana
scripts/               # Scripts d'orchestration (ex. pipeline CI modèle)
.github/workflows/     # CI application, CI modèle, CD modèle
docs/                   # Documentation technique complète (voir ci-dessous)
```

## Documentation

| Document | Contenu |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Documentation technique : installation dev, architecture applicative, dépendances |
| [docs/tests.md](docs/tests.md) | Plan de tests, procédure de couverture |
| [docs/monitoring.md](docs/monitoring.md) | Chaîne Prometheus/Grafana, métriques, seuils d'alerte |
| [docs/ci_application.md](docs/ci_application.md) | Pipeline CI de l'application |
| [docs/cd_application.md](docs/cd_application.md) | Déploiement continu de l'application (Coolify) |
| [docs/ci_cd_modele.md](docs/ci_cd_modele.md) | Pipeline CI/CD du modèle MobileNetV2 |
| [docs/agile.md](docs/agile.md) | Coordination agile et pilotage du projet |

## Choix techniques notables

- **PostgreSQL asynchrone** (`asyncpg` + `create_async_engine`) plutôt que SQLite en
  production/préprod, pour un accès concurrent réaliste sous charge.
- **JWT avec renouvellement automatique** côté frontend (`/auth/refresh` déclenché
  avant expiration) plutôt qu'une reconnexion manuelle après expiration.
- **Rate limiting par IP (slowapi) + verrouillage par compte** après échecs de
  connexion consécutifs — deux mécanismes complémentaires, le premier ne protégeant
  pas contre un attaquant lent ciblant un compte précis.
- **Modèle en volume Docker** (jamais packagé dans l'image) — un nouveau checkpoint
  se déploie sans reconstruire l'image API.
- **Séparation des métriques applicatives et des métriques de comportement du
  modèle** dans le monitoring (voir [docs/monitoring.md](docs/monitoring.md)) — un
  taux d'erreurs élevé et une dérive de confiance du modèle sont deux signaux
  différents, traités séparément.
