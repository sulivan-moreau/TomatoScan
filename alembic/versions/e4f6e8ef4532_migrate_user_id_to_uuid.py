"""migrate user id to uuid

Remplace l'identifiant auto-incrémenté de users.id par un UUID, et met à jour
predictions.user_id (clé étrangère) en conséquence pour préserver le lien
existant entre chaque prédiction et son utilisateur.

Migration en 3 temps pour rester compatible SQLite (pas d'ALTER COLUMN TYPE
natif — nécessite batch_alter_table, qui reconstruit la table) ET PostgreSQL :
  1. Ajout de colonnes UUID nullables, en parallèle des colonnes Integer existantes.
  2. Remplissage : un UUID généré par utilisateur existant, reporté sur ses
     prédictions via l'ancien lien entier user_id — aucune ligne existante
     n'est perdue ou désassociée.
  3. Bascule : suppression des anciennes colonnes Integer, renommage des
     colonnes UUID à leur place, reconstruction de la primary key et de la
     foreign key.

Revision ID: e4f6e8ef4532
Revises: c53cc2cea026
Create Date: 2026-07-14 14:08:03.932516

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4f6e8ef4532"
down_revision: Union[str, Sequence[str], None] = "c53cc2cea026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    # --- 1. Colonnes UUID nullables, en parallèle des colonnes Integer existantes ---
    op.add_column("users", sa.Column("id_uuid", sa.Uuid(), nullable=True))
    op.add_column("predictions", sa.Column("user_id_uuid", sa.Uuid(), nullable=True))

    # --- 2. Remplissage : un UUID par utilisateur, reporté sur ses prédictions ---
    # Colonnes déclarées explicitement (pas de simple autoload_with) : la
    # réflexion SQLite ne connaît pas le type Uuid (affinité de stockage
    # générique), et le binding d'un uuid.UUID Python échoue silencieusement
    # sans le bind_processor du type Uuid explicite.
    meta = sa.MetaData()
    users = sa.Table(
        "users",
        meta,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("id_uuid", sa.Uuid()),
    )
    predictions = sa.Table(
        "predictions",
        meta,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer),
        sa.Column("user_id_uuid", sa.Uuid()),
    )

    mapping_ancien_vers_nouveau: dict[int, uuid.UUID] = {}
    for ligne in bind.execute(sa.select(users.c.id)).fetchall():
        mapping_ancien_vers_nouveau[ligne.id] = uuid.uuid4()

    for ancien_id, nouvel_id in mapping_ancien_vers_nouveau.items():
        bind.execute(
            users.update().where(users.c.id == ancien_id).values(id_uuid=nouvel_id)
        )
        bind.execute(
            predictions.update()
            .where(predictions.c.user_id == ancien_id)
            .values(user_id_uuid=nouvel_id)
        )

    # --- 3. Bascule des contraintes (batch_alter_table = compatible SQLite et autres) ---
    # predictions d'abord : sa foreign key référence users.id, qui va disparaître.
    with op.batch_alter_table("predictions") as batch_op:
        batch_op.drop_column("user_id")
        batch_op.alter_column("user_id_uuid", new_column_name="user_id", nullable=False)

    # users.id : testé empiriquement sur une base SQLite seedée avec des données
    # réalistes — combiner un renommage (new_column_name=) et create_primary_key
    # dans LE MÊME batch ne pose PAS d'erreur mais perd silencieusement la
    # primary key (la contrainte ne référence pas correctement la colonne
    # renommée dans la même reconstruction). Il faut donc deux batchs distincts :
    # 1) drop de l'ancien index + ancienne colonne + renommage seul,
    # 2) create_primary_key sur la colonne déjà renommée (comme vérifié en
    # isolation : create_primary_key fonctionne bien quand il porte sur une
    # colonne qui existait déjà sous ce nom au début du batch).
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_id")
        batch_op.drop_column("id")
        batch_op.alter_column("id_uuid", new_column_name="id", nullable=False)

    with op.batch_alter_table("users") as batch_op:
        batch_op.create_primary_key("pk_users", ["id"])

    with op.batch_alter_table("predictions") as batch_op:
        batch_op.create_foreign_key(
            "fk_predictions_user_id_users", "users", ["user_id"], ["id"]
        )


def downgrade() -> None:
    """Downgrade schema.

    Irréversible en pratique : les UUID générés à l'upgrade n'ont pas
    d'équivalent entier stable à restaurer. Lève explicitement plutôt que de
    silencieusement produire de nouveaux entiers déconnectés des anciens ID
    (qui auraient pu être référencés en dehors de cette base, ex. logs, exports).
    """
    raise NotImplementedError(
        "Downgrade non supporté : les UUID générés à l'upgrade n'ont pas "
        "d'entier d'origine à restaurer de façon fiable. Restaurer depuis "
        "une sauvegarde antérieure à cette migration si un retour arrière "
        "est nécessaire."
    )
