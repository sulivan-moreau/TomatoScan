# Documentation technique — TomatoScan

Documente l'environnement de développement, l'architecture applicative et les
procédures d'exécution du projet TomatoScan.

Ferme le ticket [#36 — docs: documentation technique du projet](https://github.com/sulivan-moreau/tomatoscan/issues/36).

## Sommaire

1. [Installation de l'environnement de développement](#installation-de-lenvironnement-de-développement)
2. [Architecture applicative](#architecture-applicative)
3. [Dépendances](#dépendances)
4. [Éco-conception](#éco-conception)
5. [Procédure d'exécution des tests](#procédure-dexécution-des-tests)
6. [Pourquoi le monitoring est réservé aux comptes admin](#pourquoi-le-monitoring-est-réservé-aux-comptes-admin)

## Installation de l'environnement de développement

Prérequis : Python 3.11 à 3.13, [uv](https://docs.astral.sh/uv/), Docker (pour
PostgreSQL/monitoring en local), [just](https://github.com/casey/just) (optionnel,
raccourcis de commandes).

```bash
git clone https://github.com/sulivan-moreau/tomatoscan.git
cd tomatoscan

# Variables d'environnement — voir la liste complète dans .env.example
cp .env.example .env

# Dépendances (dont le groupe dev : pytest, ruff, etc.)
just install
# équivalent : uv sync --extra dev
```

Lancer les composants individuellement :

```bash
just api    # API FastAPI, http://localhost:8000 (docs interactives sur /docs)
just app    # Frontend Streamlit, http://localhost:8501
just up     # Stack Docker complète (API + front + PostgreSQL + Prometheus + Grafana)
```

La base de données doit exister avant le premier démarrage de l'API (celle-ci crée
les tables et un compte admin au démarrage, voir [Architecture applicative](#architecture-applicative)) ;
en local hors Docker, `DATABASE_URL` peut pointer vers un SQLite
(`sqlite+aiosqlite:///./dev.db`) ou un PostgreSQL local.

## Architecture applicative

```
┌─────────────┐      JWT Bearer      ┌──────────────────┐
│  Frontend   │ ───────────────────► │   API FastAPI     │
│  Streamlit  │ ◄─────────────────── │                    │
│  (port 8501)│        JSON          │   (port 8000)      │
└─────────────┘                      └─────────┬──────────┘
                                                │
                        ┌───────────────────────┼───────────────────────┐
                        ▼                       ▼                       ▼
                ┌───────────────┐     ┌──────────────────┐   ┌────────────────────┐
                │  PostgreSQL    │     │ Modèle MobileNetV2│   │ Prometheus/Grafana │
                │  (users,       │     │ (.pt, volume       │   │ (métriques /metrics/)│
                │  predictions)  │     │  Docker en lecture │   └────────────────────┘
                └───────────────┘     │  seule)            │
                                       └──────────────────┘
```

Description textuelle équivalente (accessibilité) : le frontend Streamlit appelle
l'API FastAPI en HTTP, authentifiée par JWT Bearer. L'API lit/écrit dans PostgreSQL
(comptes utilisateurs, historique de prédictions), charge un checkpoint MobileNetV2
depuis un volume Docker en lecture seule pour servir les prédictions, et expose ses
métriques sur `/metrics/` pour Prometheus, lui-même visualisé par Grafana.

### Couches du code (`src/tomatoscan/`)

| Dossier | Rôle |
|---|---|
| `api/main.py` | Point d'entrée FastAPI : middlewares (CORS, headers de sécurité, rate limiting), cycle de vie (`lifespan` — création des tables, bootstrap du compte admin, chargement du modèle), montage `/metrics` |
| `api/routes/` | Un routeur par domaine : `auth`, `health`, `history`, `predict`, `reports`, `users` |
| `api/schemas/` | Modèles Pydantic de requête/réponse (validation d'entrée, ex. longueur minimale du mot de passe) |
| `api/core/` | `security.py` (JWT : création, décodage, dépendances de rôle), `limiter.py` (configuration slowapi) |
| `api/services/model_service.py` | Chargement et inférence du modèle MobileNetV2, isolé des routes (mockable en test) |
| `api/metrics.py` | Déclaration des métriques Prometheus (voir [docs/monitoring.md](monitoring.md)) |
| `database/` | `modeles.py` (SQLAlchemy `User`, `Prediction`), `connexion.py` (moteur async/`SessionLocal`), `bootstrap.py` (création idempotente du compte admin) |
| `model/` | `preprocess.py` (dataset, transforms), `train.py` (entraînement MobileNetV2 transfer learning), `evaluate.py` (inférence, rapport, seuil de réentraînement) — indépendant de l'API, appelé en CLI ou depuis `scripts/` |
| `front/pages/` | Une page Streamlit par écran : `accueil`, `login`, `predict`, `history`, `dashboard` (admin), `creer_membre` (admin) |
| `front/utils/api_client.py` | Client HTTP vers l'API (login, refresh, predict, history, users, reports) |
| `front/utils/session.py` | Gestion de `st.session_state` (token, rôle) et gestion centralisée des 401 |

### Flux d'authentification

`POST /auth/token` (username/password) → JWT signé (claims `sub`, `role`, `exp`) →
transmis en header `Authorization: Bearer <token>` sur toutes les routes protégées.
`POST /auth/refresh` réémet un token avant expiration si le token courant est encore
valide (voir `front/utils/api_client.py::renouveler_si_necessaire`, déclenché
automatiquement à chaque rerun Streamlit). Le rôle (`admin` ou `agriculteur`)
détermine l'accès aux pages admin côté frontend et aux routes réservées côté API
(`verifier_role_admin`).

### Démarrage de l'API (`lifespan`)

1. Chargement de `.env`.
2. Création des tables PostgreSQL si absentes (`Base.metadata.create_all`, idempotent).
3. Bootstrap d'un compte admin (`ADMIN_USERNAME`/`ADMIN_PASSWORD`) s'il n'existe pas déjà.
4. Chargement unique du modèle MobileNetV2 en mémoire (`model_service.initialiser_modele`).

C'est ce chemin de démarrage (attente PostgreSQL + requêtes réseau + chargement
modèle) qui dimensionne le `start_period` du healthcheck Docker — voir
[docs/cd_application.md](cd_application.md#procédure-de-test-et-debug).

## Dépendances

Gérées par [uv](https://docs.astral.sh/uv/) via `pyproject.toml`/`uv.lock` pour
l'API/modèle, et `src/tomatoscan/front/requirements.txt` (pip) pour le frontend —
séparés volontairement pour ne pas embarquer les dépendances ML lourdes
(torch/tensorflow) dans l'image du frontend.

| Domaine | Dépendances principales |
|---|---|
| API | `fastapi`, `uvicorn`, `python-jose[cryptography]`, `passlib[bcrypt]`, `slowapi` |
| Modèle | `torch`, `torchvision` (entraînement/inférence — moteur cible en CI/prod), `tensorflow-macos`/`tensorflow-metal` (macOS uniquement, `sys_platform == 'darwin'`), `scikit-learn` (métriques d'évaluation), `pillow`, `numpy`, `matplotlib` |
| Frontend | `streamlit`, `requests`, `pyjwt` |
| Données | `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `python-dotenv` |
| Observabilité | `loguru` (logs), `prometheus-client` (métriques) |
| Dataset | `kaggle` (téléchargement PlantVillage) |
| Dev (`--extra dev`) | `pytest`, `pytest-asyncio`, `httpx`, `pytest-cov`, `ruff`, `aiosqlite` |

> Note : `tensorflow-macos`/`tensorflow-metal` sont déclarés comme dépendances mais
> non importés nulle part dans `src/` (aucune occurrence de `import tensorflow`) —
> le pipeline d'entraînement/inférence réel utilise exclusivement `torch`/`torchvision`
> (voir `src/tomatoscan/model/train.py`, `evaluate.py`). Restant du choix technique
> initial du projet, sans impact fonctionnel actuel.

## Éco-conception

### Choix d'infrastructure

Justification détaillée des choix éco-responsables (open source plutôt que SaaS
propriétaire, VPS OVH certifié ISO 50001, MobileNetV2 CPU-only sans GPU en
inférence, aucun stockage d'image uploadée, `uv` pour réduire le temps CPU
d'installation, images Docker `python:3.11-slim`) : voir le Livrable 5 de
[`docs/specs_techniques.pdf`](specs_techniques.pdf) (issue #27).

### Éco-conception applicative (interface Streamlit)

Au-delà de l'infrastructure, trois actes d'éco-conception sont intégrés au **code**
du frontend, traçables et vérifiables (référentiels de repère : RGESN / EcoIndex) :

| Acte | Fichier | Effet |
|---|---|---|
| **Limite d'upload alignée sur l'API** | `src/tomatoscan/front/.streamlit/config.toml` (`[server] maxUploadSize = 5`) | Empêche le transfert d'une image que l'API rejetterait de toute façon au-delà de 5 Mo (défaut Streamlit : 200 Mo). Bande passante et énergie de transfert économisées côté client comme côté serveur. |
| **Compression / redimensionnement client avant envoi** | `src/tomatoscan/front/pages/predict.py` (`_compresser_image`) | Le plus grand côté de l'image est borné à 1024 px avant l'envoi (le modèle infère en 224×224), avec ré-encodage JPEG q85 / PNG `optimize` et **conservation du format d'origine** (le type MIME reste dans les formats acceptés par l'API). Sur une photo smartphone typique (~4000×3000), la charge réseau est fortement réduite. |
| **Mise en cache des appels du tableau de bord** | `src/tomatoscan/front/pages/dashboard.py` (`@st.cache_data(ttl=60)`) | Les appels `get_reports` / `list_users` / `get_history` ne sont plus rejoués à chaque re-run Streamlit (chaque interaction relance le script) ; le cache est invalidé après une suppression pour garder des données fraîches. Réduit le nombre de requêtes API et la charge PostgreSQL. |

### Accessibilité de l'interface

Standard visé : **WCAG 2.1 niveau AA** (cohérent avec les critères d'acceptation des
user stories). Points traités dans le code : contrastes des bandeaux de résultat
calculés et conformes AA (ratios documentés dans `pages/predict.py`), libellés
explicites sur tous les champs, pictogrammes en SVG `aria-hidden` doublés d'un libellé
texte, texte alternatif descriptif sur l'aperçu de l'image analysée, et forçage de la
langue de page en `fr` (contournement documenté : Streamlit 1.58 sert `lang="en"` en dur
et n'expose aucune option native, la langue est corrigée par injection JS — limite
assumée à réévaluer si Streamlit expose un réglage natif).

## Procédure d'exécution des tests

```bash
uv run pytest tests/ -v --cov=src/tomatoscan --cov-report=term-missing
# ou : just test
```

Détail complet (liste des cas testés par périmètre, stratégie de mock, seuils de
couverture, génération du rapport HTML) : voir [docs/tests.md](tests.md).

## Pourquoi le monitoring est réservé aux comptes admin

Le tableau de bord Grafana (métriques Prometheus — taux d'erreurs, temps de réponse,
distribution des classes détectées, confiance moyenne du modèle, voir
[docs/monitoring.md](monitoring.md)) n'est accessible que depuis la page
`dashboard.py` du frontend, elle-même réservée aux comptes `admin`.

**Décision retenue (choix produit, tranché explicitement pour ce projet)** : garder
cet accès admin-only plutôt que de l'ouvrir aux comptes `agriculteur`.

**Justification** : les métriques exposées (taux d'erreurs applicatif, latence
d'inférence, dérive de confiance du modèle) sont des indicateurs **opérationnels**,
destinés à qui exploite la plateforme — pas des informations utiles au métier d'un
agriculteur, dont le seul besoin fonctionnel est d'obtenir un diagnostic sur sa photo
de feuille (`POST /predict`) et de consulter son propre historique
(`GET /predictions/history`, déjà accessible à tous les rôles, filtré par
utilisateur). Exposer le dashboard de monitoring à tous les comptes ajouterait une
surface fonctionnelle et une charge de compréhension sans bénéfice pour l'utilisateur
final, pour un projet dont le périmètre reste volontairement simple.


---

*Accessibilité : document Markdown structuré par hiérarchie de titres (H1→H3), tableaux avec en-têtes de colonnes, aucune information portée uniquement par la couleur ; lisible par un lecteur d'écran et navigable au clavier depuis GitHub. Le Markdown brut est le format standard de la documentation technique développeur — aucune mise en forme visuelle propriétaire (police, couleur de fond, contraste personnalisé) à justifier séparément : le rendu (contraste, navigation clavier, lecteur d'écran) est entièrement délégué à la plateforme d'hébergement (GitHub), déjà conforme aux standards d'accessibilité web usuels.*
