# CD Application — TomatoScan

Documente la chaîne de déploiement continu de l'application (API + frontend).

Ferme le ticket [#40 — docs: documentation pipeline CD application](https://github.com/sulivan-moreau/tomatoscan/issues/40).

## Deux maillons : livraison des images (GitHub Actions) + déploiement (Coolify)

Le déploiement continu de l'application repose sur **deux maillons complémentaires** :

1. **Livraison des images vers ghcr.io — job `livraison` de `ci-app.yml`** (GitHub
   Actions). Sur push `develop`/`main`, **après** que le job `test` soit vert
   (`needs: test`), ce job construit les images API et frontend et les **pousse sur
   GitHub Container Registry** (`ghcr.io`), taguées par le SHA du commit. C'est
   l'**étape de livraison applicative conditionnée au succès des tests** (compétence
   C19) : plus aucune image n'est publiée depuis une PR ni depuis du code non testé.
2. **Déploiement sur le VPS — Coolify.** C'est **Coolify**, une plateforme PaaS
   auto-hébergée sur le VPS OVH, qui reste la **cible de déploiement finale** : il
   surveille le dépôt Git et redéploie à chaque push. Coolify build ses propres images
   à partir des mêmes `Dockerfile.api`/`Dockerfile.front` puis démarre les conteneurs.

```
push sur develop → job "test" (ci-app.yml) vert
                 → job "livraison" pousse les images sur ghcr.io (taguées par SHA)
                 → Coolify déploie la préprod (PostgreSQL async, docker-compose.override.yml)
push sur main    → idem, puis Coolify déploie la prod (docker-compose.yml seul)
```

### Ce que « conditionné au succès des tests » veut dire ici (honnêtement)

Le job `livraison` a `needs: test` : il **ne peut pas** publier d'image si les tests
échouent — c'est vérifiable dans `ci-app.yml`. En revanche, Coolify observe le dépôt
Git indépendamment et build ses **propres** images. Pour que la chaîne complète (jusqu'au
VPS) soit réellement pilotée par la CI, le maillon manquant est la **protection de
branche** décrite plus bas : exiger le job `test` vert avant tout merge sur
`develop`/`main` garantit que **seul du code testé atteint ces branches**, donc que
Coolify ne déploie que du code testé. Livraison ghcr.io (gate technique `needs: test`)
+ protection de branche (gate humaine sur le merge) forment ensemble la garantie.

> **Preuve à constater sur GitHub.** Ce document décrit le job `livraison` tel qu'il
> est écrit dans `ci-app.yml` ; sa syntaxe YAML est validée localement
> (`yaml.safe_load`), mais **l'exécution réelle d'un run GitHub Actions ne peut pas
> être constatée depuis l'environnement de rédaction** (pas d'accès au runner). Le
> premier run vert (push sur `develop`) et la présence des images sur
> `ghcr.io/sulivan-moreau/tomatoscan-{api,front}` seront à vérifier dans l'onglet
> **Actions** et **Packages** du dépôt. Aucun run vert n'est affirmé ici.

## Sommaire

