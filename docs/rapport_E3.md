# Rapport E3 — Mise en situation professionnelle

| | |
|---|---|
| **Candidat** | Sulivan Moreau |
| **Diplôme** | Développeur en Intelligence Artificielle (RNCP 37827) — Simplon, promotion 2026 |
| **Épreuve** | E3 — Développement, exposition, monitoring et livraison continue d'une IA |
| **Compétences évaluées** | C9, C10, C11, C12, C13 |
| **Projet** | TomatoScan — détection de maladies de la tomate (MobileNetV2, transfer learning, PyTorch) |
| **Dépôt** | https://github.com/sulivan-moreau/TomatoScan |
| **Déploiement** | VPS OVH (Roubaix) orchestré par Coolify, stack conteneurisée Docker |
| **Date de vérification** | 20 juillet 2026 |
| **Soutenance** | 31 juillet 2026 |

## Contexte du projet

TomatoScan classe des feuilles de tomate en 10 classes (dataset PlantVillage) grâce à un
modèle **MobileNetV2** entraîné par transfer learning (PyTorch). Le choix de MobileNetV2
n'est pas neutre : c'est un réseau léger (≈ 2,2 millions de paramètres pour ce projet, dont
seul le classifier final est entraîné, base ImageNet gelée — voir `model/train.py:34-53`),
adapté à un déploiement sur un VPS sans GPU. L'architecture applicative se décompose en
quatre briques :

- une **API FastAPI** qui expose le modèle et authentifie les appels par JWT ;
- un **frontend Streamlit** multi-pages qui consomme cette API ;
- une base **PostgreSQL** (accès asynchrone `asyncpg`, migrations Alembic) qui persiste
  utilisateurs et prédictions ;
- une chaîne de **monitoring Prometheus / Grafana** doublée d'une journalisation `loguru`.

Deux chaînes **GitHub Actions** couvrent l'application (`ci-app`, `cd-application`) et le
modèle (`ci-model`, `cd-model`). Deux rôles applicatifs coexistent : `admin` (gestion des
comptes, tableau de bord, matrice de confusion) et `agriculteur` (analyse d'images,
historique personnel). Ce rapport traite exclusivement des compétences E3 : l'exposition
du modèle (C9), son intégration dans une application (C10), son monitoring (C11), ses tests
automatisés (C12) et sa livraison continue (C13).

## Méthode de vérification

Chaque critère ci-dessous s'appuie sur une preuve datée : un fichier (référencé par
`chemin:ligne`) ou une commande réellement exécutée. Les chiffres de test proviennent
d'exécutions réelles de `pytest`, jamais d'un décompte de mémoire. Les commandes suivantes
ont été relancées lors de la rédaction de ce rapport :

```
uv run pytest tests/ -q                              → 112 passed, 15 warnings in 11.43s
uv run pytest tests/ --collect-only -q               → 112 tests collected
uv run pytest tests/test_api/  --collect-only -q     → 44 tests collected
uv run pytest tests/test_model/ --collect-only -q    → 25 tests collected
uv run pytest tests/test_frontend/ --collect-only -q → 41 tests collected
uv run pytest tests/test_database/ --collect-only -q → 2  tests collected
uv run pytest tests/test_model --cov=src/tomatoscan/model --cov-fail-under=80
     → evaluate.py 80 %, preprocess.py 88 %, train.py 90 % — TOTAL 85.07 % ; 25 passed
git remote -v                                        → origin https://github.com/sulivan-moreau/TomatoScan.git
```

Le total se décompose exactement : **112 = 44 (API) + 25 (modèle) + 41 (frontend) + 2 (BDD)**.
Ce décompte est cohérent avec `docs/tests.md:18-47` (vue d'ensemble et répartition par domaine).

**Légende des statuts** : ✅ prouvé · ⚠️ fragile (défendable à l'oral, à consolider) ·
❌ manquant · ⬜ non vérifiable dans cet environnement.

---

## C9 — Développer une API exposant un modèle d'IA (architecture REST)

### Vue d'ensemble

L'API FastAPI expose l'inférence du modèle via `POST /predict`, protégée par un JWT Bearer.
L'accès aux fonctions du modèle (prédiction, rapports d'entraînement et d'évaluation, matrice
de confusion) passe par des points de terminaison typés et documentés en OpenAPI 3.1.0. Les
recommandations OWASP API Security Top 10 (édition 2023) sont recoupées ligne à ligne avec le
code dans `core/owasp.md`. Les 12 opérations REST sont couvertes par 44 tests verts.

### Architecture en couches

Le code de l'API est organisé en couches à responsabilité unique, ce qui rend chaque
fonction testable isolément et limite le couplage :

| Couche | Dossier | Rôle | Exemples |
|---|---|---|---|
| **Routes** | `api/routes/` | Points de terminaison HTTP, codes de statut, dépendances d'auth | `auth.py`, `predict.py`, `users.py`, `history.py`, `reports.py`, `health.py` |
| **Services** | `api/services/` | Logique métier détachée du transport HTTP | `model_service.py` (chargement + inférence MobileNetV2) |
| **Schemas** | `api/schemas/` | Contrats d'entrée/sortie validés par Pydantic | `auth.py`, `predict.py`, `users.py`, `reports.py`, `history.py` |
| **Core** | `api/core/` | Sécurité transverse, configuration | `security.py` (JWT, bcrypt), `limiter.py` (slowapi), `owasp.md` |

Le point d'entrée `main.py` assemble ces couches : il inclut les six routeurs
(`main.py:257-262`), enregistre trois middlewares (rate limiter, CORS, en-têtes de sécurité,
`main.py:241-254`), monte l'exporteur Prometheus (`main.py:268`) et gère le cycle de vie via
`lifespan` (`main.py:125-142` : création des tables, bootstrap du compte admin, chargement
unique du modèle au démarrage). Le service modèle est chargé **une seule fois** au démarrage
(`model_service.initialiser_modele()`, `main.py:141`) plutôt qu'à chaque requête — un choix de
performance vérifiable dans le code.

Un point d'architecture non trivial mérite d'être souligné à l'oral : les middlewares
`EnteteSecuriteMiddleware` (`main.py:31-61`) et le rate limiter sont implémentés en **ASGI
pur** (scope/receive/send) et non via `BaseHTTPMiddleware`. La raison est documentée dans le
code (`main.py:34-41`) : `BaseHTTPMiddleware` exécute la suite de la requête dans une tâche
anyio distincte, ce qui casse `asyncpg` (`RuntimeError: Future attached to a different loop`)
dès qu'une route ouvre une connexion PostgreSQL. C'est une vraie difficulté rencontrée et
résolue, pas un choix cosmétique.

### Cycle de vie du JWT

Le jeton d'accès suit un cycle complet, entièrement paramétré par l'environnement (aucune clé
en dur) :

1. **Création** — `POST /auth/token` (`routes/auth.py:79-161`) vérifie les identifiants contre
   la table `users` (mot de passe hashé bcrypt), puis appelle
   `creer_token_acces({"sub": username, "role": role})` (`core/security.py:41-63`). La fonction
   lit `SECRET_KEY`, `ALGORITHM` (défaut `HS256`) et `ACCESS_TOKEN_EXPIRE_MINUTES` (défaut 30)
   depuis l'environnement, ajoute un claim `exp` calculé en UTC (`security.py:60-61`), et lève
   `RuntimeError` si `SECRET_KEY` est absente (`security.py:55-57`) — jamais de repli sur une clé
   par défaut.
2. **Vérification** — la dépendance interne `_decoder_charge` (`security.py:66-94`), branchée via
   `OAuth2PasswordBearer(tokenUrl="/auth/token")`, appelle `jwt.decode` et renvoie **401** sur
   toute erreur (`JWTError`) ou si `SECRET_KEY` manque. FastAPI met cette dépendance en cache par
   requête (`security.py:71-73`) : le token n'est décodé qu'une fois même quand une route dépend
   à la fois de l'utilisateur et du rôle. Deux dépendances publiques en dérivent :
   `obtenir_utilisateur_courant` (claim `sub`, 401 si absent) et `obtenir_role_courant` (claim
   `role`, 401 si absent — pas de rôle deviné par défaut, `security.py:109-128`).
3. **Autorisation** — `verifier_role_admin` (`security.py:131-137`) lève **403** si le rôle n'est
   pas `admin`. Cette dépendance est déclarée **au niveau du routeur `/users`**
   (`routes/users.py:24-35`, `dependencies=[Depends(verifier_role_admin)]`), donc elle s'applique
   aux trois routes du routeur sans risque d'oubli sur une route ajoutée ultérieurement.
4. **Renouvellement** — `POST /auth/refresh` (`routes/auth.py:60-76`) réémet un jeton aux mêmes
   claims avec une expiration fraîche. Il **exige un token encore valide** : la dépendance
   `obtenir_utilisateur_courant` lève 401 sur un token expiré, donc un jeton périmé ne peut pas
   être renouvelé — seule une reconnexion complète le permet. Ce comportement est verrouillé par
   `test_auth.py::test_refresh_token_expire` (→ 401) et symétriquement côté frontend (voir C10).
   Il n'existe qu'un seul type de jeton (pas de refresh token séparé ni de table dédiée) : un
   choix assumé, simple et suffisant pour le périmètre.

### Tableau des points de terminaison

Construit à partir des routeurs (`routes/*.py`) et du montage Prometheus (`main.py:268`) :

| Méthode | Chemin | Protection | Rôle requis | Route (fichier) |
|---|---|---|---|---|
| GET | `/health` | Aucune (public) | — | `health.py:7` |
| POST | `/auth/token` | Aucune + rate-limit 5/min | — | `auth.py:79-92` |
| GET | `/auth/me` | JWT Bearer | tout rôle | `auth.py:43-57` |
| POST | `/auth/refresh` | JWT Bearer (non expiré) | tout rôle | `auth.py:60-76` |
| POST | `/predict` | JWT Bearer | tout rôle | `predict.py:61-78` |
| GET | `/predictions/history` | JWT Bearer (filtré par rôle) | tout rôle | `history.py:24-33` |
| GET | `/reports` | JWT Bearer | tout rôle | `reports.py:34-47` |
| GET | `/reports/evaluation` | JWT Bearer | tout rôle | `reports.py:125-136` |
| GET | `/reports/confusion-matrix` | JWT Bearer | tout rôle | `reports.py:164-173` |
| GET | `/users` | JWT Bearer + `verifier_role_admin` | admin | `users.py:38-44` |
| POST | `/users` | JWT Bearer + `verifier_role_admin` | admin | `users.py:47-79` |
| DELETE | `/users/{user_id}` | JWT Bearer + `verifier_role_admin` | admin | `users.py:82-147` |
| — | `/metrics` (mount ASGI) | Aucune (choix assumé) | — | `main.py:268` |

Soit **12 opérations REST sur 11 chemins** (`/users` porte GET+POST), plus le mount `/metrics`.
Le contrôle de rôle n'est pas seulement fonctionnel mais aussi appliqué à la **lecture** :
`GET /predictions/history` (`history.py:43-55`) ne renvoie l'historique global qu'aux admins ;
un agriculteur ne voit que ses propres prédictions (filtre `user_id`). À la création
(`users.py:69-74`), le rôle est **forcé à `agriculteur`** et toute valeur envoyée par le client
est ignorée : l'API ne permet pas de fabriquer un second admin (fermeture d'une élévation de
privilège par construction).

