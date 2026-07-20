# Rapport E4 — Conception et réalisation d'une application intégrant un service d'IA

| | |
|---|---|
| **Candidat** | Sulivan Moreau |
| **Diplôme** | Développeur en Intelligence Artificielle (RNCP 37827) — Simplon, promotion 2026 |
| **Épreuve** | E4 — Conception et développement d'une application intégrant un service d'IA |
| **Compétences évaluées** | C14, C15, C16, C17, C18, C19 |
| **Projet** | TomatoScan — détection de maladies de la tomate (MobileNetV2, transfer learning, PyTorch) |
| **Dépôt** | https://github.com/sulivan-moreau/TomatoScan |
| **Déploiement** | VPS OVH Roubaix orchestré par Coolify, stack conteneurisée Docker |
| **Date de vérification** | 20 juillet 2026 |
| **Soutenance** | 31 juillet 2026 |

## Contexte du projet

TomatoScan est une application web qui met un service d'intelligence artificielle à la
disposition d'un utilisateur métier — un agriculteur ou un technicien agronome — pour
diagnostiquer une maladie sur une feuille de tomate à partir d'une simple photo. Le cœur
IA est un réseau **MobileNetV2** entraîné par transfer learning avec **PyTorch** (base
ImageNet gelée, seul le classifieur final réentraîné), qui classe une image en **10 classes**
du jeu PlantVillage (neuf maladies plus la classe « feuille saine »). Le choix de MobileNetV2
est un choix de conception à part entière : c'est un réseau léger, capable d'inférer en CPU
sur un VPS sans GPU, ce qui conditionne toute l'architecture de déploiement décrite plus bas.

Là où l'épreuve E3 traitait le versant « science des données » du projet (exposer le modèle,
le monitorer, le tester, le livrer — C9 à C13), **E4 traite le versant « ingénierie
applicative et conduite de projet »** : analyser le besoin et le spécifier (C14), concevoir
le cadre technique et sa preuve de concept (C15), coordonner la réalisation en mode agile
(C16), développer les composants et les interfaces (C17), automatiser les tests par
intégration continue (C18) et industrialiser la livraison continue (C19). L'architecture
applicative se décompose en quatre briques cohérentes avec ce périmètre :

- un **frontend Streamlit** multi-pages, l'interface réellement manipulée par l'utilisateur ;
- une **API FastAPI** qui expose l'inférence du modèle et authentifie les appels par JWT ;
- une base **PostgreSQL** (accès asynchrone, migrations Alembic) qui persiste comptes et
  prédictions ;
- une chaîne d'**observabilité Prometheus / Grafana** doublée d'une journalisation `loguru`.

Deux rôles applicatifs structurent les parcours : `agriculteur` (analyse d'images, historique
personnel) et `admin` (gestion des comptes, tableau de bord, rapports du modèle). Le projet
est un **projet individuel de diplôme** : ce point n'est pas anecdotique, il conditionne la
lecture de C16 (les rôles agiles Product Owner / Scrum Master / Développeur sont assumés par
une seule personne) et il est traité honnêtement plutôt que masqué derrière une organisation
fictive.

## Méthode de vérification

Chaque critère de ce rapport s'appuie sur une **preuve datée** : un fichier référencé par
`chemin:ligne`, une commande réellement exécutée, ou un artefact réellement présent dans le
dépôt. Aucun chiffre n'est reporté de mémoire. Les commandes suivantes ont été rejouées lors
de la rédaction :

```
uv run pytest tests/ --cov=src/tomatoscan/api --cov-fail-under=75
     → 112 passed ; couverture API 79,28 % ("Required test coverage of 75% reached")
uv run pytest tests/test_model/ --cov=src/tomatoscan/model --cov-fail-under=80
     → 25 passed ; couverture modèle 85,07 %
.venv/bin/python -m pytest tests/test_frontend/ --cov=src/tomatoscan/front
     → 41 passed ; couverture frontend 84 %
uv run ruff check src/ tests/                        → All checks passed!
uv run ruff format --check                           → 69 files already formatted
uv run pip-audit                                     → No known vulnerabilities found
git remote -v                                        → origin https://github.com/sulivan-moreau/TomatoScan.git
git log --merges --oneline | wc -l                   → 41 (dont 1 seul sur main)
```

Les résultats d'exécution de la chaîne CI/CD ont par ailleurs été recoupés avec l'API GitHub
Actions : le workflow `ci-app.yml` porte l'identifiant `305436964`, état `active`, `83` runs
au total ; le run `29764535749` (SHA `bc0bb800`, push sur `develop`) est `success` sur ses
deux jobs.

