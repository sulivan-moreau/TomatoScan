# TomatoScan — Détection de maladies sur tomates

Modèle CNN (MobileNetV2) entraîné sur PlantVillage + Tomato-Village.
Exposé via une API FastAPI, déployé sur VPS OVH.

## Stack
- Python 3.11 / TensorFlow / FastAPI / Streamlit
- MLflow (tracking) / Prometheus / Grafana (monitoring)
- PostgreSQL (base de données)
- Docker / GitHub Actions (CI/CD)

## Installation

```bash
# Cloner le repo
git clone https://github.com/sulivan-moreau/tomatoscan.git
cd tomatoscan

# Copier et remplir les variables d'environnement
cp .env.example .env

# Installer les dépendances
just install
```

## Lancer le projet

```bash
# API
just api

# Frontend
just app

# MLflow
just mlflow

# Docker
just up
```

## Tests

```bash
just test
```

## Structure du projet
