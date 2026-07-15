# Configuration Alembic — pointe sur Base.metadata et lit DATABASE_URL depuis .env
import asyncio
import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Chargement du .env avant tout accès aux variables d'environnement
load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Injection de DATABASE_URL depuis l'environnement — remplace la valeur de alembic.ini
# Schéma attendu : postgresql+asyncpg://... (moteur async, cohérent avec
# database/connexion.py — voir la migration vers create_async_engine).
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


def _executer_migrations(connexion: Connection) -> None:
    """Partie synchrone partagée : configure le contexte Alembic sur une
    connexion déjà établie et applique les migrations. Appelée via
    AsyncConnection.run_sync() — Alembic lui-même (parcours des révisions,
    diff de schéma) reste une bibliothèque synchrone, seul l'établissement
    de la connexion est asynchrone (asyncpg).
    """
    context.configure(connection=connexion, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Mode en-ligne : se connecte à la BDD (async) et applique les migrations.

    Pattern standard Alembic pour un moteur asynchrone : async_engine_from_config
    + AsyncConnection.run_sync(), puisque le moteur d'exécution des migrations
    d'Alembic est lui-même synchrone.
    """
    connecteur = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connecteur.connect() as connexion:
        await connexion.run_sync(_executer_migrations)

    await connecteur.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
