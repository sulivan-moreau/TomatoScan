# TomatoScan — commandes du projet
# Usage : just <commande>

# Installer les dépendances
install:
    uv sync --extra dev

# Lancer l'API en dev
api:
    uv run uvicorn src.tomatoscan.api.main:app --reload --host 0.0.0.0 --port 8000

# Lancer l'app Streamlit
app:
    uv run streamlit run src/tomatoscan/front/main.py

# Lancer les tests
test:
    uv run pytest tests/ -v --cov=src/tomatoscan --cov-report=term-missing

# Linter
lint:
    uv run ruff check src/ tests/

# Formatter
format:
    uv run ruff format src/ tests/

# Entraîner le modèle
train:
    uv run python src/tomatoscan/model/train.py

# Lancer MLflow UI
mlflow:
    uv run mlflow ui --port 5000

# Docker
up:
    docker compose up -d

down:
    docker compose down

# Docker dev
up-dev:
    docker compose -f docker-compose.yml -f docker-compose.override.yml up
