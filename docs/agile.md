# Coordination agile — TomatoScan

Documente la méthode agile appliquée sur le projet TomatoScan.

Ferme le ticket [#29 — docs: coordination agile et pilotage du projet](https://github.com/sulivan-moreau/tomatoscan/issues/29).

> **Ce document contient deux types de contenu** :
> - Ce qui est **vérifiable depuis le dépôt Git** (issues, branches, PR, chronologie
>   des commits) — rédigé et rempli ci-dessous à partir de preuves réelles.
> - Ce qui nécessite une **capture depuis l'interface GitHub Projects**, à laquelle
>   cet environnement de rédaction n'a pas accès (pas de session GitHub interactive,
>   pas de `gh` CLI installé ici). Ces sections sont clairement marquées
>   **⚠️ À compléter par le candidat** avec l'emplacement exact et le contenu attendu.
>
> **Artefacts de pilotage complémentaires (générés depuis Git, réels)** :
> - [docs/pr_cadence.md](pr_cadence.md) — suivi chiffré réel de la cadence (PR fusionnées
>   par semaine, graphiques Mermaid), substitut honnête du burndown chart.
> - [docs/backlog.md](backlog.md) — backlog versionné reconstruit (user stories métier,
>   tâches techniques, correctifs), avec traçabilité issue ↔ PR ↔ branche.
> - [docs/journal_rituels.md](journal_rituels.md) — structure du journal des rituels
>   (à compléter par le candidat avec ses vrais points de suivi).

## Sommaire

