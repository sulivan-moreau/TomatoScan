# Checklist OWASP API Security Top 10 — TomatoScan

Référence : [OWASP API Security Top 10 2023](https://owasp.org/API-Security/)

Numérotation du référentiel 2023 utilisée ici :
API1 BOLA · API2 Broken Authentication · API3 Broken Object Property Level Authorization ·
API4 Unrestricted Resource Consumption · API5 Broken Function Level Authorization ·
API6 Unrestricted Access to Sensitive Business Flows · API7 Server Side Request Forgery ·
API8 Security Misconfiguration · API9 Improper Inventory Management ·
API10 Unsafe Consumption of APIs.

> Une version antérieure de ce document titrait « API7 — Security Misconfiguration » et
> « API8 — Injection » : c'était la numérotation du **Top 10 API 2019**, incohérente avec
> le référentiel 2023 cité ci-dessus. Corrigée ci-dessous.

---

## API1 — Broken Object Level Authorization

**Risque :** Un utilisateur accède aux ressources d'un autre utilisateur sans contrôle.

**Mesure appliquée :** L'endpoint `POST /predict` est protégé par un token JWT Bearer.
Toute requête sans token valide reçoit une réponse 401.
`GET /predictions/history` filtre par `user_id` : un agriculteur ne peut lister que
ses propres prédictions, jamais celles d'un autre compte ; seul un admin voit
l'historique complet.

**Fichiers :**
- `src/tomatoscan/api/routes/predict.py` — `Depends(obtenir_utilisateur_courant)`
- `src/tomatoscan/api/routes/history.py` — filtrage `requete.filter_by(user_id=utilisateur.id)` quand `role != "admin"`
- `src/tomatoscan/api/core/security.py` — validation du token JWT

---

## API2 — Broken Authentication

**Risque :** Authentification faible ou tokens sans expiration permettant la prise de compte.

**Mesures appliquées :**
- Tokens JWT avec expiration configurable (`ACCESS_TOKEN_EXPIRE_MINUTES` en `.env`)
- Algorithme HS256 avec `SECRET_KEY` forte stockée en `.env` (jamais en dur) ;
  `creer_token_acces()` lève `RuntimeError` si `SECRET_KEY` est absente, et la
  validation du token échoue en 401 dans le même cas — aucun repli sur une clé par défaut
- Mots de passe stockés hashés avec **bcrypt** (`passlib`), jamais en clair
- Connexion échouée loggée avec `loguru`
- Renouvellement (`POST /auth/refresh`) : exige un token Bearer encore valide au moment
  de l'appel — un token déjà expiré ne peut pas être renouvelé, seule une reconnexion
  complète (`POST /auth/token`) le permet

**Limite assumée :** `POST /auth/token` ne fait pas de comparaison en temps constant
entre un compte inexistant et un mot de passe faux (choix documenté dans `routes/auth.py`) :
un écart de temps de réponse reste théoriquement mesurable. Accepté pour le périmètre
de ce projet.

**Fichiers :**
- `src/tomatoscan/api/core/security.py` — `creer_token_acces()`, `_decoder_charge()`, `hacher_mot_de_passe()`
- `src/tomatoscan/api/routes/auth.py` — `POST /auth/token`, `POST /auth/refresh`
- `.env.example` — `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`

---

## API4 — Unrestricted Resource Consumption

**Risque :** L'API ne limite pas les appels, permettant le brute-force ou le DoS.

**Mesures appliquées :**
- Rate limiting `5 requêtes/minute` par IP sur `POST /auth/token` via `slowapi` (protection contre un débit élevé)
- Blocage après **5 échecs de connexion consécutifs** sur un même compte, indépendamment du débit (protège contre un attaquant qui espace ses tentatives pour rester sous le seuil par IP) — remis à zéro dès une connexion réussie
- Taille maximale des images limitée à **5 Mo** sur `POST /predict`
- Réponse 429 automatique en cas de dépassement (débit ou échecs consécutifs)

**Limite assumée — compteurs en mémoire de processus :**
Les deux protections s'appuient sur un état stocké dans la mémoire du processus API :
- `_echecs_consecutifs: dict[str, int]` (`routes/auth.py`) est un dictionnaire Python ;
- `Limiter(key_func=get_remote_address)` (`core/limiter.py`) est instancié sans
  `storage_uri`, slowapi retombe donc sur son backend par défaut `memory://`.

Conséquences, assumées et non corrigées :
1. **Remise à zéro à chaque redémarrage** du conteneur ou du processus — un attaquant
   qui provoquerait un redémarrage réinitialiserait le compteur d'échecs.
2. **Aucun partage entre workers uvicorn ni entre réplicas** : avec *n* processus,
   le seuil effectif devient *n × 5* puisque chaque processus compte de son côté.
3. Le compteur d'échecs est indexé par nom d'utilisateur et **n'expire pas** tant
   qu'aucune connexion réussie n'a lieu : un attaquant peut verrouiller un compte
   cible en provoquant 5 échecs (déni de service applicatif ciblé), le déblocage
   passant alors par un redémarrage de l'API.

Ce choix reste défendable au vu du déploiement réel : un seul processus uvicorn
(`Dockerfile.api` — `uvicorn ... --host 0.0.0.0 --port 8000`, sans `--workers`) et un
seul réplica par service (`docker-compose.yml`, aucune directive `deploy.replicas`),
donc les points 1 et 2 ne dégradent pas la protection en l'état. Une montée en charge
multi-workers ou multi-réplicas imposerait un backend partagé (Redis) pour slowapi
et pour le compteur d'échecs, ainsi qu'une expiration temporelle du verrou de compte.

**Fichiers :**
- `src/tomatoscan/api/core/limiter.py` — instance `Limiter` slowapi (backend `memory://` par défaut)
- `src/tomatoscan/api/routes/auth.py` — `@limiteur.limit("5/minute")` et `_echecs_consecutifs`
- `src/tomatoscan/api/routes/predict.py` — `TAILLE_MAX_OCTETS = 5 * 1024 * 1024`
- `src/tomatoscan/api/main.py` — `SlowAPIASGIMiddleware`, handler 429

---

## API5 — Broken Function Level Authorization

**Risque :** Une fonction réservée à un rôle privilégié reste accessible à un compte
standard — typiquement une route d'administration protégée seulement par l'absence de
lien dans l'interface, et non par un contrôle serveur.

**Mesures appliquées :**
- Le JWT embarque le rôle de l'utilisateur (`creer_token_acces({"sub": ..., "role": ...})`
  dans `routes/auth.py`) ; le rôle vient de la colonne `role` en BDD, jamais du client.