1. [Toutes les étapes et déclencheurs](#toutes-les-étapes-et-déclencheurs)
2. [Installation](#installation)
3. [Configuration (secrets, registry, VPS)](#configuration-secrets-registry-vps)
4. [Procédure de test et debug](#procédure-de-test-et-debug)
5. [Protection de branche (à activer côté GitHub)](#protection-de-branche-à-activer-côté-github)
6. [Déclenchement manuel](#déclenchement-manuel)

## Toutes les étapes et déclencheurs

| Étape | Déclencheur / mécanisme |
|---|---|
| 1. Push sur `develop` ou `main` | Déclenche le job `test` de `ci-app.yml` (GitHub Actions) et notifie Coolify (webhook) |
| 2. Job `test` (GitHub Actions) | Tests + lint + build Docker de validation — doit être **vert** pour autoriser la livraison |
| 3. Job `livraison` (GitHub Actions) | `needs: test` : build + push des images API/frontend sur `ghcr.io`, taguées par le SHA du commit — **uniquement sur push `develop`/`main`, jamais sur PR** (compétence C19) |
| 4. Build des images Docker (Coolify) | Coolify build `Dockerfile.api` et `Dockerfile.front` à partir du commit poussé (cible de déploiement finale sur le VPS) |
| 5. Sélection de la stack Compose | `develop` → `docker-compose.yml` + `docker-compose.override.yml` (préprod, `postgres_preprod`, `APP_ENV=development`) ; `main` → `docker-compose.yml` seul (prod, service `postgres`) |
| 6. Démarrage des conteneurs | `api`, `front`, la base PostgreSQL correspondante, `prometheus`, `grafana` — voir [docs/monitoring.md](monitoring.md) |
| 7. Attente de disponibilité | `front` attend que `api` passe `service_healthy` (healthcheck `GET /health`) avant de démarrer — évite que le frontend serve une API pas encore prête |
| 8. Bascule de trafic | Gérée par Coolify (reverse proxy interne) une fois les conteneurs sains |

Les étapes 2 et 3 (GitHub Actions) et les étapes 4 à 8 (Coolify) se déroulent en
parallèle après le push ; la protection de branche recommandée plus bas garantit que
seul du code ayant passé l'étape 2 arrive sur `develop`/`main`, donc que Coolify (étape
4+) ne déploie que du code testé.

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

**Registry — ghcr.io (GitHub Container Registry).** Le job `livraison` de `ci-app.yml`
pousse les images API et frontend sur `ghcr.io/sulivan-moreau/tomatoscan-api` et
`.../tomatoscan-front`, taguées par le SHA du commit. Aucun secret à créer : le job
s'authentifie avec le `GITHUB_TOKEN` intégré au run, via la permission
`packages: write` déclarée dans le workflow. Les packages publiés apparaissent dans
l'onglet **Packages** du dépôt.

> Coolify, lui, build ses images **directement sur le VPS** à partir du code source
> (il ne tire pas les images de ghcr.io) : la publication ghcr.io est un artefact de
> livraison versionné et traçable, pas la source du déploiement Coolify. Faire
> consommer par Coolify les images ghcr.io (au lieu de rebuild) est une évolution
> possible, non mise en place ici.

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

## Protection de branche (à activer côté GitHub)

**Statut : recommandation non encore appliquée** — sa configuration exige un accès
administrateur au dépôt GitHub, hors de portée depuis l'environnement de rédaction de
cette documentation. Elle est décrite ici comme **action à réaliser côté GitHub**, pas
comme un état constaté.

Pour que la chaîne CD soit réellement pilotée par les tests jusqu'au déploiement
Coolify, il faut empêcher qu'un merge non testé atteigne `develop`/`main`. À configurer
dans **GitHub → Settings → Branches → Branch protection rules**, une règle pour
`develop` et une pour `main` :

- **Require status checks to pass before merging** → cocher le check
  **`Tests & Lint (Python 3.11)`** (le job `test` de `ci-app.yml`). Un merge devient
  alors impossible tant que ce job n'est pas vert.
- **Require a pull request before merging** (recommandé) — interdit le push direct sur
  `develop`/`main`, force le passage par une PR (donc par la CI).
- **Require branches to be up to date before merging** (optionnel) — force à re-tester
  après rebase sur la cible.

Effet combiné avec le reste de la chaîne : la protection garantit que seul du code
ayant passé le job `test` arrive sur `develop`/`main` ; le job `livraison`
(`needs: test`) ne publie d'image ghcr.io qu'après ce même job vert ; et Coolify, qui
déploie ce qui est sur `develop`/`main`, ne déploie donc que du code testé.

## Déclenchement manuel

Un push sur `develop` ou `main` suffit à déclencher un déploiement — aucune action
manuelle n'est nécessaire dans le cas courant. Pour redéployer sans nouveau commit
(ex. après un changement de variable d'environnement) : bouton **Redeploy** dans
l'interface Coolify de l'application concernée — ce document ne peut pas fournir de
capture d'écran de cette interface (accès VPS non disponible depuis cet
environnement de rédaction) ; la procédure Coolify générique s'applique telle quelle.


---

*Accessibilité : document Markdown structuré par hiérarchie de titres (H1→H3), tableaux avec en-têtes de colonnes, aucune information portée uniquement par la couleur ; lisible par un lecteur d'écran et navigable au clavier depuis GitHub. Le Markdown brut est le format standard de la documentation technique développeur — aucune mise en forme visuelle propriétaire (police, couleur de fond, contraste personnalisé) à justifier séparément : le rendu (contraste, navigation clavier, lecteur d'écran) est entièrement délégué à la plateforme d'hébergement (GitHub), déjà conforme aux standards d'accessibilité web usuels.*