**Légende des statuts** : ✅ prouvé · ⚠️ fragile (défendable à l'oral, à consolider) ·
❌ manquant · ⬜ non vérifiable depuis cet environnement.

### Avertissement — sources de conception obsolètes remplacées

Le dépôt contient trois PDF de conception historiques (`docs/specs_fonctionnelles.pdf`,
`docs/specs_techniques.pdf`, `docs/modelisation.pdf`, issus des issues #26 / #27) qui ont
**divergé du code réel**. Ils mentionnent encore TensorFlow/`.keras`, MLflow, une entité de
base `MODEL` qui n'existe pas, et des colonnes `disease_class` / `confidence_score` qui
n'existent pas non plus. La **source de vérité de la modélisation est désormais
`docs/modelisation.md`** (Markdown + diagrammes Mermaid, éditable et versionné), qui reflète
exactement `src/tomatoscan/database/modeles.py`. Ce rapport ne cite jamais un PDF obsolète
comme preuve unique : quand un PDF est mobilisé (user stories, wireframes), c'est pour une
partie vérifiée cohérente avec le code, et la réserve est signalée. La régénération des PDF
depuis `modelisation.md` figure dans la liste « à faire avant la soutenance ».

---

## C14 — Analyser le besoin d'un commanditaire intégrant un service d'IA

> *Rédiger les spécifications fonctionnelles et modéliser le besoin, dans le respect des
> standards d'utilisabilité et d'accessibilité.*

### Vue d'ensemble

Le besoin de TomatoScan a été spécifié à deux niveaux complémentaires. D'un côté, une
**modélisation formelle** (données + parcours utilisateurs + flux) versionnée dans
`docs/modelisation.md`, qui fait foi. De l'autre, des **spécifications fonctionnelles**
rédigées sous forme de *user stories* dans `docs/specs_fonctionnelles.pdf`, où chaque story
porte son contexte, ses scénarios et ses critères de validation — **critères d'accessibilité
WCAG AA compris, intégrés au niveau de chaque story**. C'est le point le plus solide du bloc :
l'accessibilité n'est pas reléguée à une annexe, elle est un critère d'acceptation comme un
autre.

### Modélisation des données — un formalisme entités-relations exact

`docs/modelisation.md` §1 (lignes 35-56) contient un diagramme Mermaid `erDiagram` qui
reflète **exactement** les deux tables déclarées dans `src/tomatoscan/database/modeles.py` :

| Entité | Colonnes réelles (source de vérité) | Cardinalité |
|---|---|---|
| `users` | `id` (Uuid, PK, défaut `uuid4`), `username` (UK), `email` (UK), `hashed_password` (bcrypt), `role` (défaut `agriculteur`), `created_at` | `users ‖--o{ predictions` |
| `predictions` | `id` (Integer, PK auto-incrémenté), `user_id` (Uuid, FK → `users.id`), `nom_fichier`, `classe_predite`, `confiance` (Float 0.0-1.0), `created_at` | chaque prédiction appartient à 1 `users` |

Le formalisme entités-relations est respecté (clés primaires, clé étrangère, cardinalités
`(0,n)`/`(1,1)`), et surtout le **contenu est vrai** : les noms de colonnes du diagramme sont
les noms réels du code (`classe_predite`, `confiance`), pas les colonnes fantômes des vieux
PDF. Un point de conception important est explicité par une note (lignes 62-71) : **le modèle
d'IA n'est pas une table**. C'est un checkpoint PyTorch `.pt` chargé une seule fois en mémoire
au démarrage de l'API (singleton `initialiser_modele()` dans `model_service.py`) ; il n'y a
donc pas d'entité `MODEL` en base — le MCD du vieux PDF est faux sur ce point, `modelisation.md`
le corrige explicitement.

### Modélisation des parcours utilisateurs

`docs/modelisation.md` §3 (lignes 139-168) formalise deux parcours en `flowchart` Mermaid,
cohérents avec les pages réelles de `src/tomatoscan/front/pages/` :

- **Agriculteur** : `accueil` → `login` (POST `/auth/token`) → session JWT → `predict` (import
  photo `jpg/jpeg/png ≤ 5 Mo`, compression client, POST `/predict`, diagnostic
  `classe_predite + confiance`) → persistance en base → `history` (GET `/predictions/history`).
- **Administrateur** : `login` → `dashboard` (GET `/reports`, GET `/users`, GET
  `/predictions/history` en vue globale, lien Grafana) → `creer_membre` (création d'un compte
  agriculteur).

À ces schémas fonctionnels s'ajoutent, dans `docs/modelisation.pdf`, **4 wireframes
basse-fidélité** (login, predict, historique, dashboard). Le formalisme « schéma fonctionnel »
de `modelisation.md` suffit à lui seul à couvrir le critère ; les wireframes le complètent.

**[CAPTURE À INSÉRER — C14 : les 4 wireframes basse-fidélité (login / predict / historique /
dashboard) juxtaposés aux 4 écrans Streamlit réels correspondants, pour montrer la
correspondance maquette → interface.]**

### Spécifications fonctionnelles — contexte, scénarios, critères de validation

`docs/specs_fonctionnelles.pdf` (pages 4-8) contient **5 user stories** au format « EN TANT
QUE… JE VEUX… AFIN DE… », chacune structurée en trois blocs explicites :

| # | User story | Contexte / Scénarios | Critères de validation |
|---|---|---|---|
| US01 | Upload + prédiction | Cas SUCCÈS / FORMAT invalide / TAILLE > 5 Mo | Diagnostic affiché, image non stockée |
| US02 | Connexion | Cas IDENTIFIANTS valides / invalides / SESSION | JWT émis, rôle chargé depuis `/me` |
| US03 | Historique | Consultation filtrée par rôle | Tableau date/fichier/maladie/confiance |
| US04 | Dashboard admin | Rapports modèle, gestion comptes | Accès réservé `admin` |
| US05 | Création de compte | Création par l'admin, rôle imposé | Compte `agriculteur` créé |

La page 8 récapitule des critères d'acceptation globaux (séparation des rôles, RGPD — aucune
image conservée). Chaque story couvre donc bien contexte + scénarios + critères, comme exigé.

### Accessibilité intégrée aux critères et fondée sur un standard

C'est le point remarquable de C14 : chaque user story porte, **au sein même du récit**, une
colonne « ACCESSIBILITÉ » marquée `AA`, juxtaposée aux critères de validation fonctionnels.
Exemples relevés sur US01 : « le bouton d'upload a un label explicite (AA) », « les messages
d'erreur ont un contraste suffisant ratio 4.5:1 (AA) », « la zone d'upload est utilisable au
clavier (AA) », « les résultats sont lisibles par un lecteur d'écran (AA) ». Le standard est
**nommé explicitement** : « WCAG AA » sur chaque story du PDF, et « WCAG 2.1 niveau AA » dans
`docs/modelisation.md` §4 (ligne 174), avec les ratios de contraste réellement calculés par la
formule de luminance relative WCAG (blanc sur `#2d6a4f` = 6.39:1, blanc sur `#c1121f` =
6.22:1, tous deux ≥ 4.5:1). L'objectif d'accessibilité n'est donc pas une intention vague mais
un critère mesurable et vérifié dans le code.

### Tableau des critères — C14

| Critère | Statut | Preuve |
|---|---|---|
| La modélisation des données respecte un formalisme (Merise, E-R…) | ✅ | `docs/modelisation.md:35-56` — `erDiagram` Mermaid E-R (`users ‖--o{ predictions`), correspondance exacte avec `src/tomatoscan/database/modeles.py` ; note :62-71 explique l'absence d'entité `MODEL` (checkpoint `.pt` en mémoire, pas une table) |
| La modélisation des parcours utilisateurs respecte un formalisme | ✅ | `docs/modelisation.md:139-168` — 2 `flowchart` (parcours agriculteur / admin) cohérents avec `front/pages/` ; 4 wireframes dans `docs/modelisation.pdf` |
| Chaque spécification fonctionnelle couvre contexte / scénarios / critères de validation | ✅ | `docs/specs_fonctionnelles.pdf` p.4-8 — 5 user stories, chacune en 3 blocs CONTEXTE / SCÉNARIOS / CRITÈRES ; récap. p.8 (rôles, RGPD) |
| Les objectifs d'accessibilité sont intégrés aux critères d'acceptation des user stories | ✅ | `docs/specs_fonctionnelles.pdf` — colonne « ACCESSIBILITÉ (AA) » par story (label upload, contraste 4.5:1, clavier, lecteur d'écran), pas une section séparée |
| Les objectifs d'accessibilité s'appuient sur un standard (WCAG, RGAA…) | ✅ | « WCAG AA » sur chaque story ; `docs/modelisation.md:174` nomme « WCAG 2.1 niveau AA » et cite les ratios 6.39:1 / 6.22:1 recalculés |

**Verdict C14 : ✅ acquise (5/5 prouvés).** Réserve mineure d'homogénéité : le PDF écrit
« WCAG AA », `modelisation.md` précise « WCAG 2.1 AA » — à uniformiser sans enjeu de fond.

---

## C15 — Concevoir le cadre technique d'une application intégrant un service d'IA

> *Architecture, dépendances, environnement d'exécution, éco-responsabilité, diagramme de flux
> de données, preuve de concept en préproduction et avis GO/NO-GO.*

### Vue d'ensemble

Le cadre technique est documenté dans `docs/architecture.md` (installation, architecture en
couches, dépendances par domaine) et sa preuve de concept est conclue dans
`docs/poc_conclusion.md` par un avis **GO (avec réserves)** appuyé sur des mesures réelles. Le
point de fragilité unique et assumé de C15 est le critère « POC accessible et fonctionnelle en
préproduction » : la **plomberie de déploiement fonctionne désormais** (voir plus bas), mais la
preuve *live* (URL préprod joignable, conteneurs Coolify `healthy`) n'est pas encore capturée
dans le dépôt, et `poc_conclusion.md` n'a pas encore été mis à jour pour refléter le
rétablissement. C'est le seul « ❌ » du bloc E4.

### Spécifications techniques — architecture, dépendances, environnement

`docs/architecture.md` couvre l'ensemble du cadre technique :

| Domaine | Contenu (architecture.md) | Dépendances clés |
|---|---|---|
| Environnement de dev (l.17-33) | Python 3.11-3.13, `uv`, Docker, `just` | — |
| Architecture applicative (l.48-108) | Diagramme + description accessible, tableau des couches, flux d'authentification, `lifespan` | — |
| API | FastAPI, JWT, SQLAlchemy async, Alembic | `fastapi`, `asyncpg`, `alembic` |
| Modèle | MobileNetV2 chargé en mémoire | `torch`, `torchvision` (CPU) |
| Frontend | Streamlit multi-pages | `streamlit`, `requests`, `pandas` |
| Observabilité | Prometheus / Grafana / loguru | `prometheus-client`, `loguru` |
| Dev | Tests, lint | `pytest`, `ruff`, `aiosqlite` |

Le tout est cohérent avec `docker-compose.yml` (services `api`, `front`, `postgres`,
`prometheus`, `grafana`). **Résidu à nettoyer** : `architecture.md:127` mentionne encore
`tensorflow-macos/metal` alors que le stack est PyTorch — trace d'une itération antérieure,
sans effet sur le code, à supprimer pour cohérence.

### Diagramme de flux de données (livrable obligatoire)

Le critère « flux représentés par un diagramme de flux de données » est **obligatoire** au
référentiel et il est couvert par un diagramme **éditable et versionné** dans
`docs/modelisation.md` §2 (lignes 82-118) : navigateur → Streamlit (upload + compression) →
FastAPI (auth JWT, POST `/predict`, GET `history`/`reports`/`users`) → MobileNetV2 (tenseur
224×224 → `classe_predite` + `confiance`) → PostgreSQL (`INSERT predictions`), avec une branche
monitoring API → Prometheus → Grafana. Les libellés d'arêtes utilisent les vrais noms de
colonnes. Un second diagramme (ASCII + description textuelle accessible) figure dans
`architecture.md:50-71`.

### Éco-responsabilité des choix techniques

Les choix éco-responsables sont **réels et traçables dans le code**, pas déclaratifs
(`poc_conclusion.md` §4, lignes 78-96) :

- **Torch CPU-only** installé via l'index `whl/cpu` dans `Dockerfile.api` → évite ~2 Go de
  wheels CUDA inutiles (le modèle infère en CPU) ;
- **Images Docker légères** : base `python:3.11-slim`, `uv sync --no-dev` ;
- **Aucun stockage d'image** : seul `nom_fichier` est persisté, jamais l'image (gain de
  stockage + conformité RGPD) ;
- **Compression client avant envoi** : `_compresser_image` (front) borne à 1024 px, JPEG 85 ;
- **Cache** des appels du tableau de bord (`@st.cache_data`) évitant les requêtes réseau
  redondantes.

Côté infrastructure, `cd_application.md:17-18` documente **Coolify** comme PaaS auto-hébergé sur
VPS OVH (open source plutôt qu'un SaaS propriétaire), et `architecture.md:137-141` invoque la
certification ISO 50001 des datacenters OVH. **Réserve honnête** : l'assertion « OVH ISO 50001 »
reste documentaire non sourcée dans le dépôt, et la justification éco d'infrastructure renvoie
encore à un PDF signalé obsolète — à rapatrier dans un support à jour.

### Preuve de concept en préproduction — le point fragile assumé

C'est le critère non tenu. Il faut être précis, car la situation a **évolué favorablement**
mais n'est pas encore prouvable depuis le dépôt.

Ce qui fonctionne désormais (commits de correction réellement présents) :

- `e42fce8` : l'API attend PostgreSQL au démarrage via `depends_on: condition: service_healthy`
  (`docker-compose.yml:35-37`) — corrige un ordre de démarrage qui faisait échouer l'API ;
- `1f201a6` / `2e6f374` : les artefacts d'évaluation sont embarqués dans l'image API
  (`Dockerfile.api:41`) — l'API ne dépend plus de fichiers absents du conteneur ;
- le front joint l'API par le nom de service Docker via `TOMATOSCAN_API_URL: http://api:8000`
  (`docker-compose.yml:60`).

Ces correctifs rendent un **déploiement fonctionnel plausible** et lèvent les causes racines des
échecs passés. **Mais** `docs/poc_conclusion.md` (§1 ligne 22, §5 lignes 102-114) affirme
toujours « préproduction non joignable au dernier constat » / « production répondant 503 » :
le document se contredit avec l'idée d'une préprod rétablie. Et surtout, **aucune preuve live**
(URL publique, capture Coolify, `curl -I .../health` en 200) n'existe dans le dépôt. Le critère
reste donc **❌ non prouvé depuis le dépôt** tant que ces deux actions ne sont pas faites.

**[CAPTURE À INSÉRER — C15 : tableau de bord Coolify montrant les conteneurs `api` / `front` /
`postgres` en état `healthy` sur le VPS OVH, + l'URL publique de préproduction, + la sortie de
`curl -I https://<domaine-preprod>/health` renvoyant `HTTP/2 200`.]**

### Conclusion de la POC — avis GO/NO-GO explicite

`docs/poc_conclusion.md` §7 (lignes 154-172) rend un avis **explicite et argumenté** : « GO
(avec réserves) ». L'argumentaire s'appuie sur des mesures réelles vérifiables (accuracy de
test **0,9355** sur **10 classes** / **2 402 images**, source
`docs/rapport_evaluation_20260624_163236.json`) et sur une feuille de route de réserves
priorisées : (1) rétablir et vérifier la préprod, (2) mesurer la latence via
`tomatoscan_prediction_duration_seconds`, (3) améliorer le rappel de `Tomato_Early_blight`
(≈ 0,73) et valider la généralisation hors PlantVillage. L'avis est précis, décisionnel et
honnête sur ses limites — exactement ce qu'attend le critère.

### Tableau des critères — C15

| Critère | Statut | Preuve |
|---|---|---|
| Les specs techniques couvrent architecture, dépendances, environnement d'exécution | ✅ | `docs/architecture.md:17-125` (env dev, couches, dépendances par domaine), cohérent `docker-compose.yml` ; résidu TensorFlow l.127 à nettoyer |
| Les services/prestataires éco-responsables sont favorisés | ✅ | `poc_conclusion.md:78-96` (torch CPU, slim, pas de stockage d'image, cache) ; Coolify PaaS auto-hébergé OVH (`cd_application.md:17-18`) — assertion ISO 50001 non sourcée (réserve) |
| Les flux de données sont représentés par un diagramme (OBLIGATOIRE) | ✅ | `docs/modelisation.md:82-118` — `flowchart` Mermaid éditable et versionné (front → API → MobileNetV2 → PostgreSQL + monitoring) ; second diagramme `architecture.md:50-71` |
| La POC est accessible et fonctionnelle en préproduction | ❌ | Correctifs de déploiement présents (`e42fce8`, `1f201a6`, `2e6f374`) → déploiement plausible, MAIS aucune preuve live dans le dépôt et `poc_conclusion.md:22,102-114` affirme encore la préprod non joignable — **capture Coolify + URL + `curl /health` à fournir** |
| La conclusion de la POC donne un avis GO/NO-GO précis | ✅ | `poc_conclusion.md:154-172` — avis « GO (avec réserves) » argumenté (accuracy 0,9355 sourcée) + feuille de route priorisée |

**Verdict C15 : ⚠️ à risque (4/5 prouvés, 1 manquant).** Le seul manque est la démonstration
*live* de la préproduction. La conception, l'éco-responsabilité, le diagramme de flux et l'avis
GO/NO-GO sont solides. La crédibilité de l'avis GO se renforcera dès que la réserve n°1
(préprod) sera levée par la capture ci-dessus.

---

## C16 — Coordonner la réalisation technique en conduite agile et contexte MLOps

> *S'intégrer dans une conduite agile, faciliter les temps de collaboration.*

### Vue d'ensemble

C16 est la compétence la plus fragile du bloc — c'est cohérent avec sa nature (« soft skills »
de gestion de projet, difficiles à prouver *a posteriori* pour un projet solo). Le **cycle de
travail agile est solidement prouvé par Git** (issue → branche → PR → merge, cadence
hebdomadaire), et le **backlog** ainsi qu'un **substitut de burndown** sont versionnés et
reconstruits depuis l'historique réel. En revanche, les **rituels** (points de suivi, rétros)
et le **tableau kanban GitHub Projects** ne sont pas encore matérialisés par des entrées datées
ou des captures : les quatre critères sont donc en ⚠️ « fragile ».

### Le cycle agile prouvé par l'historique Git

Le flux de développement est réel et vérifiable, pas déclaratif :

| Élément agile | Preuve Git / fichier |
|---|---|
| Cycle issue → branche → PR → merge | `git log --merges --oneline` → **41 merges** (dont **1 seul** sur `main`) |
| Conventions de nommage | branches `feature/*` et `fix/*` (`git branch -a`) |
| Traçabilité des issues | commits référençant #16, #15, #10, #37, #39, #32, #12, #13, #11… (`git log --all --grep="#[0-9]"`) |
| Template d'issue standardisé | `.github/ISSUE_TEMPLATE/issue-standard.md:1-24` (Objectif / Tâches / Branche / Critères) |
| Rôles agiles | `docs/agile.md:39-46` — PO / SM / Dev assumés par le candidat unique (projet individuel) |
| Répartition dans le temps | cadence hebdomadaire W26 → W30 |

Ce cycle démontre l'application réelle d'une méthode agile légère (« Kanban-flow » adapté à un
solo), avec une discipline de branches, de PR et de traçabilité vers les issues.

### Outils de pilotage — backlog et cadence de livraison

Deux artefacts de pilotage sont versionnés et donc consultables par toute partie prenante :

- **Backlog** (`docs/backlog.md`) : 5 user stories métier + tâches techniques + correctifs,
  avec traçabilité issue ↔ PR ↔ branche. Il est honnête (mention explicite « issue non
  tracée » quand aucun numéro n'existe), ce qui vaut mieux qu'un backlog reconstruit
  artificiellement.
- **Substitut de burndown** (`docs/pr_cadence.md`) : cadence de PR par semaine ISO (tableau +
  graphiques Mermaid en barres et burnup cumulé), dérivée de commandes Git reproductibles :
  W26 = 3, W27 = 20, W29 = 12 PR. **Actualisation nécessaire** : la doc annonce « 35 PR » alors
  que l'historique en compte désormais **41** (semaine W30 ajoutée le 2026-07-20 : PR #97 / #98
  / #99) — léger décalage documentaire à corriger.

Il n'y a **pas de burndown Scrum formel** (aucun *story point* dans le dépôt) : ce choix est
assumé honnêtement dans `docs/agile.md:139-152` plutôt que fabriqué. Le **tableau kanban
(GitHub Projects)** est affirmé (`agile.md:117-121`) mais **non capturé** — le fichier porte le
marqueur « À insérer par le candidat » et `which gh` retourne « command not found » dans
l'environnement de vérification, donc l'usage continu du board n'est pas prouvable ici.

**[CAPTURE À INSÉRER — C16 : le tableau kanban GitHub Projects du dépôt, montrant au moins les
colonnes To do / In progress / Done avec des cartes réelles, à au moins deux dates distinctes
du projet pour attester d'un usage continu (marqueurs déjà en place dans `docs/agile.md:126-132`).]**

### Rituels et partage aux parties prenantes

Les **modalités** des rituels sont formalisées (`docs/journal_rituels.md:55-59` : tableau
Rituel / Objectif / Fréquence cible / Format / Partage, cohérent avec un projet individuel :
point de suivi formateur, revue perso d'avancement, rétrospective perso). En revanche, la
**tenue effective** de ces rituels n'est pas prouvée : le journal de bord
(`journal_rituels.md:69-74`) ne contient que des lignes `[EXEMPLE]` et `(à compléter)`, sans
aucune entrée réellement datée. Aucune trace de partage à une partie prenante (le formateur
Simplon) n'est versionnée. C'est le point à consolider en priorité pour C16 : consigner de
vrais points de suivi datés.

### Accessibilité des éléments de pilotage

Le dépôt distant est **public et accessible** (`git remote -v` → dépôt GitHub public), et tous
les artefacts de pilotage sont versionnés donc consultables (`agile.md`, `backlog.md`,
`pr_cadence.md`, `journal_rituels.md`). Chaque document porte une note d'accessibilité
(Markdown structuré H1→H3, tableaux à en-têtes, information jamais portée uniquement par la
couleur). La limite est la continuité : les documents de coordination ont été fusionnés
tardivement (PR #95 `feature/docs`, 2026-07-19), et la preuve d'un usage *continu* du board
repose sur les captures encore manquantes.

### Tableau des critères — C16

| Critère | Statut | Preuve |
|---|---|---|
| Cycles, étapes, rôles, rituels et outils de la méthode agile respectés tout au long du projet | ⚠️ | Cycle issue→branche→PR→merge **prouvé** (41 merges, branches `feature/*`/`fix/*`, refs d'issues, template `.github/ISSUE_TEMPLATE/`) ; rôles `agile.md:39-46` ; **rituels non prouvés** (`journal_rituels.md:69-74` = `[EXEMPLE]`) et kanban non capturé |
| Outils de pilotage (kanban, burndown, backlog) disponibles | ⚠️ | Backlog réel `docs/backlog.md` + cadence PR `docs/pr_cadence.md` (W26=3, W27=20, W29=12) versionnés ; kanban GitHub Projects **non capturé** ; pas de burndown Scrum formel (assumé) ; chiffre « 35 PR » à passer à 41 |
| Objectifs et modalités des rituels partagés aux parties prenantes | ⚠️ | Modalités formalisées `journal_rituels.md:55-59` ; **partage effectif non prouvé** (journal vide de vraies entrées) |
| Éléments de pilotage accessibles à toutes les parties, tout au long du projet | ⚠️ | Dépôt distant public + docs de pilotage versionnées et accessibles ; continuité non démontrée (docs fusionnées tardivement PR #95, captures kanban manquantes) |

**Verdict C16 : ⚠️ à risque (0/4 pleinement, 4/4 fragiles).** Le socle « process Git » est
excellent et prouvé ; ce qui manque est le matériel de démonstration humain (captures kanban,
journal de rituels réellement tenu). Aucune organisation fictive n'a été inventée : les manques
sont documentés honnêtement.

---

## C17 — Développer les composants techniques et les interfaces

> *Respecter les spécifications fonctionnelles et techniques, les normes d'accessibilité, de
> sécurité et de gestion des données.*

### Vue d'ensemble

C17 est le cœur « développement » du bloc et il est largement acquis : composants métier
fonctionnels, gestion des droits à double barrière, flux de données conformes, protections
OWASP côté interface, accessibilité prise en compte dans le code, et **41 tests frontend
verts** couvrant les composants et les accès. Deux points restent en ⚠️ : la fidélité aux
maquettes (écarts réels à justifier + wireframes vivant seulement dans le PDF) et une des trois
mesures d'éco-conception probablement inerte en conteneur.

### Environnement de développement du front

Le front est volontairement découplé du stack ML lourd : `src/tomatoscan/front/requirements.txt`
ne déclare que `streamlit`, `requests`, `pandas`, `python-dotenv` (pas de `torch`), et son image
`Dockerfile.front` part de `python:3.11-slim` avec `CMD streamlit run`. C'est un choix
d'éco-conception et de rapidité de build cohérent avec `architecture.md`.

### Interfaces vs maquettes — écarts réels à justifier

Les écrans implémentés correspondent **structurellement** aux 4 wireframes de
`modelisation.pdf` (login, predict avec zone d'upload + résultat + confiance, dashboard avec
historique global + création de compte). Mais la vérification a relevé de **vrais écarts** — et
les signaler honnêtement vaut mieux que prétendre à une correspondance parfaite :

| Maquette | Écran réel | Écart |
|---|---|---|
| Login : « CHAMP EMAIL » | `login.py:32` demande « Nom d'utilisateur » | champ email → username |
| Historique : « FILTRE PAR MALADIE » (dropdown) | `history.py` : pas de filtre | fonction absente |

De plus, les wireframes ne vivent **que** dans `modelisation.pdf` (partiellement obsolète pour
son MCD) ; `modelisation.md` — qui fait foi — n'en contient aucun (`grep wireframe|maquette` = 0)
et `docs/wireframes/` ne contient qu'un README pointant vers le PDF. Ces écarts sont mineurs et
défendables (un login par username est plus sûr qu'un login par email exposé), mais ils doivent
être **assumés et justifiés**, et les wireframes rapatriés dans la source éditable.

**[CAPTURE À INSÉRER — C17 : les écrans Streamlit réels (login, predict avec résultat +
confiance, historique, dashboard) en regard des wireframes correspondants, avec annotation des
deux écarts assumés (email→username, absence de filtre historique).]**

### Comportements des composants — validation et navigation

Le routing est conditionnel au rôle (`app.py:169-217` : `st.navigation` selon token et rôle,
pages masquées `position="hidden"` hors connexion). La validation des formulaires est réelle :
champs vides refusés (`login.py:44-47`, `creer_membre.py:56-57`), `file_uploader` restreint à
`jpg/jpeg/png` et bouton « Analyser » désactivé tant qu'aucun fichier n'est chargé
(`predict.py:157-180`), spinners d'attente, et **confirmation à deux temps** pour la suppression
d'un compte (`dashboard.py:247-269`). Le test `test_navigation_role.py` exécute le vrai `app.py`
via `AppTest` et valide la navigation par rôle — ce n'est pas un test de façade.

### Composants métier et flux de données

Chaque page assure sa fonction métier de bout en bout : `predict.py` (upload →
`_compresser_image` → `api_client.predict` POST `/predict` → bandeau diagnostic + recommandation
+ confiance), `history.py` (GET `/predictions/history` → tableau stylé), `dashboard.py`
(rapports modèle, liste des utilisateurs, suppression), `creer_membre.py` (création de compte).
Le client `api_client.py` couvre l'ensemble des opérations (login, me, predict, history,
reports, users). Le flux réseau est paramétré proprement : `api_client.py:47`
`API_URL = os.getenv("TOMATOSCAN_API_URL", "http://localhost:8000")` — en Docker, le front joint
l'API par le service `http://api:8000`. Appels multipart pour `predict`, Bearer JWT, `/health`
pour l'état API.

### Gestion des droits d'accès — double barrière

L'accès admin est protégé à **deux niveaux**, ce que le référentiel demande explicitement (« y
compris côté interface ») :

1. **Navigation** : `app.py:190-204` n'ajoute les pages « Tableau de bord » et « Créer un
   membre » que si `role == "admin"` ;
2. **Garde-fou de page** : `dashboard.py:78-80` et `creer_membre.py:33-35` affichent
   `st.error("Accès réservé aux administrateurs.")` puis `st.stop()`.

Le rôle est figé au login depuis `/me` (`login.py:58`), **jamais dérivé côté client**, et
re-vérifié à chaque re-run (`app.py:161-164`). Les tests
`test_agriculteur_est_bloque_sur_les_pages_admin` et
`test_changer_le_role_dans_le_token_change_immediatement_l_acces_affiche`
(`test_navigation_role.py:107-144`) prouvent le blocage et la réactivité au changement de rôle.

### OWASP côté interface

Les préconisations OWASP pertinentes côté front sont implémentées. **Anti-XSS** :
`api_client.py:84` applique `html.escape()` (import `html` l.24) au libellé de repli avant
injection dans un bloc `st.markdown(unsafe_allow_html=True)` ; les données dynamiques des blocs
`unsafe_allow_html` sont soit échappées (`maladie_fr` via `fr_label`, `predict.py:251`), soit
numériques (pourcentage). Les valeurs contrôlables par l'utilisateur (`username`) sont rendues
via `st.caption` / `st.write` / `st.dataframe` (échappement Streamlit natif). **Session** : JWT
validé à chaque re-run (`app.py:149`), purge sur token invalide, renouvellement silencieux. La
démarche est documentée dans `src/tomatoscan/api/core/owasp.md`.

### Éco-conception — deux mesures solides, une inerte

Deux mesures sont robustes et actives partout : (1) la **compression/redimensionnement image
côté client avant envoi réseau** (`predict.py:46-91` `_compresser_image`, borne 1024 px, JPEG
qualité 85, `optimize=True`, appelée `predict.py:202`) ; (2) la **mise en cache** des appels API
(`dashboard.py:37-57` `@st.cache_data(ttl=60)` + invalidation explicite après suppression
`dashboard.py:60-64,261`). La troisième mesure est **fragile** : `.streamlit/config.toml`
(`maxUploadSize=5`) est placé dans `src/tomatoscan/front/.streamlit/`, or Streamlit lit son
config projet depuis `$CWD/.streamlit`. En Docker, `WORKDIR=/app` et la commande lance
`src/tomatoscan/front/app.py` (`Dockerfile.front:16,39`) : le fichier est en
`/app/src/tomatoscan/front/.streamlit` et **ne sera pas chargé** depuis `CWD=/app` — le
`maxUploadSize` (et le thème) sont donc probablement inertes en préprod. À corriger en déplaçant
le fichier à la racine du CWD ou en passant `--server.maxUploadSize=5` dans la `CMD`.

### Tests des composants et des accès

`.venv/bin/python -m pytest tests/test_frontend/ --cov=src/tomatoscan/front` → **41 passed**,
couverture **84 %** au total. Détail (term-missing) :

| Module | Couverture |
|---|---|
| `session.py` | 100 % |
| `history.py` | 95 % |
| `login.py` | 93 % |
| `accueil.py` | 93 % |
| `predict.py` | 89 % |
| `app.py` | 83 % |
| `dashboard.py` | 83 % |
| `api_client.py` | 78 % |
| `creer_membre.py` | 62 % |

La gestion des accès est spécifiquement couverte par `test_navigation_role.py` (admin /
agriculteur / changement de rôle) via `AppTest` sur le vrai `app.py`. **Nuances honnêtes** :
`creer_membre.py` reste à 62 % (lignes 25-31, 56-66 non testées) et `dashboard.py` mesuré à
83 % (et non 92 % comme parfois annoncé) — deux points de consolidation, sans remettre en cause
le fond.

### Accessibilité dans le développement

L'accessibilité est prise en compte **dans le code**, pas seulement dans la doc : `lang="fr"`
forcé sur une app francophone servie en `lang="en"` par Streamlit (`app.py:89-114`
`forcer_langue_francaise` par injection JS), contrastes WCAG AA calculés (`predict.py:11-12`),
texte alternatif de l'aperçu image via caption (`predict.py:167-172`), SVG décoratifs
`aria-hidden="true"` (`predict.py:242,260`), label explicite sur le `file_uploader`
(`predict.py:158`). Limite assumée : le hack JS `forcer_langue_francaise` est sans effet sous
`AppTest` (qui n'exécute pas le JS) mais efficace en navigateur réel.

### Documentation technique

`docs/architecture.md` couvre l'installation de l'environnement de dev (:17), l'architecture
applicative et les modules (:80), les dépendances par domaine (:110-125) et l'exécution des
tests avec couverture (:168 `uv run pytest tests/ -v --cov=src/tomatoscan …`). La doc est en
Markdown structuré avec table des matières — format navigable au lecteur d'écran. À nettoyer :
la référence TensorFlow résiduelle (`architecture.md:127`), déjà signalée en C15.

### Tableau des critères — C17

| Critère | Statut | Preuve |
|---|---|---|
| L'environnement de dev respecte les specs techniques | ✅ | `front/requirements.txt` (streamlit/requests/pandas) découplé du ML lourd ; `Dockerfile.front:16,39` (slim, `streamlit run`) ; `architecture.md:17,110,125` |
| Les interfaces sont intégrées et respectent les maquettes | ⚠️ | Correspondance structurelle wireframes `modelisation.pdf` p4 ↔ écrans ; **écarts** email→username (`login.py:32`) et filtre historique absent ; wireframes seulement dans le PDF, à rapatrier dans `modelisation.md` |
| Les comportements des composants (validation, navigation) respectent les specs | ✅ | `app.py:169-217` (routing par rôle) ; validations `login.py:44-47`, `predict.py:157-180` ; confirmation 2 temps `dashboard.py:247-269` ; `test_navigation_role.py` sur le vrai `app.py` |
| Les composants métier fonctionnent comme prévu | ✅ | `predict.py`/`history.py`/`dashboard.py`/`creer_membre.py` + `api_client.py` ; **41 tests frontend verts** |
| La gestion des droits d'accès respecte les specs (y c. interface) | ✅ | Double barrière `app.py:190-204` + `dashboard.py:78-80`/`creer_membre.py:33-35` ; rôle depuis `/me`, re-vérifié `app.py:161-164` ; tests `test_navigation_role.py:107-144` |
| Les flux de données sont intégrés dans le respect des specs | ✅ | `api_client.py:47` `TOMATOSCAN_API_URL` → `http://api:8000` en Docker ; multipart, Bearer JWT, `/health` ; diagramme `modelisation.pdf` p5 |
| Éco-conception (Green IT) | ⚠️ | Compression client `predict.py:46-91` et cache `dashboard.py:37-57` **solides** ; `.streamlit/config.toml` probablement **non chargé** en Docker (CWD≠dossier config) — à corriger |
| Top 10 OWASP côté interface | ✅ | `html.escape()` `api_client.py:84` avant `unsafe_allow_html` ; `username` via échappement Streamlit natif ; JWT re-validé `app.py:149` ; `core/owasp.md` |
| Tests couvrent composants métier et gestion des accès | ✅ | 41 passed, couverture front 84 % ; accès via `test_navigation_role.py` — nuances : `creer_membre.py` 62 %, `dashboard.py` 83 % |
| Sources versionnées, dépôt Git distant | ✅ | `git remote -v` → dépôt GitHub ; front + tests versionnés |
| Enjeux d'accessibilité pris en compte au développement | ✅ | `lang="fr"` forcé `app.py:89-114` ; contrastes AA `predict.py:11-12` ; alt image, `aria-hidden`, label `file_uploader` |
| La doc technique couvre install / architecture / dépendances / tests | ✅ | `docs/architecture.md:17,80,110-125,168` — nettoyer résidu TensorFlow l.127 |
| La doc respecte les recommandations d'accessibilité | ✅ | Markdown structuré + TOC (`architecture.md:10`) ; PDF à texte extractible (non-image) |

**Verdict C17 : ✅ acquise (11/13 pleinement prouvés, 2 fragiles).** Les fragilités (fidélité
maquettes + config.toml Docker) sont mineures et corrigeables rapidement.

---

## C18 — Automatiser les phases de tests par intégration continue

> *Garantir la qualité technique des réalisations au versionnement des sources.*

### Vue d'ensemble

La chaîne CI applicative (`.github/workflows/ci-app.yml`, GitHub Actions) est complète,
documentée et **réellement exécutée** par la plateforme. Elle enchaîne lint, format, audit de
sécurité, migrations, tests avec seuils de couverture bloquants et builds Docker de validation.
Toutes les commandes documentées ont été **rejouées localement au vert** lors de la
vérification. C18 est acquise sans réserve de fond ; le seul manque est une capture d'un run
GitHub Actions (`gh` indisponible dans l'environnement de rédaction).

### Outil, déclencheurs et cohérence technique

L'outil est **GitHub Actions** (le dépôt est sur GitHub), runner `ubuntu-latest`, Python 3.11 +
`uv` (`astral-sh/setup-uv`) — cohérent avec le stack Python du projet. Les déclencheurs sont
`push` **et** `pull_request` sur `develop` et `main` (`ci-app.yml:38-46`), ce qui satisfait
l'exigence « au push ET pull_request ».

### Étapes de la chaîne

Le job `test` enchaîne, dans l'ordre, toutes les étapes préalables aux tests puis les tests
eux-mêmes :

| # | Étape | Ligne (`ci-app.yml`) |
|---|---|---|
| 1 | `checkout` | :98 |
| 2 | setup Python 3.11 | :102 |
| 3 | setup `uv` | :109 |
| 4 | `uv sync --extra dev` | :117 |
| 5 | `pip-audit` (audit de vulnérabilités) | :128 |
| 6 | `ruff check src/ tests/` | :134 |
| 7 | `ruff format --check` | :139 |
| 8 | service PostgreSQL 16 + création défensive de la base | :58-71, :148-151 |
| 9 | `alembic upgrade head` (migrations avant tests) | :157-158 |
| 10 | `pytest tests/ --cov=src/tomatoscan/api --cov-fail-under=75` | :164-170 |
| 11 | `pytest tests/test_model/ --cov=src/tomatoscan/model --cov-fail-under=80` | :171-175 |
| 12 | build Docker de validation (API + front, sans push) | :183-186 |

Les **seuils de couverture sont bloquants** via `--cov-fail-under` : le rejeu local donne API =
**112 passed**, couverture **79,28 %** (≥ 75, « Required test coverage of 75% reached ») et
modèle = **25 passed**, **85,07 %** (≥ 80). La présence d'un **service PostgreSQL réel** (pas un
mock) et le rejeu des migrations Alembic avant pytest garantissent que les tests s'exécutent
contre un schéma conforme à la production.

**[CAPTURE À INSÉRER — C18 : l'onglet Actions de GitHub montrant un run `ci-app.yml` au vert,
avec les étapes lint / format / pip-audit / migrations / pytest (seuils atteints) / build Docker
toutes en succès — idéalement le run `29764535749` (SHA `bc0bb800`).]**

### Documentation et versionnement de la chaîne

`docs/ci_application.md` couvre l'ensemble : tableau « Outils utilisés » (l.18-30 : GitHub
Actions, `uv`, `pytest`+`pytest-cov`, `ruff`, `pip-audit`, Alembic, PostgreSQL 16, Docker),
section « Déclencheurs » (l.32-43), tableau « Étapes du pipeline » (l.51-64) et le job
« livraison » (l.66-70). Elle documente aussi l'installation (l.75-79), la configuration des
secrets/variables (l.81-98 : `SECRET_KEY`, `ADMIN_*`, `DATABASE_URL`, `MODEL_PATH`…) et le test
en local (l.110-131). Toutes ces commandes ont été rejouées au vert (ruff « All checks
passed » / « 69 files formatted », pip-audit « No known vulnerabilities found », pytest API +
modèle). Les configurations sont versionnées (`git ls-files .github/workflows/` → `ci-app.yml`,
`ci-model.yml`, `cd-model.yml` ; `alembic/`, `pyproject.toml` config ruff/pytest). Une note
d'accessibilité clôt le document (`ci_application.md:141`).

### Tableau des critères — C18

| Critère | Statut | Preuve |
|---|---|---|
| La doc couvre outils, étapes, tâches et déclencheurs | ✅ | `docs/ci_application.md:18-30,32-43,51-70` ; déclencheurs confirmés `ci-app.yml:38-46` |
| L'outil CI est cohérent avec l'environnement technique | ✅ | GitHub Actions, `ubuntu-latest`, Python 3.11 + `uv` (`ci-app.yml:36-52`), stack Python |
| La chaîne intègre les étapes préalables (build, config) | ✅ | `ci-app.yml:96-186` : checkout, setup, `uv sync`, pip-audit, ruff, PostgreSQL 16 réel, `alembic upgrade head` avant pytest |
| La chaîne exécute les tests au push ET PR, avec seuils de couverture | ✅ | `ci-app.yml:164-175` `--cov-fail-under=75` (API) / `80` (modèle) ; rejeu : 112 passed 79,28 %, 25 passed 85,07 % |
| Les configurations sont versionnées sur dépôt distant | ✅ | `git ls-files .github/workflows/` ; `alembic/`, `pyproject.toml` versionnés ; origin GitHub |
| La doc couvre installation, configuration et test de la chaîne | ✅ | `ci_application.md:75-79,81-98,110-131` — commandes rejouées vertes |
| La doc respecte les recommandations d'accessibilité | ✅ | `ci_application.md:141` (Markdown structuré, tableaux à en-têtes, pas d'info par couleur seule) |

**Verdict C18 : ✅ acquise (7/7 prouvés).** Seul reliquat : insérer la capture d'un run réel
(config + rejeu local couvrent déjà la preuve d'exécution).

---

## C19 — Créer un processus de livraison continue

> *S'appuyer sur la chaîne d'intégration continue, paramétrer les outils d'automatisation et
> les environnements de test pour une restitution optimale.*

### Vue d'ensemble

La livraison continue repose sur **deux maillons** : (1) le job `livraison` de `ci-app.yml`
construit et pousse les images Docker sur **ghcr.io** après validation des tests, et (2)
**Coolify** (PaaS sur le VPS OVH) déploie la stack. Le point fort de C19 est qu'il est
**prouvé par des runs GitHub Actions réels** (pas seulement une validation YAML locale) : le
packaging et le push d'images s'exécutent effectivement, et la livraison est bien
**conditionnée aux tests** et **interdite depuis une PR**.

### Étapes, déclencheurs et exécution réelle

`docs/cd_application.md:57-73` documente 8 étapes (push `develop`/`main`, job `test`, job
`livraison` avec `needs: test`, build Coolify, sélection de la stack Compose selon la branche,
démarrage des conteneurs, attente `service_healthy`, bascule du trafic) avec le déclencheur de
chacune, plus le déclenchement manuel (bouton *Redeploy* Coolify, l.184-191). L'exécution réelle
est attestée par l'API GitHub Actions : workflow `id 305436964`, `active`, `83` runs ; le run
`29764535749` (SHA `bc0bb800`, push `develop`) est `success` sur ses deux jobs — « Tests & Lint
(Python 3.11) » et « Livraison — build & push des images vers ghcr.io ».

### Packaging Docker — exécuté sans erreur

Le packaging est **double** et prouvé sur ce run réel :

- job `test`, étape 14 « Build Docker de validation (API + frontend, sans push) » → `success`
  (`ci-app.yml:183-186`, `docker build Dockerfile.api` + `Dockerfile.front`) ;
- job `livraison`, étapes 4 et 5 « Build & push image API » / « Build & push image frontend » →
  `success` (`ci-app.yml:237-256`, `docker/build-push-action@v6`) vers
  `ghcr.io/sulivan-moreau/tomatoscan-{api,front}`.

Les fichiers référencés par `Dockerfile.api:41` (`docs/rapport_evaluation_20260624_163236.json`,
`docs/confusion_matrix.png`, `docs/historique_20260624_161841.csv`) sont bien présents dans le
dépôt, ce qui explique pourquoi le build réussit désormais (correctif d'embarquement des
artefacts).

### Livraison conditionnée et interdite depuis une PR

Le job `livraison` porte `needs: test` et
`if: github.event_name == 'push' && (ref develop || main)` (`ci-app.yml:203-206`). La preuve du
comportement conditionnel est **observée sur des runs réels** : sur un push `develop` (run
`29764535749`) le job `livraison` s'exécute **après** un job `test` vert et pousse les images ;
sur un run `pull_request` (`29765851517`, branche `fix/rapport-entrainement-prod`) le même job
est **`skipped`**. La livraison n'a donc lieu qu'après packaging/tests validés, et jamais depuis
une PR — exactement le garde-fou attendu.

### Installation, configuration et test de la chaîne de livraison

`docs/cd_application.md` documente : l'**installation** (l.79-96 : création de l'app Coolify,
environnements `develop`/`main`, webhook, prérequis `.env` / `best_model.pt` / secrets GitHub),
la **configuration** (l.98-131 : ghcr.io + `GITHUB_TOKEN`/`packages:write`, tableau des
variables `.env`, ports) et la **procédure de test/debug** (l.133-157 : healthcheck `/health`,
`just up-dev`, `docker compose` local, diagnostic des logs Coolify). Le document est honnête sur
ses limites : la **protection de branche** GitHub (exiger le status check `test`) est documentée
comme recommandation mais **pas encore appliquée** (l.159-182) — sans elle, le « conditionné aux
tests » repose sur `needs: test` côté ghcr.io, mais Coolify build indépendamment ; la gate
humaine sur le merge reste à activer.

**[CAPTURE À INSÉRER — C19 : le tableau de bord Coolify montrant le déploiement `develop`
(préprod) et/ou `main` (prod) réussi — conteneurs à jour et `healthy` — avec l'URL publique
correspondante ; à mettre en regard du run ghcr.io « Build & push » vert.]**

### Tableau des critères — C19

| Critère | Statut | Preuve |
|---|---|---|
| La doc couvre toutes les étapes, tâches et déclencheurs | ✅ | `cd_application.md:57-73` (8 étapes + déclencheurs) ; déclenchement manuel l.184-191 ; deux maillons ghcr.io + Coolify l.7-46 |
| Les fichiers de config sont reconnus et exécutés par le système | ✅ | `ci-app.yml` actif (workflow id 305436964, `active`, 83 runs) ; run `29764535749` (SHA `bc0bb800`) `success` sur les 2 jobs |
| Les étapes de packaging (build containers) s'exécutent sans erreur | ✅ | Run réel : build validation API+front `success` (`ci-app.yml:183-186`) ; build & push API/front `success` (`ci-app.yml:237-256`) ; artefacts `Dockerfile.api:41` présents |
| L'étape de livraison est intégrée et exécutée après packaging validé | ✅ | `needs: test` + `if push && (develop\|main)` (`ci-app.yml:203-206`) ; push `develop` → livraison exécutée, run PR `29765851517` → livraison `skipped` |
| Les sources de la chaîne sont versionnées et accessibles | ✅ | `git ls-files` : `ci-app.yml`, `docker-compose.yml`, `docker-compose.override.yml`, `Dockerfile.api/front`, `cd_application.md` ; origin GitHub public |
| La doc couvre installation, configuration et test de la chaîne | ✅ | `cd_application.md:79-96,98-131,133-157` ; limite protection de branche assumée l.159-182 |
| La doc respecte les recommandations d'accessibilité | ⚠️ | `cd_application.md` structuré H1→H3, tableaux à en-têtes, note l.196 ; conformité auto-déclarée (pas d'audit outillé) — acceptable pour de la doc développeur |

**Verdict C19 : ✅ acquise (6/7 pleinement, 1 fragile mineur).** La livraison continue est
réellement exécutée par la plateforme et correctement conditionnée. À activer avant la
soutenance : la protection de branche GitHub (gate humaine sur le merge) et la capture Coolify.

---

## Grille de correspondance au référentiel

Renvoi synthétique de chaque critère à sa preuve (détail et statut dans les tableaux ci-dessus).

### C14 — Analyse du besoin et spécifications
| Critère | Où est la preuve |
|---|---|
| Modélisation des données (formalisme) | `docs/modelisation.md:35-56` (erDiagram) ↔ `database/modeles.py` |
| Modélisation des parcours (formalisme) | `docs/modelisation.md:139-168` (2 flowchart) ; wireframes `modelisation.pdf` |
| Specs : contexte / scénarios / critères | `docs/specs_fonctionnelles.pdf` p.4-8 (5 user stories) |
| Accessibilité dans les critères d'acceptation | colonne « ACCESSIBILITÉ (AA) » par story |
| Accessibilité fondée sur un standard | « WCAG 2.1 AA » `modelisation.md:174` (ratios 6.39:1 / 6.22:1) |

### C15 — Cadre technique et POC
| Critère | Où est la preuve |
|---|---|
| Architecture / dépendances / environnement | `docs/architecture.md:17-125` |
| Éco-responsabilité des services | `poc_conclusion.md:78-96` ; Coolify PaaS OVH |
| Diagramme de flux (OBLIGATOIRE) | `docs/modelisation.md:82-118` (Mermaid) |
| POC en préproduction ❌ | correctifs déploiement présents ; **preuve live à fournir** |
| Conclusion GO/NO-GO | `poc_conclusion.md:154-172` (GO avec réserves) |

### C16 — Coordination agile / MLOps
| Critère | Où est la preuve |
|---|---|
| Cycle / rôles / rituels agiles ⚠️ | 41 merges, branches `feature/*`/`fix/*`, template issue ; rituels non tenus |
| Outils de pilotage ⚠️ | `backlog.md`, `pr_cadence.md` ; kanban non capturé |
| Rituels partagés aux parties prenantes ⚠️ | modalités `journal_rituels.md:55-59` ; partage non prouvé |
| Pilotage accessible tout au long ⚠️ | dépôt public + docs versionnées ; continuité à démontrer |

### C17 — Composants et interfaces
| Critère | Où est la preuve |
|---|---|
| Environnement de dev | `front/requirements.txt`, `Dockerfile.front:16,39` |
| Interfaces vs maquettes ⚠️ | écrans ↔ wireframes `modelisation.pdf` ; écarts email→username, filtre absent |
| Comportements (validation/navigation) | `app.py:169-217`, `predict.py:157-180` ; `test_navigation_role.py` |
| Composants métier | pages front + `api_client.py` ; 41 tests verts |
| Droits d'accès (double barrière) | `app.py:190-204` + `dashboard.py:78-80` ; tests `:107-144` |
| Flux de données | `api_client.py:47` `TOMATOSCAN_API_URL` |
| Éco-conception ⚠️ | compression `predict.py:46-91`, cache `dashboard.py:37-57` ; config.toml Docker inerte |
| OWASP interface | `html.escape()` `api_client.py:84` ; `core/owasp.md` |
| Tests composants + accès | 41 passed, front 84 % ; `test_navigation_role.py` |
| Sources versionnées | `git remote -v` ; front + tests |
| Accessibilité au développement | `lang="fr"` `app.py:89-114` ; contrastes AA |
| Doc technique | `architecture.md:17,80,110-125,168` |
| Doc accessible | Markdown + TOC `architecture.md:10` |

### C18 — Intégration continue (tests)
| Critère | Où est la preuve |
|---|---|
| Doc outils / étapes / déclencheurs | `docs/ci_application.md:18-70` |
| Outil CI cohérent | GitHub Actions + `uv` (`ci-app.yml:36-52`) |
| Étapes préalables (build, config) | `ci-app.yml:96-186` (PostgreSQL 16, `alembic upgrade head`) |
| Tests au push ET PR + seuils | `ci-app.yml:164-175` ; 112/25 passed, 79,28 %/85,07 % |
| Config versionnée | `git ls-files .github/workflows/` |
| Doc install / config / test | `ci_application.md:75-131` |
| Doc accessible | `ci_application.md:141` |

### C19 — Livraison continue
| Critère | Où est la preuve |
|---|---|
| Doc étapes / tâches / déclencheurs | `cd_application.md:57-73` |
| Config reconnue et exécutée | run `29764535749` (SHA `bc0bb800`) `success` |
| Packaging containers sans erreur | builds validation + push `success` (`ci-app.yml:183-256`) |
| Livraison après packaging validé | `needs: test` + `if push` ; PR `29765851517` `skipped` |
| Sources versionnées | `git ls-files` (workflows, compose, Dockerfiles) |
| Doc install / config / test | `cd_application.md:79-157` |
| Doc accessible ⚠️ | `cd_application.md:196` (auto-déclaré) |

---

## Synthèse et verdict

| Compétence | Verdict | Critères prouvés | Points à consolider |
|---|---|---|---|
| **C14** | ✅ Acquise | 5/5 | Uniformiser « WCAG 2.1 AA » entre PDF et `modelisation.md` (détail) |
| **C15** | ⚠️ À risque | 4/5 | ❌ preuve live préprod (capture Coolify + URL + `curl /health`) ; mettre à jour `poc_conclusion.md` |
| **C16** | ⚠️ À risque | 0/4 pleins, 4/4 fragiles | Captures kanban GitHub Projects + journal de rituels réellement tenu |
| **C17** | ✅ Acquise | 11/13 pleins, 2 fragiles | Écarts maquettes à justifier + `config.toml` Docker + couverture `creer_membre.py` |
| **C18** | ✅ Acquise | 7/7 | Capture d'un run GitHub Actions au vert |
| **C19** | ✅ Acquise | 6/7 pleins, 1 fragile | Protection de branche GitHub + capture Coolify |

**Bilan.** Quatre compétences (C14, C17, C18, C19) sont **acquises** ; deux (C15, C16) sont **à
risque mais défendables**, avec des manques clairement identifiés et **non fabriqués**. Le point
central à traiter avant la soutenance est **la preuve *live* du déploiement** : la plomberie de
livraison continue fonctionne désormais (images poussées sur ghcr.io, correctifs de démarrage et
d'embarquement d'artefacts en place, run GitHub Actions vert), ce qui **renforce C15 et C19** ;
il ne manque que la capture d'exécution en préprod (Coolify + `curl /health`) et la mise à jour
de `poc_conclusion.md`, qui affirme encore l'inverse. Pour C16, le socle « process Git » est
solide et prouvé ; ce qui manque est le matériel de démonstration humain (kanban, rituels
datés).

La cohérence des chiffres a été vérifiée transversalement et **aucune valeur n'en contredit une
autre** : accuracy de test **0,9355** sur **10 classes** / **2 402 images**, **112 tests API**
(couverture **79,28 %**), **25 tests modèle** (**85,07 %**), **41 tests frontend** (couverture
**84 %**), **41 PR fusionnées** (dont 1 sur `main`), contrastes AA **6,39:1** / **6,22:1**. Les
PDF de conception obsolètes sont explicitement remplacés par `docs/modelisation.md` comme source
de vérité.

### À faire manuellement par le candidat avant le 31 juillet 2026

1. **C15.4 — preuve de préprod** : diagnostiquer et confirmer le déploiement Coolify, puis
   insérer la **capture Coolify (conteneurs `healthy`) + l'URL préprod + la sortie de
   `curl -I https://<domaine-preprod>/health` en 200**. Mettre à jour `docs/poc_conclusion.md`
   (§1 l.22, §5 l.102-114) pour refléter la préprod rétablie — sinon le dossier se contredit.
2. **C16 — kanban et rituels** : insérer au moins deux captures du **GitHub Project** à deux
   dates distinctes (`docs/agile.md:126-132`) et remplir `docs/journal_rituels.md:69-74` avec de
   **vrais points de suivi datés** (remplacer les lignes `[EXEMPLE]`). Actualiser « 35 PR » →
   **41** dans `docs/pr_cadence.md`.
3. **C17 — maquettes et éco-conception** : reporter les wireframes dans `docs/modelisation.md`
   (source éditable), **justifier les écarts** email→username et l'absence de filtre historique,
   et corriger le chargement de `.streamlit/config.toml` en Docker (déplacer à la racine du CWD
   ou passer `--server.maxUploadSize=5` dans la `CMD`). Compléter la couverture de
   `creer_membre.py` (62 %).
4. **C18 — capture CI** : joindre une capture (ou `gh run list --workflow=ci-app.yml`) d'un run
   `ci-app.yml` au vert (`gh` était indisponible dans l'environnement de rédaction).
5. **C19 — gate de merge** : activer la **protection de branche GitHub** (exiger le status check
   `test`) et joindre la capture Coolify du déploiement `develop`/`main`.
6. **Nettoyages de cohérence** : supprimer la référence résiduelle `tensorflow-macos/metal`
   (`architecture.md:127`), régénérer ou supprimer les PDF de conception obsolètes
   (`modelisation.pdf` MCD, `specs_techniques.pdf`) à partir de `docs/modelisation.md`, et
   uniformiser la mention « WCAG 2.1 AA ».

---

*Rapport établi le 20 juillet 2026 par vérification directe : fichiers relus, commandes réellement
exécutées (pytest API 112 / modèle 25 / frontend 41 ; couvertures 79,28 % / 85,07 % / 84 % ; ruff
et pip-audit au vert ; 41 merges Git ; runs GitHub Actions recoupés via l'API), aucun chiffre
supposé. Aucun commit ni push n'a été effectué lors de cette rédaction.*