### Sécurité : hash, validation, OWASP

**Hachage des mots de passe.** `core/security.py:19` instancie
`CryptContext(schemes=["bcrypt"], deprecated="auto")`. Les fonctions `hacher_mot_de_passe`
(`:22-24`) et `verifier_mot_de_passe` (`:27-38`) encapsulent bcrypt ; la vérification retourne
`False` (plutôt que de lever) sur un hash vide ou malformé, pour ne jamais faire planter la
route de login. Aucun mot de passe n'est jamais stocké en clair (`users.py:72`,
`hashed_password=hacher_mot_de_passe(...)`).

**Validation Pydantic + taille max.** Toutes les entrées passent par des schémas Pydantic
typés : `UserCreate` impose `password: str = Field(min_length=8)`
(`schemas/users.py:15`), d'où un **422** automatique sur un mot de passe trop court
(`test_users.py::test_creation_avec_mot_de_passe_trop_court_retourne_422`). Sur `POST /predict`,
la validation est en trois temps (`routes/predict.py:97-118`) : type MIME **et** extension
(`FORMATS_ACCEPTES`, `EXTENSIONS_ACCEPTEES`), puis taille du contenu lu contre
`TAILLE_MAX_OCTETS = 5 * 1024 * 1024` (**5 Mo**), enfin lisibilité réelle par PIL
(`UnidentifiedImageError` → 400). L'image est traitée en mémoire (`io.BytesIO`), jamais écrite
sur disque.

**Checklist OWASP API Security Top 10 (2023).** `core/owasp.md` recoupe chaque item avec le
code. Synthèse vérifiée :

