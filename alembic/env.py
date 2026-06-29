# Configuration Alembic — pointe sur Base.metadata et lit DATABASE_URL depuis .env
import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from alembic import context

# Chargement du .env avant tout accès aux variables d'environnement
load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Injection de DATABASE_URL depuis l'environnement — remplace la valeur de alembic.ini
url_bdd = os.getenv("DATABASE_URL", "")
config.set_main_option("sqlalchemy.url", url_bdd)

# Import des modèles pour que Base.metadata connaisse toutes les tables
from tomatoscan.database.connexion import Base  # noqa: E402
from tomatoscan.database import modeles  # noqa: E402, F401 — enregistre User et Prediction

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Mode hors-ligne : génère le SQL sans connexion réelle à la BDD."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Mode en-ligne : se connecte à la BDD et applique les migrations."""
    connecteur = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connecteur.connect() as connexion:
        # Paramètre nommé "connection" imposé par l'API Alembic
        context.configure(connection=connexion, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