1. [Contexte et rôles](#contexte-et-rôles)
2. [Méthode appliquée](#méthode-appliquée)
3. [Cadence observée (preuve : historique Git)](#cadence-observée-preuve--historique-git)
4. [Kanban](#kanban)
5. [Burndown chart](#burndown-chart)
6. [Imprévus rencontrés et gestion](#imprévus-rencontrés-et-gestion)
7. [Changements de plan en cours de projet](#changements-de-plan-en-cours-de-projet)

## Contexte et rôles

TomatoScan est un projet de certification individuel (candidat DevIA Simplon). Les
rôles SCRUM habituellement répartis dans une équipe sont donc assumés par une seule
personne :

| Rôle SCRUM | Assumé par |
|---|---|
| Product Owner (priorisation, définition des critères d'acceptation) | Sulivan Moreau |
| Scrum Master (facilitation, suivi d'avancement) | Sulivan Moreau |
| Développeur | Sulivan Moreau |

Le référentiel de certification (jury Simplon) joue le rôle d'exigence externe
équivalente à un « client » dans un contexte SCRUM classique.

## Méthode appliquée

Le projet suit un cycle **issue → branche dédiée → Pull Request → merge sur `develop`**,
observable intégralement dans l'historique Git :

1. Chaque fonctionnalité ou correctif est rattaché à une **issue GitHub** numérotée
   (ex. issue #5 « endpoint POST /predict », issue #16 « dashboard Grafana »).
2. Une **branche dédiée** est créée par sujet, avec une convention de nommage
   cohérente : `feature/<sujet>` pour une fonctionnalité, `fix/<sujet>` pour un
   correctif (ex. `feature/api-predict`, `fix/torch-cpu`).
3. Le travail est intégré via une **Pull Request** vers `develop`, fusionnée après
   revue. L'historique compte **41 commits de merge** au total
   (`git log --merges --oneline | wc -l`) : **40 PR de fonctionnalité ou de correctif**
   fusionnées sur `develop` + **1 promotion initiale `develop → main`** (PR #42, seul
   merge présent sur `main`). Le détail par semaine est dans
   [docs/pr_cadence.md](pr_cadence.md).
4. `develop` est périodiquement fusionné vers `main` pour les mises en production
   (déploiement automatique par Coolify, voir [docs/cd_application.md](cd_application.md)).

Ce fonctionnement correspond à un flux de type **Kanban / SCRUM allégé** (petits lots
de travail livrés en continu, un ticket = une branche = une PR), plutôt qu'à un SCRUM
strict à sprints de durée fixe avec cérémonies formelles (daily, sprint planning,
rétrospective) — aucune trace de telles cérémonies n'existe dans le dépôt Git, ce qui
est cohérent avec un projet individuel où elles perdent une partie de leur utilité
(pas de coordination d'équipe à synchroniser).

> ⚠️ **À compléter par le candidat** : si des cérémonies ou points de suivi ont bien
> été tenus (revues personnelles, journal de bord, **points hebdomadaires avec le
> formateur référent Simplon**), les consigner dans
> [docs/journal_rituels.md](journal_rituels.md) — ce fichier fournit la structure du
> journal de bord et les modalités à renseigner. Le seul historique Git ne peut pas
> attester ces rituels.

## Cadence observée (preuve : historique Git)

Cadence réelle des **PR fusionnées** par semaine ISO
(`git log --merges --date=format:'%G-W%V' --pretty="%ad" | sort | uniq -c`). Le suivi
chiffré complet, avec graphiques Mermaid et vue cumulée, est dans
[docs/pr_cadence.md](pr_cadence.md) :

| Semaine ISO | Période | PR fusionnées | Total commits |
|---|---|---:|---:|
| 2026-W26 | 22/06 – 28/06 | 3 | 9 |
| 2026-W27 | 29/06 – 05/07 | 20 | 40 |
| 2026-W28 | 06/07 – 12/07 | 0 | 12 |
| 2026-W29 | 13/07 – 19/07 | 12 | 38 |
| 2026-W30 | 20/07 – 26/07 | 6 | 15 |

Deux métriques distinctes y figurent : les **PR fusionnées** (41 au total, l'unité de
livraison) et le **nombre total de commits** par semaine (rythme de travail brut). La
semaine W28 illustre l'écart : 0 PR fusionnée mais 12 commits — travail de rédaction des
specs poussé sur les branches `25-/26-/27-docs-*`, fusionnées seulement en W29.

Repères notables :

- **2026-06-23 → 2026-07-02** : mise en place du socle (modèle, API, base de données,
  authentification, frontend, CI, premier monitoring) — 20 PR sur ~10 jours.
- **2026-07-03 → 2026-07-12** : creux d'activité apparent dans les commits de code
  (probablement du temps consacré à la rédaction/spécifications — voir les branches
  `25-docs-*`, `26-docs-*`, `27-docs-*` fusionnées le 2026-07-19, contenant les user
  stories, le MCD et les spécifications techniques rédigées durant cette période).
- **2026-07-13 → 2026-07-19** : reprise intensive côté code — gestion des rôles,
  migration PostgreSQL asynchrone, corrections de bugs (voir
  [Imprévus rencontrés](#imprévus-rencontrés-et-gestion)), audit et corrections de
  code pour les blocs E3/E4.

Cette chronologie est un **indicateur de cadence réel et vérifiable**, mais ne
remplace pas un burndown chart formel (voir plus bas) : elle mesure des fusions de
code, pas un nombre de points d'histoire restants sur un sprint.

## Kanban

Un tableau Kanban existe sur **GitHub Projects**, confirmé par Satoshi comme utilisé
tout au long du projet (colonnes de suivi des issues listées dans ce document : #18,
#21, #24, #29, #36, #38, #40, #41, etc.).

> ⚠️ **À compléter par le candidat** — ce document ne peut pas capturer l'interface
> GitHub Projects (pas d'accès interactif ni `gh` CLI depuis cet environnement, aucune
> image n'est fabriquée ici). **À insérer : captures réelles du GitHub Project** aux
> trois moments suivants :
>
> `[À insérer : capture réelle du GitHub Project — début de projet, colonnes peu remplies]`
>
> `[À insérer : capture réelle du GitHub Project — mi-parcours]`
>
> `[À insérer : capture réelle du GitHub Project — état récent, preuve de l'usage continu dans le temps (critère d'acceptation du ticket #29)]`
>
> En attendant ces captures, le suivi chiffré réel de l'avancement est disponible et
> versionné dans [docs/pr_cadence.md](pr_cadence.md), et le backlog reconstruit dans
> [docs/backlog.md](backlog.md). Vérifier aussi que le tableau est à jour par rapport à
> l'état réel des issues (issues fermées déplacées en conséquence).

## Burndown chart

Un burndown chart SCRUM formel (points d'histoire restants par jour de sprint)
suppose un découpage en sprints avec estimation en points — **aucune trace d'une
telle estimation n'existe dans ce dépôt** (pas de champ « story points » visible
dans les issues listées, pas de fichier de suivi de sprint versionné). Il serait
malhonnête de fabriquer ici des chiffres de points d'histoire qui n'ont jamais été
posés.

Le substitut honnête retenu est **déjà généré et versionné** :
[docs/pr_cadence.md](pr_cadence.md) présente, à partir des PR réellement fusionnées, un
tableau de cadence par semaine, un graphique en barres (PR par semaine) et une **courbe
d'avancement cumulé (burnup)** en Mermaid. Il est présenté pour ce qu'il est — un suivi
de livraison basé sur Git — et non comme un burndown SCRUM classique qu'il n'est pas.

> ⚠️ **À compléter par le candidat** (facultatif) : si un burndown ou une roadmap avec
> dates cibles existe dans GitHub Projects, en insérer une capture réelle ici en
> complément. Ne pas fabriquer de chiffres de points d'histoire.

## Imprévus rencontrés et gestion

Liste construite à partir des commits `fix:` réels du dépôt (pas de reconstruction
a posteriori) :

| Date | Imprévu | Comment il a été géré |
|---|---|---|
| 2026-07-02 | Build Docker échouait sur le VPS : torch résolvait des dépendances CUDA/NVIDIA (~2 Go), absentes de la cible de déploiement | Installation explicite de la variante CPU-only de torch/torchvision avant `uv sync`/`pip install`, appliquée de façon cohérente dans `Dockerfile.api` et `ci-model.yml` |
| 2026-07-02 | Conteneurs inaccessibles entre eux sur le réseau Coolify | Passage à un réseau Docker externe partagé (`coolify`), suppression des ports exposés inutiles |
| 2026-07-07 | Dashboard Grafana masqué par le volume persistant `grafana_data` (la configuration au build était écrasée au démarrage) | Déplacement de la configuration hors du chemin du volume monté |
| 2026-07-14 | Bug intermittent : un admin se faisait bloquer comme un agriculteur (« accès réservé ») sur le VPS | Diagnostiqué en deux temps : d'abord un problème de décodage base64url vs base64 standard du JWT, puis une réécriture du décodage via PyJWT pour recalculer systématiquement le rôle depuis le token plutôt que depuis un état mis en cache |
| 2026-07-15 | Passage à PostgreSQL asynchrone (asyncpg) a cassé la CI (SQLite synchrone incompatible avec `create_async_engine`), puis révélé une incompatibilité `BaseHTTPMiddleware`/asyncpg (`RuntimeError: Future attached to a different loop`) | CI migrée vers un vrai service PostgreSQL ; middlewares personnalisés réécrits en ASGI pur (`EnteteSecuriteMiddleware`, rate limiting) pour rester sur la tâche asyncio d'origine |
| 2026-07-16 | Le conteneur API échouait parfois son healthcheck au démarrage sur PostgreSQL (chemin de démarrage plus long qu'avec SQLite : attente BDD + bootstrap + chargement modèle) | `start_period`/`retries` du healthcheck Docker élargis pour refléter le temps de démarrage réel mesuré |

## Changements de plan en cours de projet

| Changement | Raison |
|---|---|
| SQLite → PostgreSQL asynchrone (asyncpg) en cours de projet | Aligner l'environnement de développement/CI sur la cible réelle de production (PostgreSQL), après un premier socle construit sur SQLite pour aller vite au démarrage |
| Rôle par défaut deviné en cas d'absence du claim JWT `role` → rejet explicite 401 | Suite au diagnostic du bug intermittent d'accès admin (voir tableau ci-dessus) : un token sans rôle ne doit jamais être traité comme un rôle par défaut silencieux, même si ce cas ne devrait normalement jamais se produire |
| Verrouillage après échecs de connexion consécutifs ajouté en plus du rate limiting existant | Le rate limiting seul (débit par IP) ne protège pas contre un attaquant lent et distribué ciblant un compte précis — ajouté après audit de sécurité du projet |
| Suite de tests consolidée après un pic de variantes redondantes ; **101 tests** aujourd'hui (`uv run pytest tests/ -q --collect-only` → `101 tests collected`) | Un audit de la suite a identifié de nombreuses variantes redondantes d'un même scénario sans gain de couverture réel ; règle retenue : un test nominal + un test d'erreur obligatoire par fonction, sauf régression de bug réel toujours conservée (voir [docs/tests.md](tests.md)) |
| Déclencheur d'alerte de réentraînement (C11) ajouté au pipeline modèle (2026-07-16) | Non prévu dans le socle initial — ajouté pour répondre explicitement au critère de compétence sur les déclencheurs d'entraînement continu |


---

*Accessibilité : document Markdown structuré par hiérarchie de titres (H1→H3), tableaux avec en-têtes de colonnes, aucune information portée uniquement par la couleur ; lisible par un lecteur d'écran et navigable au clavier depuis GitHub. Le Markdown brut est le format standard de la documentation technique développeur — aucune mise en forme visuelle propriétaire (police, couleur de fond, contraste personnalisé) à justifier séparément : le rendu (contraste, navigation clavier, lecteur d'écran) est entièrement délégué à la plateforme d'hébergement (GitHub), déjà conforme aux standards d'accessibilité web usuels.*
