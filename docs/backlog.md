# Backlog produit — TomatoScan (reconstruit depuis Git)

> **Nature de ce document.** Backlog **versionné**, reconstruit à partir des **traces Git
> réelles** du dépôt : noms de branches, numéros de Pull Request (messages de merge) et
> numéros d'issue référencés dans les messages de commit. L'outil `gh` (GitHub CLI)
> **n'est pas installé** dans cet environnement de rédaction (`which gh` → `gh not found`),
> ce qui empêche d'interroger directement l'API GitHub Issues/Projects ; le backlog est
> donc reconstitué depuis ce que Git contient localement.
>
> **Règle d'honnêteté.** Un numéro d'issue n'est indiqué que lorsqu'il apparaît réellement
> dans un message de commit (`git log --all --grep="#"`). Quand aucun numéro n'est
> retrouvable, la cellule porte la mention **« issue non tracée »** — rien n'est inventé.

## Sommaire

1. [Méthode de reconstruction](#méthode-de-reconstruction)
2. [User stories métier](#user-stories-métier)
3. [Tâches techniques](#tâches-techniques)
4. [Correctifs (imprévus)](#correctifs-imprévus)
5. [Branches sans PR fusionnée](#branches-sans-pr-fusionnée)

## Méthode de reconstruction

```bash
which gh                                     # -> gh not found (pas d'accès API GitHub)
git branch -a                                # branches feature/*, fix/*, 25-/26-/27-*
git log --merges --oneline                   # numéros de PR (messages de merge)
git log --all --grep="#[0-9]" --pretty="%s"  # numéros d'issue référencés dans les commits
```

Le numéro d'issue de chaque item provient des sous-titres de commit du type
`feat: ... (issue #N)` ou `docs: ... (#N)`, réellement présents dans l'historique.
Les branches nommées `25-…`, `26-…`, `27-…` correspondent directement aux issues GitHub
#25, #26, #27 (convention de nommage GitHub « numéro-titre-de-l-issue »).

Statut : tous les items listés ci-dessous sont **Fait** (branche fusionnée sur `develop`
via une PR), sauf mention contraire dans la section
[Branches sans PR fusionnée](#branches-sans-pr-fusionnée).

## User stories métier

Les 5 user stories métier du produit (confirmées par les wireframes de la modélisation,
cf. `docs/rapport_E3.md` et livrable issue #26). Chacune peut recouvrir plusieurs PR
(API + frontend).

| # | User story | Issue(s) tracée(s) | PR | Branche(s) | Statut |
|---|---|---|---|---|---|
| US1 | **Prédiction par upload d'image** — l'utilisateur téléverse une photo de feuille et obtient la maladie détectée avec un score de confiance | #5 (API `POST /predict`), #12 (page front predict) | #48, #56 | `feature/api-predict`, `feature/front-predict` | Fait |
| US2 | **Connexion** — l'utilisateur s'authentifie (JWT) pour accéder aux fonctions protégées | #6 (auth API), #13 (auth frontend) | #49, #55 | `feature/api-auth`, `feature/front-auth` | Fait |
| US3 | **Historique des prédictions** — l'utilisateur consulte ses prédictions passées (filtre par maladie) | #32 (`GET /predictions/history`) | #57 | `feature/prediction-history` | Fait |
| US4 | **Dashboard admin** — l'administrateur voit l'historique global et gère la distinction de rôles admin/agriculteur | issue non tracée (fonctionnalité livrée via le développement frontend et les correctifs de rôle) | #82, #84, #87 | `feature/frontend-development`, `fix/role-login-decodage`, `fix/jwt-pyjwt-decode` | Fait |
| US5 | **Création de compte** — l'administrateur crée les comptes utilisateurs (agriculteurs) depuis le dashboard admin | issue non tracée (partie du périmètre dashboard admin, cf. wireframes issue #26) | #82 | `feature/frontend-development` | Fait |

> Note d'honnêteté sur US4/US5 : aucun message de commit ne porte de numéro d'issue dédié
> pour « dashboard admin » ou « création de compte ». Ces user stories sont attestées par
> les wireframes (documentation, issue #26) et livrées dans le développement frontend
> (#82) et les correctifs de gestion des rôles (#84/#87), mais leur traçabilité issue↔PR
> est **partielle** — mention conservée telle quelle plutôt que complétée par un numéro
> inventé.

## Tâches techniques

Tâches d'infrastructure, de qualité et de socle (non directement une valeur métier finale
mais nécessaires au produit) :

| Tâche | Issue | PR | Branche | Statut |
|---|---|---|---|---|
| Entraînement du modèle MobileNetV2 | #30 | #46 | `feature/model-training` | Fait |
| Setup FastAPI + endpoint `/health` | #4 | #47 | `feature/api-setup` | Fait |
| Sécurité OWASP (rate limiting, en-têtes, checklist) | #7 | #50 | `feature/api-security` | Fait |
| Base de données PostgreSQL (modèles User/Prediction, Alembic) | #31 | #51 | `feature/database-setup` | Fait |
| Endpoint `GET /reports` (métriques d'entraînement) | #9 | #52 | `feature/api-reports` | Fait |
| Documentation OpenAPI (descriptions, tags, exemples JWT) | #8 | #53 | `feature/api-docs` | Fait |
| Initialisation frontend Streamlit (navigation, ping API) | #11 | #54 | `feature/front-setup` | Fait |
| Suite de tests + couverture (89 %) | #10 | #58 | `feature/api-tests` | Fait |
| Pipeline CI GitHub Actions (lint, tests, couverture) | #37 | #59 | `feature/ci-app-tests` | Fait |
| CD — Dockerisation API + frontend, compose préprod/prod | #39 | #60 | `feature/cd-app-deployment` | Fait |
| Métriques Prometheus (prédictions, durée, erreurs) | #15 | #70 | `feature/api-metrics` | Fait |
| Dashboard Grafana + Prometheus (panels, alertes) | #16 | #71 | `feature/monitoring-dashboard` | Fait |
| Bonnes pratiques API | issue non tracée | #88 | `feat/bonnes-pratiques-api` | Fait |
| Migration PostgreSQL asynchrone (asyncpg) | issue non tracée | #89 | `feature/postgresql-async-develop` | Fait |
| Déclencheur de réentraînement du modèle (compétence C11) | issue non tracée | #90 | `feature/monitoring-retrain-trigger` | Fait |
| Corrections de code suite à l'audit E3/E4 | issue non tracée | #94 | `feature/corrections-code-e3-e4` | Fait |
| Documentation projet (agile, tests, monitoring, etc.) | issue non tracée | #95 | `feature/docs` | Fait |
| Livrable — user stories et critères d'accessibilité | #25 | #43 | `25-docs-user-stories-et-critères-daccessibilité` | Fait |
| Livrable — MCD Merise, wireframes, diagramme de flux | #26 | #44 | `26-docs-mcd-merise-et-wireframes` | Fait |
| Livrable — spécifications techniques et architecture | #27 | #45 | `27-docs-spécifications-techniques-et-architecture` | Fait |
| Promotion initiale `develop → main` | issue non tracée | #42 | `develop` | Fait |

## Correctifs (imprévus)

Items nés d'un problème rencontré en cours de route (branches `fix/*`), reconstruits depuis
les messages de commit `fix:`. Le détail de la cause et de la résolution est documenté dans
[docs/agile.md](agile.md#imprévus-rencontrés-et-gestion).

| Correctif | Issue | PR | Branche | Statut |
|---|---|---|---|---|
| Décodage JWT base64url (bug d'accès admin intermittent) | issue non tracée | #84 | `fix/role-login-decodage` | Fait |
| Décodage JWT réécrit via PyJWT (rôle recalculé depuis le token) | issue non tracée | #87 | `fix/jwt-pyjwt-decode` | Fait |
| Healthcheck API adapté au démarrage PostgreSQL | issue non tracée | #92 | `fix/healthcheck-api-postgresql` | Fait |
| torch CPU pour le build Docker VPS (suppression dépendances CUDA) | issue non tracée | #68, #69 | `fix/torch-cpu` | Fait |
| Réseau Coolify externe, suppression des ports exposés | issue non tracée | #66 | `fix/docker-network-coolify` | Fait |
| Formatage ruff | issue non tracée | #64 | `fix/ruff-formatfix/ruff-format` | Fait |
| Suppression f-strings sans placeholder (ruff F541) | issue non tracée | #62 | `fix/ruff-f541` | Fait |

## Branches sans PR fusionnée

Branches locales existantes qui **ne correspondent pas à un merge dans l'historique** de
`develop` (travail exploratoire, ou intégré autrement) — listées par honnêteté, statut
**non fusionné** :

| Branche | Observation |
|---|---|
| `fix/issue-metrics` | Contient des commits sur le rapport d'évaluation du modèle et un correctif d'alerte Grafana ; non retrouvée comme merge distinct dans `git log --merges` |
| `mvp` | Branche de travail antérieure (ex. suppression `justfile`) ; non fusionnée telle quelle |
| `docs/rapport-e3` | Branche de rédaction ; contenu non fusionné sous ce nom |

---

*Accessibilité : document Markdown structuré (H1→H2), backlog en tableaux à en-têtes de
colonnes explicites, aucune information portée uniquement par la couleur. Rendu et
navigation délégués à la plateforme d'hébergement (GitHub).*