- `verifier_role_admin()` (`core/security.py`) lève **403** si le rôle du token courant
  n'est pas `"admin"`.
- Cette dépendance est déclarée **au niveau du routeur** `/users`
  (`APIRouter(..., dependencies=[Depends(verifier_role_admin)])`) : elle s'applique donc
  aux trois routes (`GET`, `POST`, `DELETE /users/{user_id}`) sans risque d'oubli sur
  une route ajoutée plus tard.
- `obtenir_role_courant()` rejette en **401** un token dont le claim `role` est absent,
  plutôt que de supposer un rôle par défaut.
- Élévation de privilège fermée par construction : `POST /users` force `role="agriculteur"`
  en dur et ignore toute valeur de rôle envoyée par le client — l'API ne permet pas de
  créer un second compte admin.
- Le compte admin bootstrap (`ADMIN_USERNAME`) et l'auto-suppression sont refusés (400)
  sur `DELETE /users/{user_id}`, pour qu'un admin ne puisse pas rendre le système
  inadministrable.
- Contrôle de rôle également appliqué à la lecture : `GET /predictions/history` ne
  renvoie l'historique global qu'aux admins (cf. API1).

**Fichiers :**
- `src/tomatoscan/api/core/security.py` — `obtenir_role_courant()`, `verifier_role_admin()`
- `src/tomatoscan/api/routes/users.py` — `dependencies=[Depends(verifier_role_admin)]` sur le routeur, `role="agriculteur"` forcé à la création
- `src/tomatoscan/api/routes/auth.py` — rôle inséré dans le JWT à la connexion
- `src/tomatoscan/api/routes/history.py` — historique global réservé au rôle admin