| Item OWASP 2023 | Statut | Mécanisme (code) |
|---|---|---|
| API1 — Broken Object Level Authorization | ✅ | JWT sur `/predict` ; historique filtré par `user_id` (`history.py:43-55`) |
| API2 — Broken Authentication | ✅ | JWT expirable (`exp`), bcrypt, `SECRET_KEY` en `.env`, refresh refusé si expiré |
| API3 — Broken Object Property Level Auth. | ➖ | Réponses limitées aux champs des schémas : `UserOut` n'expose jamais le hash |
| API4 — Unrestricted Resource Consumption | ✅⚠️ | `@limiteur.limit("5/minute")` (slowapi) + blocage 5 échecs consécutifs (`auth.py:32,124`) + taille max 5 Mo. *Limite documentée : compteurs en mémoire de processus* |
| API5 — Broken Function Level Authorization | ✅ | `verifier_role_admin` au niveau du routeur `/users` ; rôle porté par le JWT, jamais par le client |
| API6 — Sensitive Business Flows | ➖ | Aucun flux métier sensible (ni paiement ni réservation) |
| API7 — Server Side Request Forgery | ➖ | Aucune requête sortante bâtie depuis une entrée utilisateur (aucun client HTTP importé dans `api/`) |
| API8 — Security Misconfiguration | ✅ | En-têtes de sécurité (`nosniff`, `DENY`, XSS) + garde-fou CORS au démarrage |
| API9 — Improper Inventory Management | ➖ | Surface unique et versionnée (OpenAPI généré, une seule version d'API) |
| API10 — Unsafe Consumption of APIs | ➖ | L'API ne consomme aucune API tierce |
| `/metrics` non authentifié | ⚠️ | Choix assumé (scraping interne Docker, aucune donnée personnelle en label) |

Deux points méritent d'être détaillés car ils illustrent une compréhension fine, pas une simple
case cochée :

- **API4 — le double verrou.** Le rate limiting slowapi (`5/minute` par IP) protège d'un débit
  élevé, mais une fenêtre glissante par minute n'empêche pas un attaquant patient d'espacer ses
  tentatives. Un **second compteur** `_echecs_consecutifs` (`auth.py:32`), indexé par nom de
  compte et **indépendant du temps**, bloque après 5 échecs consécutifs (`auth.py:124-128`) et
  se remet à zéro sur une connexion réussie (`auth.py:155`). Le code documente honnêtement les
  limites (`owasp.md:72-93`) : ces compteurs sont en mémoire de processus (remis à zéro au
  redémarrage, non partagés entre workers), acceptable car le déploiement réel n'a **qu'un seul
  processus uvicorn et un seul réplica**. Les deux mécanismes sont testés séparément
  (`test_security.py::test_rate_limiting`,
  `::test_5_echecs_consecutifs_bloquent_meme_si_le_debit_reste_bas`,
  `::test_connexion_reussie_reinitialise_le_compteur_d_echecs`).
- **API8 — le garde-fou CORS.** `_lire_cors_origins()` (`main.py:64-122`) refuse au démarrage
  (`RuntimeError`) une configuration CORS permissive (`allow_origins=["*"]`) hors des
  environnements de développement/test, et n'associe **jamais** le joker `*` à
  `allow_credentials=True` (combinaison interdite par la spec CORS que Starlette contourne
  dangereusement). Le commentaire du code (`main.py:64-121`) explique le défaut initial et sa
  correction : c'est une misconfiguration réelle qui avait été introduite silencieusement puis
  corrigée.

Le choix de laisser `/metrics` **non authentifié** est explicitement argumenté
(`owasp.md:192-245`) : la cible de scrape est interne au réseau Docker (`api:8000`, aucun port
publié sur l'hôte), et surtout **aucun label de métrique ne porte de donnée personnelle** — les
seuls labels sont `classe` (ensemble fini de classes MobileNetV2), `statut` (`"succes"`) et
`type_erreur` (chaînes littérales). Une restriction au niveau du reverse proxy est recommandée
en production. C'est une limite assumée et documentée, pas un oubli.

### Conformité OpenAPI 3.1 et tests

FastAPI génère automatiquement une spécification **OpenAPI 3.1.0** (`app.openapi()`), enrichie
de métadonnées : `title`, `version`, `contact`, `license` MIT et cinq `tags` documentés
(`main.py:196-210`, `_TAGS_METADATA` l.164-194). Chaque route déclare ses `responses={...}`
(codes 400/401/403/404/409/422/429/503 selon le cas) et une docstring qui alimente la
documentation interactive `/docs` et `/openapi.json`. Les schémas Pydantic peuplent la section
`components`.

Les **44 tests API** couvrent les 12 opérations. Répartition vérifiée par
`pytest --collect-only` : `test_auth.py` (8), `test_reports.py` (10), `test_predict.py` (6, dont
2 paramétrés), `test_users.py` (6), `test_security.py` (4), `test_history.py` (4),
`test_security_edge.py` (3), `test_health.py` (2), `test_metrics.py` (1). Les tests utilisent
`httpx.AsyncClient` contre l'application FastAPI réelle, avec le service modèle mocké
(jamais de poids MobileNetV2 chargés) et une base SQLite en mémoire (`docs/tests.md:168-179`).

| # | Critère | Statut | Preuve (fichier:ligne / commande) |
|---|---|---|---|
| 1 | Accès au modèle restreint par authentification | ✅ | `routes/predict.py:74-78` `Depends(obtenir_utilisateur_courant)` ; `core/security.py:66-94` valide le JWT et renvoie 401. Tests `test_security_edge.py` (SECRET_KEY absente → 401, token sans `sub` → 401) |
| 2 | Accès aux fonctions du modèle selon les spécifications | ✅ | `POST /predict` (`predict.py:74`) → `model_service.predire()` ; endpoints modèle `GET /reports`, `/reports/evaluation`, `/reports/confusion-matrix` (`reports.py:34,125,164`). `test_predict.py` → 200, `0.0 ≤ confiance ≤ 1.0` |
| 3 | Recommandations OWASP top 10 intégrées | ✅ | `core/owasp.md` (API1/2/4/5/8, numérotation 2023) recoupé au code ; tests `test_security.py` (headers, 429, 5×401) |
| 4 | Sources versionnées, dépôt Git distant | ✅ | `git remote -v` → origin GitHub ; HEAD poussé. *Nuance : voir « à faire » sur l'alignement de branche* |
| 5 | Tests couvrent tous les points de terminaison | ✅ | 12 opérations REST recensées, toutes testées ; 9 fichiers `tests/test_api/`, **44 tests collectés** |
| 6 | Tests s'exécutent sans bug | ✅ | `uv run pytest tests/test_api/ -q` → 44 passed (warning tiers passlib/crypt uniquement) |
| 7 | Résultats correctement interprétés | ✅ | `docs/tests.md:22-38` interprète couverture globale ~83 %, API ~78 % (seuil CI 75 %), modèle ~85 % (seuil 80 %) et distingue les trois périmètres |
| 8 | Documentation couvre architecture + tous les endpoints | ✅ | `docs/architecture.md` + OpenAPI auto-généré `/docs` (docstrings + `responses={...}`) |
| 9 | Documentation couvre auth / autorisation | ✅ | `main.py:145-162` (« Authentification » JWT Bearer) ; `owasp.md` API2/API5 |
| 10 | Doc + API respectent un standard (OpenAPI) | ✅ | `app.openapi()` → `openapi: 3.1.0`, `main.py:196-210` |
| 11 | Documentation accessible | ✅ | `architecture.md` note d'accessibilité (hiérarchie H1→H3, tableaux à en-têtes, pas d'info par la seule couleur) |

**C9 : 11/11 critères prouvés — compétence pleinement acquise.**

`[CAPTURE À INSÉRER — Swagger UI (/docs) montrant les 11 chemins regroupés par tags (Monitoring, Authentification, Prédiction, Rapports, Utilisateurs)]`

---

## C10 — Intégrer l'API d'un modèle d'IA dans une application

### Vue d'ensemble

Le frontend Streamlit consomme l'API via un client centralisé (`front/utils/api_client.py`) qui
gère l'authentification JWT, le **renouvellement proactif** du jeton avant expiration, et
l'intégration des 12 points de terminaison. Les 10 classes brutes du modèle sont traduites en
libellés français avec échappement HTML défensif. 41 tests d'intégration verts.

### Architecture Streamlit multi-pages

`front/app.py` est le point d'entrée. Il configure la page (`set_page_config`, `app.py:22-27`),
injecte un thème CSS (`inject_css`, `:30-86`), puis pilote une **navigation conditionnelle par
rôle** via `st.navigation` (`:169-217`) :

- **non connecté** → pages `Accueil` + `Connexion` seulement, liens de sidebar masqués
  (`position="hidden"`, `app.py:209-215`) ;
- **connecté (tout rôle)** → `Accueil`, `Analyse`, `Historique` ;
- **connecté admin** → en plus `Tableau de bord` et `Créer un membre` (`app.py:190-204`).

La navigation n'est donc pas un simple masquage de liens : les pages admin ne sont même pas
enregistrées dans l'objet `st.navigation` d'un agriculteur. Ce comportement est verrouillé de
bout en bout par `test_navigation_role.py` (un agriculteur est bloqué sur les pages admin ; un
changement de rôle dans le token change immédiatement la navigation affichée), exécuté via
`streamlit.testing.v1.AppTest` sur le vrai `app.py`.

### Le client API : `_requete_api` factorisée

Le cœur du client est `_requete_api()` (`api_client.py:126-190`), un squelette commun qui
centralise :

- le **dispatch** explicite vers `requests.get/post/delete` (`:156-161`) — volontairement
  explicite plutôt que `requests.request` générique, pour que le point d'entrée réseau reste
  patchable par les tests ;
- les **timeouts** différenciés : `TIMEOUT = 10 s` pour les requêtes courtes, `TIMEOUT_PREDICT
  = 30 s` pour l'inférence CNN qui peut être plus longue (`:50-51`, `:358`) ;
- la **gestion d'erreur typée** : toute `requests.RequestException` devient une `ApiError`
  (`:171-172`) avec `status_code=None` ; toute réponse non-2xx devient une `ApiError` portant le
  **code HTTP** d'origine (`:174-188`), afin que chaque page réagisse précisément (401, 400,
  503…). Un `messages_par_code` optionnel permet de substituer un message convivial pour un code
  donné (ex. 401 sur login).

Cette factorisation supprime une duplication qui existait dans chaque fonction publique. Chaque
appelant garde la responsabilité d'interpréter le corps 2xx ; seuls le transport, le timeout et
les erreurs sont mutualisés. La classe `ApiError` (`:90-99`) porte l'attribut `status_code`,
pilier du flux 401 décrit plus bas.

### Renouvellement du token (mécanisme proactif)

Trois fonctions coopèrent (`api_client.py`) :

- `is_token_valid(token)` (`:265-279`) décode la payload JWT **sans vérifier la signature** (la
  vérification de validité est faite côté API) uniquement pour lire le claim `exp` et comparer à
  `time.time()`. Un token malformé → `False` (loggué).
- `temps_restant_avant_expiration(token)` (`:282-295`) renvoie le nombre de secondes restantes.
- `renouveler_si_necessaire(token)` (`:318-336`) applique la règle : si le token expire dans
  **moins de `SEUIL_RENOUVELLEMENT_SECONDES = 120 s`** (`:55`), il appelle `refresh_token()`
  silencieusement ; sinon il renvoie le token inchangé. En cas d'échec réseau du renouvellement,
  il **retourne le token inchangé** plutôt que de faire planter la page — le prochain appel API
  déclenchera le flux 401 si le token a fini par expirer.

`refresh_token()` (`:298-315`) appelle `POST /auth/refresh` avec le token courant : côté API, un
token **déjà expiré** est rejeté en 401 (voir C9). Ce refus est prouvé **des deux côtés** : le
test frontend `test_api_client.py::TestRenouvellementToken` vérifie que le renouvellement ne se
déclenche que sous le seuil, et le test API `test_auth.py::test_refresh_token_expire` vérifie le
401. Le renouvellement est branché dans le cycle de vie de la page : `app.py:157`
(`st.session_state.token = api_client.renouveler_si_necessaire(token_actuel)`), une fois par
re-run Streamlit, avant tout appel API.

### Le flux 401 : `gerer_erreur_401`

