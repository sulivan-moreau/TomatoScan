# CD Application — TomatoScan

Documente la chaîne de déploiement continu de l'application (API + frontend).

Ferme le ticket [#40 — docs: documentation pipeline CD application](https://github.com/sulivan-moreau/tomatoscan/issues/40).

## À la différence du modèle, pas de workflow GitHub Actions

Le déploiement de l'API et du frontend n'est **pas** piloté par un workflow GitHub
Actions (contrairement au modèle, voir `cd-model.yml` /
[docs/ci_cd_modele.md](ci_cd_modele.md)). C'est **Coolify**, une plateforme PaaS
auto-hébergée sur le VPS OVH, qui surveille directement le dépôt Git et redéploie
automatiquement à chaque push — sans étape intermédiaire dans `.github/workflows/`.

Cette architecture est documentée dans les en-têtes de `docker-compose.yml` et
`ci-app.yml` :

```
push sur develop → Coolify déclenche le déploiement préprod
                    (PostgreSQL async, docker-compose.override.yml)
push sur main    → Coolify déclenche le déploiement prod
                    (PostgreSQL, docker-compose.yml seul)
```

La CI GitHub Actions (`ci-app.yml`) reste un **garde-fou en amont** : elle valide
tests, lint et build Docker sur chaque push/PR, mais ne déclenche pas elle-même le
déploiement — c'est Coolify qui build et déploie ses propres images à partir des
mêmes `Dockerfile.api`/`Dockerfile.front`, indépendamment du résultat de la CI (voir
le commentaire de l'étape « Build Docker de validation » dans `ci-app.yml`).

## Sommaire

1. [Toutes les étapes et déclencheurs](#toutes-les-étapes-et-déclencheurs)
2. [Installation](#installation)
3. [Configuration (secrets, registry, VPS)](#configuration-secrets-registry-vps)
4. [Procédure de test et debug](#procédure-de-test-et-debug)
5. [Déclenchement manuel](#déclenchement-manuel)

## Toutes les étapes et déclencheurs

| Étape | Déclencheur / mécanisme |
|---|---|
| 1. Push sur `develop` ou `main` | Déclencheur — Coolify observe le dépôt GitHub connecté |
| 2. Build des images Docker | Coolify build `Dockerfile.api` et `Dockerfile.front` à partir du commit poussé |
| 3. Sélection de la stack Compose | `develop` → `docker-compose.yml` + `docker-compose.override.yml` (préprod, `postgres_preprod`, `APP_ENV=development`) ; `main` → `docker-compose.yml` seul (prod, service `postgres`) |
| 4. Démarrage des conteneurs | `api`, `front`, la base PostgreSQL correspondante, `prometheus`, `grafana` — voir [docs/monitoring.md](monitoring.md) |
| 5. Attente de disponibilité | `front` attend que `api` passe `service_healthy` (healthcheck `GET /health`) avant de démarrer — évite que le frontend serve une API pas encore prête |
| 6. Bascule de trafic | Gérée par Coolify (reverse proxy interne) une fois les conteneurs sains |

Le modèle MobileNetV2 (`.pt`) n'est **jamais** reconstruit par ce processus : il vit
dans un volume Docker persistant (`./models:/app/models:ro`) sur le VPS, déposé
séparément (voir [docs/ci_cd_modele.md](ci_cd_modele.md) — CD Modèle).

## Installation

Ce déploiement suppose une instance Coolify déjà installée sur le VPS OVH cible
(hors périmètre de ce document — installation Coolify générique, indépendante de
TomatoScan). Côté application, la seule « installation » consiste à :

1. Créer une application Coolify pointant vers le dépôt GitHub `tomatoscan`.
2. Configurer deux environnements Coolify distincts (préprod → branche `develop`,
   prod → branche `main`), chacun avec son propre fichier `.env` sur le VPS.
3. Activer le déploiement automatique sur push (webhook GitHub configuré par Coolify).

Prérequis avant le tout premier déploiement (voir en-tête de `docker-compose.yml`) :

```text
1. Copier .env.example en .env et remplir toutes les valeurs (par environnement)
2. Déposer best_model.pt dans le volume Docker models/ sur le VPS (copie SSH directe)
3. Configurer les secrets GitHub nécessaires à la CI (SECRET_KEY, ADMIN_USERNAME, ADMIN_PASSWORD)
```

## Configuration (secrets, registry, VPS)

Pas de registry Docker externe : Coolify build les images directement sur le VPS à
partir du code source, aucun push vers Docker Hub / ghcr.io.

Variables d'environnement à définir dans le `.env` de chaque environnement Coolify
(voir `.env.example` pour la liste complète et les valeurs par défaut) :

| Catégorie | Variables |
|---|---|
| Base de données | `DATABASE_URL`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` |
| Sécurité JWT | `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` |
| Compte admin | `ADMIN_USERNAME`, `ADMIN_PASSWORD` |
| API | `API_HOST`, `API_PORT`, `APP_ENV`, `APP_HOST`, `APP_PORT` |
| CORS | `CORS_ORIGINS` (jamais `*` en production — incompatible avec `allow_credentials=True`) |
| Modèle | `MODEL_PATH`, `REPORTS_PATH` |
| Monitoring | `GRAFANA_PASSWORD`, `GRAFANA_URL` |

Ports exposés par les images (voir `Dockerfile.api`/`Dockerfile.front`) :

| Service | Port interne | Doit correspondre à |
|---|---|---|
| API (uvicorn) | 8000 | `API_PORT`/`APP_PORT` dans `.env` |
| Frontend (Streamlit) | 8501 | — |

## Procédure de test et debug

- **Avant tout push** : la CI (`ci-app.yml`) valide déjà que les deux `Dockerfile`
  construisent sans erreur — un échec de cette étape signale un problème qui
  bloquerait aussi le build Coolify (voir [docs/ci_application.md](ci_application.md)).
- **Healthcheck API** : `docker-compose.yml` définit un healthcheck sur `GET /health`
  (`interval: 30s`, `retries: 5`, `start_period: 60s`) — le `start_period` élargi
  tient compte du démarrage plus long en PostgreSQL async (attente de
  `postgres_preprod`/`postgres` sain, `create_all` + bootstrap admin, puis
  chargement du modèle MobileNetV2, avant que l'API ne réponde).
- **Diagnostiquer un déploiement qui ne démarre pas** : dans l'interface Coolify,
  consulter les logs de build puis les logs runtime du conteneur `api` — un
  healthcheck qui échoue en boucle empêche `front` de démarrer (dépendance
  `condition: service_healthy`).
- **Tester la stack en local avant de pousser** :
  ```bash
  just up-dev
  # équivalent à :
  docker compose -f docker-compose.yml -f docker-compose.override.yml up
  ```
  Reproduit fidèlement la configuration préprod (`postgres_preprod`, `APP_ENV=development`).
- **Tester uniquement la configuration prod en local** :
  ```bash
  docker compose -f docker-compose.yml up
  ```

## Déclenchement manuel

Un push sur `develop` ou `main` suffit à déclencher un déploiement — aucune action
manuelle n'est nécessaire dans le cas courant. Pour redéployer sans nouveau commit
(ex. après un changement de variable d'environnement) : bouton **Redeploy** dans
l'interface Coolify de l'application concernée — ce document ne peut pas fournir de
capture d'écran de cette interface (accès VPS non disponible depuis cet
environnement de rédaction) ; la procédure Coolify générique s'applique telle quelle.


---

*Accessibilité : document Markdown structuré par hiérarchie de titres (H1→H3), tableaux avec en-têtes de colonnes, aucune information portée uniquement par la couleur ; lisible par un lecteur d'écran et navigable au clavier depuis GitHub.*