---

## API7 — Server Side Request Forgery

**Statut : non applicable en l'état.**
L'API n'émet aucune requête sortante à partir d'une entrée utilisateur : aucun client
HTTP (`requests`, `httpx`, `aiohttp`, `urllib`) n'est importé dans `src/tomatoscan/api/`.
`POST /predict` reçoit un fichier téléversé, jamais une URL à aller chercher, et
`GET /reports` lit un chemin de fichier local issu de la variable d'environnement
`REPORTS_PATH`, non d'un paramètre de requête. Cette section est conservée pour
expliciter la couverture du référentiel, pas pour documenter une mesure.

---

## API8 — Security Misconfiguration

**Risque :** Configuration par défaut permissive, headers manquants, CORS trop ouvert.

**Mesures appliquées :**
- Headers de sécurité ajoutés sur toutes les réponses via `EnteteSecuriteMiddleware` :
  - `X-Content-Type-Options: nosniff` — bloque le MIME sniffing
  - `X-Frame-Options: DENY` — protège contre le clickjacking
  - `X-XSS-Protection: 1; mode=block` — active le filtre XSS des navigateurs anciens
- CORS restreint aux origines listées dans `CORS_ORIGINS` (`.env`), avec un **garde-fou
  au démarrage** décrit ci-dessous.
- `.env` dans `.gitignore` — secrets jamais commités.

### Garde-fou CORS (défaut corrigé)

`_lire_cors_origins()` lisait auparavant `os.getenv("CORS_ORIGINS", "*")` et le résultat
était passé à `CORSMiddleware` avec `allow_credentials=True` codé en dur. Si la variable
était absente de l'environnement — ce qui était le cas — la configuration réellement
appliquée était donc `allow_origins=["*"]` **avec** credentials : exactement la
misconfiguration que cette section prétendait traiter. Cette combinaison est interdite
par la spécification CORS, et Starlette la contourne en renvoyant l'origine de la requête
telle quelle accompagnée de `Access-Control-Allow-Credentials: true`
(`starlette/middleware/cors.py`, branche `allow_all_origins and allow_credentials`) :
n'importe quelle origine pouvait alors émettre des requêtes authentifiées par cookie.

Comportement actuel de `_lire_cors_origins()` (`src/tomatoscan/api/main.py`) :

| `CORS_ORIGINS` | `APP_ENV` | Résultat |
|---|---|---|
| origines explicites | quelconque | `allow_origins=[…]`, `allow_credentials=True` |
| absente, vide ou `*` | `development` | WARNING loguru + `allow_origins=["*"]`, `allow_credentials=False` (seule forme du joker valide selon la spec) |
| absente, vide ou `*` | ≠ `development` | ERROR loguru + `RuntimeError` — **l'API refuse de démarrer** |

Le joker n'est donc jamais combiné à `allow_credentials=True`, et une configuration
permissive ne peut plus atteindre la préproduction ou la production silencieusement.

**Fichiers :**
- `src/tomatoscan/api/main.py` — `EnteteSecuriteMiddleware`, `_lire_cors_origins()`, `CORSMiddleware`
- `.env.example` — `CORS_ORIGINS`, `APP_ENV`
- `.gitignore` — `.env` exclu

---

## `/metrics` — endpoint Prometheus non authentifié (choix assumé)

`src/tomatoscan/api/main.py` monte l'exporteur Prometheus sans aucune dépendance
d'authentification :

```python
app.mount("/metrics", make_asgi_app())
```

**Choix assumé**, pour trois raisons vérifiables dans le dépôt :

1. **Scraping interne au réseau Docker.** Prometheus cible `api:8000` sur le réseau
   `coolify` (`monitoring/prometheus.yml` — `targets: ['api:8000']`, `metrics_path: /metrics/`),
   c'est-à-dire le nom de service Docker, résolvable uniquement à l'intérieur du réseau.
   Ajouter une authentification imposerait de gérer un secret de scraping côté Prometheus
   pour un gain nul sur ce chemin interne.