`front/utils/session.py:14-26` définit `gerer_erreur_401(erreur)` : si `erreur.status_code ==
401`, la session est **entièrement vidée** (`st.session_state.clear()`) et un rerun redirige vers
la connexion ; sinon la fonction ne fait rien et laisse l'appelant traiter les autres codes.
Cette fonction factorise un bloc auparavant dupliqué dans quatre pages
(`creer_membre`, `dashboard`, `history`, `predict`). La distinction est nette et testée : un
**401 vide la session**, un **400 métier ne la vide pas** (`pages/predict.py:209-218` appelle
`gerer_erreur_401(erreur)` puis traite le 400/503 ; test
`test_gestion_401.py::test_predict_erreur_400_n_efface_pas_la_session`). Une double barrière
existe aussi dans `app.py` : à chaque re-run, un token invalide localement vide la session
(`app.py:149-152`), et un token sans rôle en session est considéré incohérent et déconnecté
(`app.py:161-164`).

### Correspondance endpoint → fonction client → page

Chaque opération de l'API a une fonction dédiée dans `api_client.py`, elle-même appelée par une
page précise (vérifié par `grep` sur `front/pages/`) :

| Endpoint API | Fonction client | Page(s) consommatrice(s) |
|---|---|---|
| `GET /health` | `ping()` (`:196`) | client (health-check), couvert par `TestPing` |
| `POST /auth/token` | `login()` (`:210`) | `pages/login.py:52` |
| `GET /auth/me` | `me()` (`:234`) | `pages/login.py:53` |
| `POST /auth/refresh` | `refresh_token()` / `renouveler_si_necessaire()` (`:298/318`) | `app.py:157` |
| `POST /predict` | `predict()` (`:339`) | `pages/predict.py:203` |
| `GET /predictions/history` | `get_history()` (`:427`) | `pages/history.py:44`, `pages/dashboard.py:57` |
| `GET /reports` | `get_reports()` (`:447`) | `pages/dashboard.py:45` |
| `GET /reports/evaluation` | `get_evaluation()` (`:468`) | `pages/dashboard.py:128` |
| `GET /reports/confusion-matrix` | `get_confusion_matrix()` (`:490`) | `pages/dashboard.py:163` |
| `GET /users` | `list_users()` (`:369`) | `pages/dashboard.py:51` |
| `POST /users` | `create_user()` (`:389`) | `pages/creer_membre.py:61` |
| `DELETE /users/{id}` | `delete_user()` (`:409`) | `pages/dashboard.py:257` |

Les 10 classes brutes du modèle sont traduites en français par `DISEASE_LABELS` +
`fr_label()` (`api_client.py:60-84`). Le repli (classe inconnue) est **échappé** avec
`html.escape` avant retour (`:84`), car le résultat est rendu via
`st.markdown(unsafe_allow_html=True)` — défense en profondeur à coût nul, même si `classe`
provient toujours de la propre API.

### Éco-conception

Deux mécanismes concrets, documentés dans le code comme relevant de l'éco-conception (C17) :

- **Compression d'image côté client avant l'envoi réseau** (`pages/predict.py:46-91`,
  `_compresser_image`). Le plus grand côté est borné à `TAILLE_MAX_COTE_PX = 1024`
  (`:42`) et recompressé (`QUALITE_JPEG = 85`) : une photo de smartphone (souvent 4000×3000)
  est ramenée à ~1024 px, ce qui réduit fortement le volume transféré, alors que le modèle
  travaille de toute façon en 224×224. En cas d'erreur, les octets d'origine sont renvoyés
  (l'analyse n'est jamais bloquée). Le format d'origine est préservé pour ne pas casser le
  contrat multipart.