2. **Aucune publication de port sur l'hôte.** Le service `api` de `docker-compose.yml`
   ne déclare ni `ports:` ni `expose:` : le conteneur n'est joignable que via le réseau
   `coolify` et le reverse proxy de Coolify.
3. **Aucune donnée personnelle dans les métriques.** Vérifié dans
   `src/tomatoscan/api/metrics.py` — les seuls labels déclarés sont :
   - `predictions_total` → `classe` (nom de classe prédit par le modèle, ensemble fini
     fixé par les `class_names` du checkpoint MobileNetV2) et `statut` (unique valeur
     émise : la chaîne littérale `"succes"`) ;
   - `errors_total` → `type_erreur` (chaînes littérales : `format_invalide`,
     `fichier_trop_lourd`, `modele_indisponible`, `image_corrompue`, `erreur_prediction`) ;
   - `prediction_duration_seconds` et `prediction_confidence` → aucun label.

   Aucun label ne reçoit de valeur contrôlée par l'utilisateur : ni nom d'utilisateur,
   ni adresse IP, ni nom de fichier téléversé (`nom_fichier` est enregistré en BDD,
   jamais en label de métrique). S'y ajoutent les métriques techniques par défaut du
   client Python (`process_*`, `python_*`), qui ne portent pas non plus de donnée
   personnelle. Une exposition de `/metrics` divulguerait donc du volume d'usage et des
   performances du modèle, pas des données à caractère personnel.

**Limite assumée :** l'exposition publique dépend de la configuration Coolify, qui vit
hors du dépôt. Si un nom de domaine est attaché au service `api`, le reverse proxy sert
l'application entière et `/metrics` devient joignable publiquement — le dépôt seul ne
permet pas d'affirmer le contraire. Le risque résiduel reste une fuite d'information
métier (volume de prédictions, taux d'erreur, distribution des confiances), pas de
données personnelles.

**Mesure recommandée en production**, par ordre de préférence :
1. Filtrer `/metrics` au niveau du reverse proxy Coolify/Traefik (règle de refus, ou
   restriction par IP source du conteneur Prometheus) — aucune modification de code.
2. À défaut, exposer l'exporteur sur un port interne distinct, non routé par le proxy.
3. À défaut, protéger le mount par une dépendance FastAPI vérifiant un jeton de scraping
   dédié (`METRICS_TOKEN` en `.env`), à renseigner dans `prometheus.yml`.

**Fichiers :**
- `src/tomatoscan/api/main.py` — `app.mount("/metrics", make_asgi_app())`
- `src/tomatoscan/api/metrics.py` — déclaration des métriques et de leurs labels
- `monitoring/prometheus.yml` — cible de scrape interne `api:8000`
- `docker-compose.yml` — service `api` sans `ports:` publiés

---

## Validation des entrées (Injection — API8:2019, hors Top 10 2023)

L'*Injection* était l'item **API8:2019** du Top 10 API 2019 ; elle ne constitue plus une
catégorie autonome du Top 10 API 2023. Les mesures ci-dessous sont conservées car elles
sont réellement en place, mais elles sont rattachées ici à leur référentiel d'origine
pour ne pas laisser croire à un item 2023 qui n'existe pas.

**Mesures appliquées :**
- Tous les inputs API sont validés par des schémas **Pydantic** (types stricts, champs requis)
- Les fichiers image sont validés par type MIME **et** extension avant traitement
  (`FORMATS_ACCEPTES`, `EXTENSIONS_ACCEPTEES`), puis par la taille du contenu lu
- **Aucune requête SQL n'est construite par concaténation de chaînes.** L'accès aux
  données passe exclusivement par l'ORM SQLAlchemy en mode expression
  (`select(User).filter_by(username=nom_utilisateur)` dans `routes/predict.py`,
  `routes/auth.py`, `routes/users.py`, `routes/history.py`), qui transmet les valeurs
  utilisateur comme **paramètres liés** au driver et non comme fragments de SQL. Aucun
  appel à `session.execute(text(...))` ni à une requête assemblée manuellement n'existe
  dans `src/tomatoscan/api/`.

  > Correction : une version antérieure de ce document affirmait « aucune requête SQL
  > dynamique — pas d'ORM utilisé sur ce chemin de prédiction ». C'était faux :
  > `routes/predict.py` interroge bien la table `users` via l'ORM avant d'enregistrer
  > la prédiction. C'est la justification qui était erronée, pas la mesure : le paramétrage
  > effectué par l'ORM est précisément ce qui protège de l'injection.

- L'image est traitée en mémoire (`io.BytesIO`) sans jamais être écrite sur disque

**Fichiers :**
- `src/tomatoscan/api/schemas/auth.py` — `LoginRequest`, `TokenResponse`, `MeResponse`
- `src/tomatoscan/api/schemas/predict.py` — `PredictionResponse`
- `src/tomatoscan/api/schemas/users.py` — `UserCreate`, `UserOut`
- `src/tomatoscan/api/routes/predict.py` — validation MIME + taille avant traitement

---

## Résumé des contrôles

| Menace OWASP API 2023 | Statut | Mécanisme |
|---|---|---|
| API1 — Broken Object Level Authorization | ✅ | JWT sur `/predict`, historique filtré par `user_id` |
| API2 — Broken Authentication | ✅ | JWT expirable, bcrypt, `SECRET_KEY` en `.env` |
| API3 — Broken Object Property Level Authorization | ➖ | Réponses limitées aux champs des schémas Pydantic (`UserOut` n'expose pas le hash) |
| API4 — Unrestricted Resource Consumption | ✅ ⚠️ | Rate limit 5/min, 5 échecs consécutifs, taille max 5 Mo — compteurs en mémoire de processus (limite documentée) |
| API5 — Broken Function Level Authorization | ✅ | `verifier_role_admin` sur le routeur `/users`, rôle porté par le JWT |
| API6 — Unrestricted Access to Sensitive Business Flows | ➖ | Pas de flux métier sensible (ni paiement, ni réservation) ; `/predict` couvert par API4 |
| API7 — Server Side Request Forgery | ➖ | Aucune requête sortante construite à partir d'une entrée utilisateur |
| API8 — Security Misconfiguration | ✅ | Headers de sécurité, CORS explicite + garde-fou au démarrage |
| API9 — Improper Inventory Management | ➖ | Surface unique et versionnée (OpenAPI généré, une seule version d'API déployée) |
| API10 — Unsafe Consumption of APIs | ➖ | L'API ne consomme aucune API tierce |
| `/metrics` non authentifié | ⚠️ | Choix assumé (scraping interne, aucune donnée personnelle) — restriction proxy recommandée en production |

Légende : ✅ mesure implémentée · ⚠️ limite assumée documentée · ➖ non applicable en l'état.

---

## Chargement du modèle (`torch.load` avec `weights_only=False`)

Le checkpoint MobileNetV2 est chargé avec `torch.load(..., weights_only=False)`
(`src/tomatoscan/api/services/model_service.py`, `src/tomatoscan/model/evaluate.py`) —
nécessaire car le checkpoint contient des objets Python (la liste des noms de classes),
pas uniquement des tenseurs. Ce réglage **désérialise potentiellement du code arbitraire** :
un fichier `.pt` piégé pourrait exécuter du code au chargement.

**Pourquoi c'est acceptable ici :** le `.pt` n'est **jamais** téléchargé depuis une source
externe. Il provient exclusivement de notre propre pipeline d'entraînement (`train.py`) et
est déposé sur le volume du VPS via `cd-model.yml` (accès SSH authentifié) : la source est
de confiance, aucun canal ne permet à un attaquant de fournir un checkpoint arbitraire. Si le
modèle venait un jour d'un tiers, il faudrait repasser à `weights_only=True` (chargement du
seul `state_dict`) ou vérifier une somme de contrôle signée avant chargement.
</content>