- **Cache des données du tableau de bord** (`pages/dashboard.py`). Streamlit relance tout le
  script à chaque interaction ; sans cache, les trois requêtes réseau (`get_reports`,
  `list_users`, `get_history`) seraient rejouées à chaque clic. Elles sont donc décorées
  `@st.cache_data(ttl=CACHE_TTL_SECONDES, show_spinner=False)` (`dashboard.py:37,48,54`), avec le
  token comme clé de cache. Après une écriture (suppression d'un compte), `_vider_cache_donnees()`
  (`:60,261`) invalide le cache pour ne pas resservir une liste périmée.

### Accessibilité

- **`lang="fr"` forcé** (`app.py:89-114`, `forcer_langue_francaise`). Streamlit sert son
  `index.html` en `lang="en"` codé en dur, sans option pour le changer (v1.58). Un court script
  injecté met à jour `document.documentElement.lang`, sinon les lecteurs d'écran annoncent le
  contenu francophone avec une prononciation anglaise. Le contournement est documenté et
  sans danger en test (AppTest n'exécute pas le JS).
- **Contrastes WCAG AA calculés.** Les bandeaux résultat de la page d'analyse utilisent du texte
  blanc sur `#2d6a4f` et `#c1121f`, dont les ratios (respectivement **6.39:1** et **6.22:1**) sont
  documentés comme calculés par la formule de luminance relative WCAG (`pages/predict.py:10-13`),
  au-dessus du seuil AA (4.5:1).
- **Textes alternatifs et sémantique.** L'aperçu d'image porte une caption descriptive servant de
  texte alternatif (`predict.py:167-172`) ; les icônes des bandeaux sont des **SVG inline
  `aria-hidden`** (le sens est porté par le libellé texte, pas par l'icône).

| # | Critère | Statut | Preuve (fichier:ligne / commande) |
|---|---|---|---|
| 1 | Application de départ installée et fonctionnelle en dev | ✅ | `.env.example` fournit un DSN async ; `app.py:22/205` structure la page et la navigation |
| 2 | Communication avec l'API fonctionne | ✅ | `api_client.py:126` `_requete_api()` centralise `requests` vers `API_URL`. `pytest tests/test_frontend/ -q` → 41 passed |
| 3 | Authentification et renouvellement (expiration) intégrés | ✅ | `api_client.py:298/318/265` ; refus d'un token expiré prouvé des deux côtés (`test_api_client.py` + `test_auth.py::test_refresh_token_expire`) |
| 4 | Tous les points de terminaison concernés sont intégrés | ✅ | 12 opérations intégrées (voir tableau endpoint → fonction → page) |
| 5 | Adaptations d'interface nécessaires intégrées | ✅ | `dashboard.py:128/163/257`, `api_client.py:60-84` `fr_label` + `html.escape`, compression image `predict.py:46-91` |
| 6 | Tests d'intégration couvrent tous les endpoints exploités | ✅ | `test_api_client.py` (chaque endpoint) + `test_gestion_401.py`, `test_navigation_role.py`, `test_regression_base64url.py` |
| 7 | Tests s'exécutent en totalité, sans bug | ✅ | `pytest tests/test_frontend/ -q` → 41 passed. Suite globale → 112 |
| 8 | Résultats correctement interprétés | ✅ | Contrats précis, pas de smoke tests (header Bearer exact, `accuracy_test == 0.9355`, octets PNG, champ multipart `fichier`, 3 branches de renouvellement) |
| 9 | Sources versionnées et accessibles | ✅ | `git ls-files` suit `api_client.py`, `test_api_client.py`, `.env.example` |

**C10 : 9/9 critères prouvés — compétence pleinement acquise.**

`[CAPTURE À INSÉRER — page « Analyse » (predict.py) après upload d'une image : bandeau de diagnostic (vert « Tomate saine » ou rouge maladie), recommandation et barre de confiance]`

---

## C11 — Monitorer un modèle d'IA (métriques, alerte, restitution)

### Vue d'ensemble

Quatre métriques Prometheus sont réellement instrumentées (`api/metrics.py`) et incrémentées
dans `routes/predict.py`, exposées sur `/metrics` et restituées par un dashboard Grafana de 7
panneaux. Un déclencheur de ré-entraînement (seuil d'accuracy 0,85) alimente une alerte CI.

### Les 4 métriques Prometheus

| Métrique | Type | Labels | Description | Où incrémentée (`predict.py`) |
|---|---|---|---|---|
| `tomatoscan_predictions_total` | Counter | `classe`, `statut` | Prédictions réussies par classe détectée et statut | `:149` `.labels(classe=classe, statut="succes").inc()` |
| `tomatoscan_prediction_duration_seconds` | Histogram | (aucun) | Durée d'inférence MobileNetV2 (buckets par défaut) | `:146` `.observe(perf_counter()-debut)` dans le `finally` |
| `tomatoscan_prediction_confidence` | Histogram | (aucun), buckets `[0.5…1.0]` | Distribution des scores de confiance (qualité modèle) | `:150` `.observe(confiance)` |
| `tomatoscan_errors_total` | Counter | `type_erreur` | Erreurs `/predict` par type | `:104/114/123/136/142` `.labels(type_erreur=…).inc()` |

Deux subtilités sont volontaires et défendables :

- **`prediction_duration` est observé dans le `finally`** (`predict.py:144-146`), donc mesuré
  **même en cas d'erreur d'inférence** — pour capturer aussi les requêtes lentes ou bloquantes,
  pas seulement les succès.
- **`prediction_confidence` a des buckets personnalisés** `[0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99,
  1.0]` (`metrics.py:24`) plutôt que les buckets par défaut orientés latence : ils sont pensés
  pour la plage utile d'un score de confiance. Le commentaire (`metrics.py:18-20`) explicite qu'il
  s'agit d'une **métrique de qualité du modèle** (dérive de confiance), pas d'une métrique
  applicative.

Les cinq `type_erreur` émis correspondent exactement aux points de rejet de `predict.py` :
`format_invalide`, `fichier_trop_lourd`, `modele_indisponible`, `image_corrompue`,
`erreur_prediction`. Chaque incrément est donc rattaché à une branche de code réelle.

### Les 7 panneaux Grafana

Parsés depuis `monitoring/grafana/dashboards/tomatoscan.json`. Chaque PromQL référence une
métrique **réellement définie** — aucun PromQL orphelin :

| # | Titre du panneau | Type | Requête PromQL |
|---|---|---|---|
| 1 | Prédictions / seconde | stat | `sum(rate(tomatoscan_predictions_total[5m]))` |
| 2 | Prédictions totales | stat | `sum(tomatoscan_predictions_total)` |
| 3 | Erreurs / seconde | stat | `sum(rate(tomatoscan_errors_total[5m]))` (seuils 0.05 / 0.1) |
| 4 | Durée d'inférence — MobileNetV2 | timeseries | `histogram_quantile(0.95, rate(tomatoscan_prediction_duration_seconds_bucket[5m]))` + p50 |
| 5 | Erreurs par type | timeseries | `sum(rate(tomatoscan_errors_total[5m])) by (type_erreur)` |
| 6 | Prédictions par classe détectée | timeseries | `sum(rate(tomatoscan_predictions_total[5m])) by (classe)` |
| 7 | Confiance moyenne des prédictions | stat | `sum(rate(tomatoscan_prediction_confidence_sum[5m])) / sum(rate(tomatoscan_prediction_confidence_count[5m]))` |

Le panneau 4 exploite le suffixe `_bucket` généré par l'Histogram, et le panneau 7 le couple
`_sum` / `_count` — la connaissance de ces suffixes Prometheus est réelle. Les fenêtres `[5m]`
associées à `rate()` et le `refresh: 30s` du dashboard (`tomatoscan.json:9`) confèrent bien un
caractère temps réel à la restitution. Le panneau 4 précise honnêtement dans sa description que
la durée mesurée **n'inclut pas la latence HTTP totale** de la requête, seulement l'inférence.

### Seuil de ré-entraînement

`model/evaluate.py:27` définit `SEUIL_ACCURACY_REENTRAINEMENT = 0.85` et `:33`
`SEUIL_F1_CLASSE_SOUS_PERFORMANTE = 0.80`. La fonction `verifier_seuil_reentrainement()`
(`:232-242`) est un **déclencheur pur** (aucun effet de bord) : elle retourne `True` si
l'accuracy de test passe sous 0,85 **ou** si au moins une classe est sous-performante en F1 — ce
second critère capture une dérive sur une maladie précise que l'accuracy globale peut masquer,
important pour un outil de diagnostic. `journaliser_declenchement()` (`:245-298`) écrit la
décision dans un CSV **cumulatif** (`reentrainement_log.csv`), append-only, pour garder un
historique des décisions dans le temps.

Le seuil 0,85 est justifié dans le code (`evaluate.py:20-26`) : le modèle de production tourne
autour de **93,5 % d'accuracy** (voir plus bas), donc 85 % laisse une marge pour absorber le
bruit de mesure tout en détectant une dérive réelle. La CI branche ce mécanisme
(`ci-model.yml:106-118`, étape « 7bis ») : si la dernière ligne du log vaut `,True`, un
`::warning::` est émis dans le résumé du run — **mais aucun déploiement n'est déclenché
automatiquement** (voir C13 pour la justification de ce choix assumé). Testé par
`test_evaluate.py::test_verifier_seuil_reentrainement` et
`::test_journaliser_declenchement_ecrit_puis_accumule_sans_dupliquer_l_en_tete`.

### Alerting Grafana

Trois fichiers de provisioning (`monitoring/grafana/provisioning/alerting/`) :

- `alertes.yml` définit une règle « Taux d'erreurs TomatoScan élevé » évaluée chaque minute,
  qui se déclenche si `sum(rate(tomatoscan_errors_total[5m])) > 0.1 req/s` maintenu 1 minute. Le
  fichier documente un **bug réel trouvé et corrigé** après un test en conditions réelles
  (`alertes.yml:15-22`) : sans une étape intermédiaire `reduce` (refId B) réduisant la série
  temporelle à une valeur unique avant le seuil (refId C), Grafana refusait d'évaluer la règle
  (« only reduced data can be alerted on »).
- `contact_points.yml` déclare un canal e-mail ; l'adresse est un espace réservé à remplacer,
  et **aucun secret n'est en dur** — les identifiants SMTP sont lus depuis les variables
  d'environnement `GF_SMTP_*` du service Grafana.
- `policies.yml` route toutes les alertes vers ce canal (une seule règle existe pour l'instant,
  un routage plus fin serait prématuré).

### Distinction C11 (modèle) vs C20 (application)

Point clé à défendre à l'oral : le monitoring **modèle** (C11) et le monitoring **applicatif**
(C20) sont distincts, et le code le matérialise.

- **C11 — santé du modèle** : `prediction_confidence` (distribution des scores, dérive),
  `predictions_total by (classe)` (distribution des diagnostics posés — panneau 6, décrit comme
  « métrique de comportement du modèle, pas applicative »). Une baisse continue de la confiance
  moyenne (panneau 7, seuils 0.7 / 0.85) signale une dérive du modèle ou des entrées inhabituelles.
- **C20 — santé de l'application** : `errors_total by (type_erreur)` (erreurs 400/503),
  `prediction_duration` (latence d'inférence), débit (`predictions/s`).

`metrics.py:18-20` documente explicitement que `prediction_confidence` est une métrique de
**qualité du modèle** et non applicative. Cette séparation évite de confondre « le modèle se
dégrade » (dérive) et « l'application a des erreurs » (bug, panne).

| # | Critère | Statut | Preuve (fichier:ligne / commande) |
|---|---|---|---|
| 1 | Métriques expliquées sans erreur d'interprétation | ✅ | `docs/monitoring.md:33-54` ; `metrics.py:18-20` distingue confiance (qualité) vs métrique applicative |
| 2 | Outils adaptés au contexte et aux contraintes | ✅ | `monitoring.md:56-93` justifie Prometheus/Grafana/loguru pour un déploiement conteneurisé ; `prometheus.yml` scrape `api:8000` |
| 3 | Au moins un vecteur de restitution temps réel | ✅ | `tomatoscan.json` = 7 panneaux, PromQL tous valides, `[5m]` + `rate` + `refresh: 30s` |
| 4 | Enjeux d'accessibilité pris en compte lors du choix de l'outil | ⚠️ | `monitoring.md` soulève l'enjeu (dashboard admin-only) mais **aucun audit WCAG mené sur Grafana**. *À consolider à l'oral : contrôle rapide (thème, clavier, contraste) ou assumer le public admin-only.* |
| 5 | Chaîne d'abord testée en bac à sable | ✅ | `monitoring.md` (vérifié en local) ; bug d'alerte trouvé/corrigé après test de trafic d'erreurs (`alertes.yml:15-22`) ; `docker-compose.local.yml` dédié |
| 6 | Chaîne en état de marche, métriques restituées | ✅ | 4 métriques incrémentées dans `predict.py` ; exposées `main.py:268` ; `test_metrics.py` (dans les 112) |
| 7 | Sources versionnées, dépôt distant | ✅ | `git ls-files monitoring/` ; aucun secret en dur (`GF_SMTP_*`) |
| 8 | Documentation installation / configuration / utilisation | ✅ | `monitoring.md` (commandes exécutables, distinction prod/préprod/local, variables `GF_SMTP_*`) |
| 9 | Documentation accessible | ✅ | `monitoring.md` note d'accessibilité ; structure vérifiée |
| + | Déclencheur de ré-entraînement (amélioration itérative) | ✅ | `evaluate.py:27/33/232-242` + log CSV ; `ci-model.yml:106-118` `::warning::`. *Choix assumé : alerte seulement, pas de redéploiement auto* |

**C11 : 9/10 critères prouvés, 1 fragile (accessibilité de l'outil Grafana non auditée) — compétence acquise, à consolider à l'oral sur le point 4.**

`[CAPTURE À INSÉRER — dashboard Grafana « TomatoScan — Monitoring » affichant les 7 panneaux avec des données réelles (débit de prédictions, durée d'inférence p50/p95, erreurs par type, confiance moyenne)]`

---

## C12 — Programmer les tests automatisés d'un modèle d'IA

### Stratégie de test

La stratégie est documentée dans `docs/tests.md` (plan de tests complet) et dans les docstrings
d'en-tête de chaque fichier de test. Deux principes structurent la suite (`tests.md:49-57`) :

1. **Un test nominal + un test d'erreur obligatoire par fonction**, pas de variantes multiples du
   même scénario — pour éviter le gonflement artificiel du nombre de tests sans gain de couverture.
2. **Exception explicite** : toute régression d'un bug réel (trouvé puis corrigé pendant
   l'écriture des tests) reste testée même si elle dépasse la règle ci-dessus.

La **stratégie de mock du modèle** est essentielle et honnête (`tests.md:210-215`) : jamais de
poids MobileNetV2/ImageNet réels ni de dataset PlantVillage réel. `construire_modele()` mocke la
base pré-entraînée par un faux `nn.Module` minimal ; `executer_epoch()`/`entrainer_modele()`
mockent modèle, optimizer et scheduler mais **laissent circuler de vrais tenseurs PyTorch**
(loss et accuracy calculés réellement, pas simulés) ; les fixtures de
`tests/test_model/conftest.py` génèrent de vraies petites images JPEG en mémoire
(`PIL.Image.new`, `conftest.py:22-24`). On teste donc la logique réelle sans dépendre d'un
entraînement lourd.

### Couverture par module

Mesure relancée lors de la rédaction :
`uv run pytest tests/test_model --cov=src/tomatoscan/model --cov-report=term --cov-fail-under=80`

| Module | Stmts | Miss | Couverture |
|---|---|---|---|
| `src/tomatoscan/model/__init__.py` | 0 | 0 | 100 % |
| `src/tomatoscan/model/evaluate.py` | 124 | 25 | 80 % |
| `src/tomatoscan/model/preprocess.py` | 64 | 8 | 88 % |
| `src/tomatoscan/model/train.py` | 100 | 10 | 90 % |
| **TOTAL** | **288** | **43** | **85,07 %** |

Résultat : `Required test coverage of 80% reached. Total coverage: 85.07% ; 25 passed`. Le seuil
CI de **80 %** (`ci-app.yml:175`, `--cov-fail-under=80`) est donc dépassé de ~5 points — une
marge volontaire (le seuil est fixé légèrement sous la couverture réelle) pour qu'il échoue sur
une vraie régression sans casser la CI au moindre arrondi (`tests.md:104-112`).

### Répartition nominal / erreur / limite

Les 25 tests couvrent les trois familles :

- **Nominal** : `test_transform_nominal_produit_un_tensor_224x224_deterministe`,
  `test_obtenir_classes_tomates_filtre_correctement`,
  `test_construire_modele_gele_la_base_et_remplace_le_classifier`,
  `test_charger_checkpoint_extrait_les_bons_champs`,
  `test_generer_rapport_calcule_l_accuracy_et_liste_les_classes_sous_performantes`, etc.
- **Erreur** : `test_obtenir_classes_tomates_dossier_introuvable` (`FileNotFoundError`),
  `test_dataset_fichier_corrompu_leve_une_erreur_non_geree` (fichier illisible),
  `test_afficher_confusion_matrix_classe_absente_ne_plante_plus` et
  `test_generer_rapport_classe_totalement_absente_ne_plante_plus` (deux régressions de bugs réels).
- **Limite** : `test_verifier_seuil_reentrainement` (franchissement du seuil 0,85),
  `test_entrainer_modele_early_stopping_sauvegarde_uniquement_aux_ameliorations` (arrêt anticipé
  après 3 dégradations), `test_journaliser_declenchement…` (accumulation sans doublon d'en-tête).

Les assertions portent sur des **valeurs calculées réelles**, pas des tautologies : par exemple
`test_generer_rapport…` vérifie une accuracy calculée et la liste des classes sous le seuil F1 ;
`test_afficher_confusion_matrix_produit_une_matrice_dix_par_dix` vérifie la forme et les
proportions de la matrice via l'appel intercepté à `imshow()`, pas via un appel direct à sklearn.

### Idempotence

La suite est **idempotente** : deux exécutions consécutives donnent le même résultat. Pour les
tests modèle, chaque test s'appuie sur `tmp_path` (dossier temporaire pytest jeté à chaque run) et
sur des fixtures qui recréent le dataset factice à neuf (`conftest.py:27-48`). Pour les tests
API/BDD, deux garde-fous (`tests.md:172-179`) : (1) les tables sont supprimées (`drop_all`) au
teardown de session, et (2) chaque test créant un compte génère un `username` unique via
`uuid4()`. Sans le premier, une base persistante (fichier SQLite local, PostgreSQL de la CI)
garderait un historique résiduel d'un run à l'autre ; sans le second, un second run échouerait sur
« username déjà pris ». Les deux mécanismes garantissent qu'aucun état ne fuit entre tests ni
entre exécutions.

### Les 4 étapes du modèle testées

La suite couvre les quatre étapes du cycle de vie du modèle, une par fichier de test :

1. **Validation / chargement des données** — `test_donnees.py` (5 tests) : filtrage des classes
   `Tomato*` (`obtenir_classes_tomates`), cohérence du mapping label ↔ index, dossier introuvable,
   fichier corrompu, couverture de toutes les classes/images.
2. **Préparation (preprocessing)** — `test_preprocessing.py` (3 tests) : transform nominale
   déterministe 224×224, normalisation ImageNet, transform avec augmentation toujours valide.
3. **Entraînement** — `test_train.py` (8 tests) : sélection du device (MPS/CPU), gel de la base +
   remplacement du classifier, une epoch d'entraînement (forward/backward/step par batch), une
   epoch de validation (aucun backward), sauvegarde CSV, orchestration complète, early stopping.
4. **Évaluation** — `test_evaluate.py` (9 tests) : chargement du checkpoint, inférence,
   construction/normalisation de la matrice de confusion (10×10), sauvegarde d'un fichier PNG,
   génération du rapport JSON, seuil de ré-entraînement, journalisation CSV.

### Résultat réel du modèle de production

Le rapport d'évaluation versionné `docs/rapport_evaluation_20260624_163236.json` atteste des
performances réelles du modèle : **accuracy de test 0,9355** (meilleure epoch 13, meilleure
accuracy de validation 0,9455), sur **2 402 images de test**, avec `classes_sous_performantes:
[]` (aucune classe sous le seuil F1 de 0,80 — la plus basse, `Tomato_Early_blight`, est à
F1 = 0,806). Ce fichier est la source du chiffre `0.9355` vérifié par le test frontend
`test_api_client.py` (`get_evaluation`), ce qui relie la valeur affichée dans l'application à une
mesure réelle.

| # | Critère | Statut | Preuve (fichier:ligne / commande) |
|---|---|---|---|
| 1 | Cas listés et définis (partie visée, périmètre, stratégie) | ✅ | `docs/tests.md:181-215` (tableau « Modèle » + stratégie commune) ; docstrings d'en-tête de chaque `test_*.py` |
| 2 | Outils de test cohérents avec l'environnement | ✅ | `tests.md:68-77` (pytest, pytest-cov) ; usage réel de `torch`, `PIL`, `unittest.mock` |
| 3 | Tests intégrés respectant la couverture établie | ✅ | `--cov-fail-under=80` → **85,07 %** (evaluate 80 %, preprocess 88 %, train 90 %) ; seuil appliqué en CI `ci-app.yml:175` |
| 4 | Tests s'exécutent sans problème (+ idempotence, nominal/erreur/limite) | ✅ | 25 passed ; suite globale idempotente (`tmp_path` + `drop_all` + `uuid4`) ; 3 familles présentes ; assertions sur valeurs calculées |
| 5 | Sources versionnées, dépôt distant | ✅ | `git ls-files tests/test_model/` ; `git remote -v` → origin GitHub |
| 6 | Documentation installation / dépendances / exécution / couverture | ✅⚠️ | `tests.md:59-112` (install, 3 commandes CI, justification des seuils). Décomptes globaux **corrigés** (l.20 = 112, l.45 = 25). *Reste : la table du § « Modèle » énumère 24 lignes ; ajouter `test_afficher_confusion_matrix_avec_chemin_sortie_sauvegarde_un_fichier` pour atteindre 25.* |
| 7 | Documentation accessible | ✅ | `tests.md:265` note d'accessibilité ; structure vérifiée |

**C12 : 7/7 critères prouvés (6 pleinement, 1 avec une correction mineure de doc restante) — compétence acquise.**

`[CAPTURE À INSÉRER — terminal : sortie de `uv run pytest tests/test_model --cov=src/tomatoscan/model --cov-fail-under=80` montrant le tableau de couverture par module et « Total coverage: 85.07% »]`

---

## C13 — Créer une chaîne de livraison continue d'un modèle d'IA (MLOps)

### Vue d'ensemble

Deux workflows GitHub Actions (`ci-model.yml`, `cd-model.yml`) automatisent le test des données,
l'entraînement, l'évaluation et le déploiement du modèle. L'orchestrateur
`scripts/ci_entrainement_evaluation.py` enchaîne le pipeline complet sur un mini-dataset versionné.
Les angles morts (déclencheurs non encore armés, `models/` gitignoré, `dry_run` par défaut) sont
documentés comme choix assumés.

### `ci-model.yml` — étapes détaillées

Déclencheurs (`ci-model.yml:19-23`) : push sur une branche `feature/model-*` **ou**
`workflow_dispatch` (manuel). Variables d'environnement CI (`:25-32`) : `CI_EPOCHS: 2`,
`CI_BATCH_SIZE: 4`, chemins des artefacts. Le job (`ubuntu-latest`, `timeout-minutes: 15`)
enchaîne 8 étapes :

1. **Checkout** du code, qui inclut `tests/fixtures/mini_dataset/` (`:42-43`).
2. **Setup Python 3.11** (`:46-49`).
3. **Setup uv** avec cache (`:52-55`).
4. **Installation torch/torchvision CPU-only** *avant* `uv sync` (`:61-64`) : évite de télécharger
   ~1,5 Go de wheels CUDA/NVIDIA inutiles sur un runner sans GPU — même stratégie que
   `Dockerfile.api`.
5. **Installation des dépendances** `uv sync --extra dev` (`:67-68`).
6. **Tests de préparation des données** (`:76-77`) : `pytest test_donnees.py test_preprocessing.py`
   — l'étape de test des données du critère C13.
7. **Entraînement + évaluation réels** (`:87-88`) via `ci_entrainement_evaluation.py` — aucun mock,
   les vraies fonctions de `train.py`/`evaluate.py`.
8. (**7bis**) **Vérification du seuil de ré-entraînement** (`:106-118`) : lit la dernière ligne de
   `reentrainement_log.csv` et émet un `::warning::` si `,True`, **sans** déclencher de déploiement.
9. **Publication des artefacts** (`:123-132`) : checkpoint + rapport JSON, `if: always()`,
   rétention 14 jours.

L'en-tête du workflow est explicite et honnête (`:6-11`) : ce pipeline « ne produit PAS un modèle
utilisable et ne vérifie AUCUN seuil de performance » — c'est un **smoke-test de la chaîne
technique** sur 32 images (4 classes × 8) et 2 epochs, pas une évaluation représentative. MLflow
n'est pas utilisé (le rapport est un JSON, comme partout dans le projet).

### `cd-model.yml` — le non-déploiement automatique assumé

Déclencheurs (`cd-model.yml:19-33`) : push sur `develop` touchant `models/**.pt`, **ou**
`workflow_dispatch` avec un input `dry_run` **par défaut à `true`**. Le job (7 étapes) vérifie la
présence du `.pt` attendu (`:54-66`), configure l'accès SSH via `webfactory/ssh-agent`
(`:70-73`, clé en secret jamais loguée), teste la connexion (`:86-91`), puis — **seulement hors
dry-run** — copie le `.pt` sur le VPS et met à jour un lien symbolique stable
`mobilenetv2_current.pt` (`:99-110`) avant de redémarrer le conteneur API (`:123-137`).

Deux **choix assumés** sont documentés dans le code et cruciaux à défendre :

- **`models/` est gitignoré**, donc le déclencheur `push … paths: models/**.pt` ne s'arme pas
  tant qu'un `.pt` n'est pas ajouté au dépôt avec `git add -f` (décision laissée à l'humain,
  `cd-model.yml:12-15`). Le chemin nominal reste donc `workflow_dispatch`.
- **Pas de déploiement automatique piloté par l'accuracy CI** (`ci-model.yml:90-105`). Le
  commentaire explique qu'un pipeline sur 32 images en 2 epochs a mesuré ~20 % d'accuracy sur un
  run de vérification, chiffre sans rapport avec les ~93,5 % du modèle réel : brancher un
  déploiement dessus serait absurde. Un vrai déploiement automatique devrait d'abord passer par
  une évaluation sur le dataset complet et **une revue humaine** avant tout redémarrage en
  production. Le `dry_run: true` par défaut matérialise ce principe de prudence.

### L'orchestrateur `ci_entrainement_evaluation.py`

`scripts/ci_entrainement_evaluation.py` (103 lignes) enchaîne le pipeline en trois étapes
(`:53-96`) : (1) chargement + préparation des données (`charger_dataset`), (2) entraînement réel
(`entrainer_modele`), (3) évaluation sur le jeu de test (`charger_checkpoint`,
`executer_inference`, `generer_rapport`), puis vérification du seuil de ré-entraînement. Point de
rigueur : l'accuracy et les classes sous-performantes sont **relues depuis le rapport JSON tout
juste écrit** (`:91-94`) plutôt que recalculées, pour ne jamais diverger des valeurs consignées.
Le script n'utilise **que** les vraies fonctions de `train.py`/`evaluate.py` (aucun mock),
contrairement aux tests unitaires — c'est ce qui prouve que la chaîne complète tourne réellement.

### Traçabilité et migrations

- **Mini-dataset versionné.** `tests/fixtures/mini_dataset/` contient **32 images réelles** (4
  classes `Tomato_*`, 8 images chacune) committées dans le dépôt — le pipeline CI est donc
  reproductible sans le dataset PlantVillage complet (~2 Go, absent du dépôt). Le déterminisme du
  split est assuré par `random_state=42` (`preprocess.py:132/140`).
- **Migrations Alembic.** La chaîne applicative applique et vérifie les migrations à chaque run :
  `ci-app.yml:157-158` exécute `uv run alembic upgrade head` contre un **PostgreSQL réel** avant
  `pytest`, ce qui garantit que les migrations s'appliquent bien sur une vraie base (pas seulement
  sur SQLite en mémoire). C'est la brique de traçabilité du schéma de données.
- **Sources versionnées.** `git ls-files` suit `ci-model.yml`, `cd-model.yml`,
  `scripts/ci_entrainement_evaluation.py`, `docs/ci_cd_modele.md` et le mini-dataset.

### Limite honnête

L'orchestrateur s'exécute de bout en bout localement, mais **un run réel sur la plateforme GitHub
Actions n'est pas vérifiable dans cet environnement** (`gh` indisponible ici). C'est le seul point
de C13 qui exige une preuve externe — d'où la capture demandée ci-dessous.

| # | Critère | Statut | Preuve (fichier:ligne / commande) |
|---|---|---|---|
| 1 | Documentation couvre étapes, tâches, déclencheurs | ✅ | `docs/ci_cd_modele.md` (2 workflows, déclencheurs, étapes numérotées, angles morts explicités) |
| 2 | Déclencheurs intégrés comme définis | ✅ | `ci-model.yml:19-23` (push `feature/model-*` + `workflow_dispatch`) ; `cd-model.yml:19-33` (push `develop` `models/**.pt` + `workflow_dispatch` `dry_run` défaut `true`) |
| 3 | Config reconnue et exécutée selon les déclencheurs | ⚠️/⬜ | YAML valides ; orchestrateur exécutable de bout en bout. Run GitHub Actions réel non vérifiable (`gh` absent). **Action : capture de l'onglet Actions.** |
| 4 | Étape de test des données intégrée, sans erreur | ✅ | `ci-model.yml:76-77` `pytest test_donnees.py test_preprocessing.py` (8 tests) |
| 5 | Étapes test / entraînement / validation intégrées | ✅ | `ci-model.yml:87-88` → `ci_entrainement_evaluation.py` (vraies fonctions, aucun mock) |
| 6 | Sources de la chaîne versionnées | ✅ | `git ls-files` (workflows, script, `mini_dataset` 32 images) |
| 7 | Documentation installation / configuration / test | ✅ | `ci_cd_modele.md` (repro locale, secrets `VPS_SSH_PRIVATE_KEY`/`VPS_HOST`…, déclenchement manuel) |
| 8 | Documentation accessible | ✅ | `ci_cd_modele.md` note d'accessibilité ; structure vérifiée |

**C13 : 7/8 critères prouvés, 1 non vérifiable ici (run GitHub Actions réel, `gh` indisponible) — compétence acquise sous réserve de la capture de run.**

`[CAPTURE À INSÉRER — onglet « Actions » GitHub : historique des runs de `ci-model.yml` (entraînement + évaluation) et `cd-model.yml` (déploiement), montrant au moins un run reconnu et exécuté par la plateforme]`

---

## Grille de correspondance au référentiel

Renvoi synthétique de chaque critère à sa preuve (détail et statut dans les tableaux ci-dessus).

### C9 — API REST exposant le modèle
| Critère | Où est la preuve |
|---|---|
| Auth restreint l'accès | `routes/predict.py:74-78` + `core/security.py:66-94` ; `test_security_edge.py` |
| Fonctions du modèle exposées | `predict.py:74`, `model_service.py`, `reports.py` ; `test_predict.py` |
| OWASP top 10 (2023) | `core/owasp.md` (API1/2/4/5/8) ; `test_security.py` |
| Sources versionnées | `git remote -v` ; HEAD poussé sur origin |
| Tests couvrent tous les endpoints | 12 opérations, `tests/test_api/` → 44 |
| Tests sans bug | `pytest tests/test_api/` → 44 passed |
| Résultats interprétés | `docs/tests.md:22-38` |
| Doc architecture + endpoints | `docs/architecture.md` + OpenAPI `/docs` |
| Doc auth/autorisation | `main.py:145-162`, `owasp.md` API2/5 |
| Standard OpenAPI | `app.openapi()` → 3.1.0 ; `main.py:196-210` |
| Doc accessible | `architecture.md` (note d'accessibilité) |

### C10 — Intégration de l'API dans l'application
| Critère | Où est la preuve |
|---|---|
| App de départ fonctionnelle | `.env.example`, `app.py:22/205` |
| Communication API | `api_client.py:126` ; `tests/test_frontend/` → 41 |
| Auth + renouvellement | `api_client.py:298/318/265` ; `test_auth.py::test_refresh_token_expire` |
| Tous les endpoints intégrés | `api_client.py` (12 opérations, tableau endpoint→fonction→page) |
| Adaptations d'interface | `dashboard.py:128/163/257` ; `fr_label` + `html.escape` ; compression `predict.py:46-91` |
| Tests d'intégration | `test_api_client.py` + `test_gestion_401.py` + `test_navigation_role.py` + `test_regression_base64url.py` |
| Tests sans bug | `pytest tests/test_frontend/` → 41 passed |
| Résultats interprétés | `test_api_client.py` (Bearer exact, `0.9355`, octets PNG, multipart `fichier`) |
| Sources versionnées | `git ls-files` (client, tests, `.env.example`) |

### C11 — Monitoring du modèle
| Critère | Où est la preuve |
|---|---|
| Métriques expliquées | `docs/monitoring.md:33-54` ; `metrics.py:18-20` |
| Outils adaptés | `monitoring.md:56-93` ; `prometheus.yml` |
| Restitution temps réel | `tomatoscan.json` (7 panneaux, `refresh: 30s`) |
| Accessibilité de l'outil ⚠️ | `monitoring.md` (audit WCAG Grafana non mené) |
| Bac à sable | `monitoring.md` ; bug d'alerte corrigé (`alertes.yml:15-22`) ; `docker-compose.local.yml` |
| Chaîne en marche | `routes/predict.py` (4 métriques) ; `main.py:268` ; `test_metrics.py` |
| Sources versionnées | `git ls-files monitoring/` ; secrets via `GF_SMTP_*` |
| Doc install/config/usage | `monitoring.md` |
| Doc accessible | `monitoring.md` (note d'accessibilité) |
| Déclencheur ré-entraînement | `evaluate.py:27/33/232-242` ; `ci-model.yml:106-118` |

### C12 — Tests automatisés du modèle
| Critère | Où est la preuve |
|---|---|
| Cas listés/définis | `docs/tests.md:181-215` + docstrings d'en-tête |
| Outils cohérents | `tests.md:68-77` ; `torch`, `PIL`, `unittest.mock` |
| Couverture établie | `--cov-fail-under=80` → 85,07 % ; `ci-app.yml:175` |
| Exécution/idempotence/familles | `pytest tests/test_model` → 25 passed ; nominal/erreur/limite |
| Sources versionnées | `git ls-files tests/test_model/` |
| Doc install/exécution/couverture | `tests.md:59-112` (décomptes corrigés 112/25) |
| Doc accessible | `tests.md:265` |

### C13 — Livraison continue du modèle (MLOps)
| Critère | Où est la preuve |
|---|---|
| Doc étapes/tâches/déclencheurs | `docs/ci_cd_modele.md` |
| Déclencheurs intégrés | `ci-model.yml:19-23`, `cd-model.yml:19-33` |
| Config exécutée ⚠️/⬜ | `ci_entrainement_evaluation.py` ; run GitHub Actions à capturer |
| Test des données | `ci-model.yml:76-77` (8 tests) |
| Test/entraînement/validation | `ci-model.yml:87-88` ; vraies fonctions, aucun mock |
| Sources versionnées | `git ls-files` (workflows, script, fixtures) |
| Doc install/config/test | `ci_cd_modele.md` |
| Doc accessible | `ci_cd_modele.md` (note d'accessibilité) |

---

## Synthèse et verdict

| Compétence | Verdict | Critères prouvés | Points à consolider |
|---|---|---|---|
| **C9** | ✅ Pleinement acquise | 11/11 | — |
| **C10** | ✅ Pleinement acquise | 9/9 | — |
| **C11** | ✅ Acquise | 9/10 | ⚠️ accessibilité Grafana non auditée (défendable à l'oral, public admin-only) |
| **C12** | ✅ Acquise | 7/7 | ⚠️ ajouter une ligne au tableau « Modèle » de `docs/tests.md` (24 → 25 lignes) |
| **C13** | ✅ Acquise | 7/8 | ⬜ fournir la preuve d'un run GitHub Actions réel (`gh` indisponible ici) |

Les cinq compétences sont acquises. Les points restants sont tous documentés honnêtement et
défendables : ils relèvent d'une consolidation (une ligne de doc, une capture) ou d'une limite
assumée (audit d'accessibilité de l'outil), pas d'un manque de fond. La cohérence des chiffres a
été vérifiée transversalement : **112 tests** (44 API / 25 modèle / 41 frontend / 2 BDD),
**85,07 %** de couverture modèle, **accuracy de test 0,9355**, **4 métriques**, **7 panneaux
Grafana** — aucune de ces valeurs ne contredit une autre dans le document.

### À faire manuellement par le candidat avant le 31 juillet 2026

1. **Compléter `docs/tests.md`** (C12) : la table du § « Modèle » énumère 24 lignes alors que le
   décompte annoncé est 25 ; ajouter la ligne
   `test_afficher_confusion_matrix_avec_chemin_sortie_sauvegarde_un_fichier`.
2. **Insérer les captures d'écran** marquées `[CAPTURE À INSÉRER]` :
   - Swagger UI `/docs` (chemins par tags) — C9
   - Page « Analyse » avec résultat + confiance — C10
   - Dashboard Grafana « TomatoScan » (7 panneaux, données réelles) — C11
   - Sortie couverture `pytest tests/test_model … 85,07 %` — C12
   - Onglet Actions GitHub : runs `ci-model.yml` / `cd-model.yml` — C13
3. **Consolider C11.4** : consigner un contrôle d'accessibilité rapide de Grafana (thème
   sombre/clair, navigation clavier, contraste des panneaux) ou assumer explicitement à l'oral le
   public admin-only.
4. **Consolider C13.3** : joindre `gh run list --workflow=ci-model.yml` (ou une capture Actions)
   attestant qu'au moins un run a été reconnu et exécuté par la plateforme.
5. Optionnel : merger le HEAD sur `origin/develop` distant pour clarifier le versionnement (C9.4).

---

*Rapport établi le 20 juillet 2026 par vérification directe : fichiers relus, commandes réellement
exécutées (`pytest --collect-only` → 112 tests ; couverture modèle → 85,07 % ; 25 tests modèle
passés), aucun chiffre supposé. Aucun commit ni push n'a été effectué lors de cette rédaction.*
