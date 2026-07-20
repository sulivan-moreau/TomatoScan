# Incidents — TomatoScan

Bugs réels rencontrés et corrigés sur le projet, présentés ici pour la
compétence **C21** (identifier, analyser et corriger un dysfonctionnement) du
référentiel DevIA Simplon.

Chaque incident est tracé par son numéro de **pull request** et ses commits
réels (branche `fix/*`, commit de correction, commit de merge). Les commits de
correction du projet ne portent pas de numéro d'*issue* GitHub — voir la note de
traçabilité en fin de document.

---

## Incident 1 — Rôle admin dégradé en agriculteur : décodage JWT base64 vs base64url

**PR #84** — branche `fix/role-login-decodage` — commit `da4f786` — merge `8c21745`.

### Symptôme

Découvert par moi-même en préproduction (VPS Coolify) : mon compte **admin** se
faisait *parfois* traiter comme un simple agriculteur — pages d'administration
(`/dashboard`, `/creer_membre`) refusées avec « Accès réservé aux
administrateurs », ou session brutalement invalidée alors que je venais de me
connecter. **Intermittent, non systématique** : selon le token, tout
fonctionnait ou l'admin était dégradé, sans action reproductible évidente.

### Reproduction en développement

Le front lit le rôle et l'expiration en décodant *localement* la payload du JWT
(`_decoder_payload_token` dans `src/tomatoscan/front/utils/api_client.py`). J'ai
forgé des JWT et cherché lesquels cassaient le décodage. Verdict : seuls
échouaient les tokens dont la payload **encodée** contient `-` ou `_`.

```bash
uv run python -c "
import base64, json, jwt
# Payload dont l'encodage base64url contient - et _ (username avec ~ et ?)
p = {'sub': '~ferme?', 'role': 'admin', 'exp': 9_999_999_999}
seg = jwt.encode(p, 'cle', algorithm='HS256').split('.')[1]
print('segment      :', seg)                 # ...J-ZmVybWU_Ii...
print('contient - ? ', '-' in seg, '| _ ?', '_' in seg)   # True | True
seg += '=' * (4 - len(seg) % 4)
# Ancien décodage (base64 STANDARD) — ce que faisait le code avant correction :
try:
    print('base64 standard :', json.loads(base64.b64decode(seg)))
except Exception as e:
    print('base64 standard : LEVE', type(e).__name__)      # UnicodeDecodeError
# Décodage corrigé (base64url) :
print('base64url       :', json.loads(base64.urlsafe_b64decode(seg)))  # OK
"
```

Sortie réelle : `base64 standard` lève `UnicodeDecodeError`, `base64url` décode
correctement `{'sub': '~ferme?', 'role': 'admin', 'exp': 9999999999}`. Un
username purement alphanumérique (`admin`, `agri01`…), lui, produit un encodage
sans `-`/`_` et passe dans les deux cas — d'où l'aspect intermittent.

### Diagnostic

C'est l'étape qui manquait à l'analyse initiale : passer du « ça arrive parfois »
à la cause exacte.

- L'alphabet **base64url** (RFC 7519, celui des JWT) ne diffère de l'alphabet
  **base64 standard** que sur deux valeurs : 62 (`-` au lieu de `+`) et 63 (`_`
  au lieu de `/`). Tant que la payload n'encode aucune de ces deux valeurs, les
  deux alphabets produisent la **même** chaîne et le bug reste invisible.
- Produire un `-`/`_` exige un groupe de 6 bits valant 62 ou 63, soit 6 bits à 1
  consécutifs. Or tout octet ASCII a son bit de poids fort à 0, ce qui empêche
  une telle séquence de traverser une frontière d'octet : seuls `?` (0x3F) et
  `~` (0x7E) parmi les caractères ASCII imprimables la portent. Un `sub`
  alphanumérique classique ne peut donc jamais déclencher le bug — mesuré : **0
  déclenchement sur 700 000+ tokens** `{sub, role, exp}` à username normal.
- `base64.b64decode(..., validate=False)` (le défaut) **écarte silencieusement**
  les caractères hors alphabet standard. Quand la payload contenait `-`/`_`, ces
  caractères étaient supprimés, décalant tout le flux d'octets : le décodage
  levait une exception (ou renvoyait des octets corrompus). En aval,
  `is_token_valid` jugeait alors le token invalide (→ admin déconnecté) et
  `obtenir_role` retombait sur son défaut `"agriculteur"` (→ admin dégradé).

### Cause racine

`_decoder_payload_token` décodait la payload avec `base64.b64decode` (alphabet
standard `+/`) au lieu de `base64.urlsafe_b64decode` (alphabet base64url `-_`
imposé par les JWT). Le rôle et l'expiration étaient donc lus faux dès qu'un
token s'encodait avec `-` ou `_`.

### Correction

Diff réel du commit `da4f786` (`src/tomatoscan/front/utils/api_client.py`) :

```diff
-    return json.loads(base64.b64decode(partie_payload))
+    return json.loads(base64.urlsafe_b64decode(partie_payload))
```

La même PR ajoute un log explicite dans les `except` de `is_token_valid` et
`obtenir_role`, pour qu'un futur échec de décodage ne soit plus silencieux.

Renforcement ultérieur (**PR #87**, branche `fix/jwt-pyjwt-decode`, commit
`b54540a`, merge `9e3cba5`) : le décodage manuel a été entièrement délégué à
**PyJWT**, qui gère nativement base64url et le padding. C'est l'implémentation
actuelle, encore plus robuste que `urlsafe_b64decode` :

```python
def _decoder_payload_token(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})
```

### Vérification

Le test de non-régression manquant a été créé :
`tests/test_frontend/test_regression_base64url.py`. Il forge un JWT dont la
payload contient `-` **et** `_`, invoque la vraie fonction du projet, et prouve
que l'ancien décodage (base64 standard) échouait sur cette même payload là où le
correctif réussit. Le test existant `test_api_client.py::test_decode_et_expiration`
ne couvrait pas ce cas (payload alphanumérique sans `-`/`_`).

```
tests/test_frontend/test_regression_base64url.py::...::test_la_vraie_fonction_decode_une_payload_base64url PASSED
tests/test_frontend/test_regression_base64url.py::...::test_l_ancien_decodage_base64_standard_echouait_sur_cette_payload PASSED
5 passed in 0.23s
```

### Prévention / ce que j'en retiens

- Ne jamais décoder « à la main » un format normalisé (JWT) quand une lib le
  fait correctement : d'où le passage à PyJWT.
- Un bug « intermittent » cache presque toujours une variable cachée — ici, le
  contenu binaire encodé du token. Le rendre reproductible (forger l'entrée qui
  déclenche) a été le vrai déblocage.
- Un `except` qui masque l'échec transforme un bug en comportement dégradé
  silencieux : les échecs de décodage sont désormais loggués.

### Durcissement défensif associé (PR #94) — *pas la cause du symptôme ci-dessus*

Séparément, `obtenir_role_courant` (côté API, `security.py`) faisait un
*fail-open* : `charge.get("role", "agriculteur")`. Corrigé en **PR #94** (commit
`513cfc2`, merge `68d8358`) pour lever un 401 explicite si le claim `role` est
absent. **Ce n'est pas** l'origine du symptôme intermittent de préproduction :
`créer_token_acces()` inclut toujours le claim `role`, donc ce cas ne se produit
pas en usage normal — c'est un durcissement *fail-closed* de défense en
profondeur, non intermittent, documenté ici honnêtement comme tel et non comme
la résolution de l'incident 1.

---

## Incident 2 — Frontend démarrait avant une API prête : healthcheck trop court pour PostgreSQL

**PR #92** — branche `fix/healthcheck-api-postgresql` — commit `b48cf4c` — merge `cb88775`.

- **Symptôme** — En préproduction, le frontend (`depends_on: api condition:
  service_healthy`) démarrait alors que l'API n'était pas encore prête, ou l'API
  était marquée `unhealthy` puis redémarrée en boucle au premier déploiement.
- **Diagnostic** — Le passage de SQLite à PostgreSQL asynchrone a allongé le
  démarrage de l'API : le *lifespan* attend d'abord `postgres` (`service_healthy`),
  puis fait des allers-retours réseau réels (`create_all` + bootstrap admin) avant
  de charger le modèle MobileNetV2. L'ancien budget de healthcheck (`start_period:
  20s`, `retries: 3`) ne couvrait plus ce chemin.
- **Cause racine** — Healthcheck calibré pour l'ancien démarrage (SQLite, quasi
  instantané), pas pour le démarrage PostgreSQL async plus long.
- **Correction** (`docker-compose.yml`) :

  ```diff
  -      retries: 3
  -      start_period: 20s
  +      retries: 5
  +      start_period: 60s
  ```
- **Vérification** — Déploiement Coolify : l'API atteint l'état `healthy` avant
  expiration, le frontend ne démarre plus prématurément.
- **Prévention** — Recalibrer les healthchecks à chaque changement de dépendance
  de démarrage (ici la base de données), pas seulement au code applicatif.

---

## Incident 3 — Build Docker impossible sur le VPS : torch tirait les wheels CUDA

**PR #68 puis #69** — branche `fix/torch-cpu` — commits `56a18a2` et `4732bbe` — merges `d7db95a` et `d0b49d6`.

- **Symptôme** — Le build de l'image API échouait / explosait en taille sur le
  VPS (machine CPU, sans GPU) : `uv sync` tirait les wheels CUDA/NVIDIA de
  `torch` (~2 Go), inutiles et hors budget disque du runner.
- **Diagnostic** — Par défaut, `torch` s'installe depuis PyPI avec ses
  dépendances CUDA. Sur un VPS CPU, ces paquets sont à la fois inutilisables et
  trop lourds.
- **Cause racine** — Aucune contrainte n'orientait la résolution de `torch` vers
  la variante CPU au build Docker.
- **Correction (en deux temps, d'où deux PR)** :
  - **PR #68** (`56a18a2`) — `Dockerfile.api` installe `torch`/`torchvision`
    depuis l'index CPU **avant** `uv sync`, et `pyproject.toml` ajoute une
    contrainte `torch` (`[tool.uv] constraint-dependencies = ["torch"]`) :

    ```dockerfile
    RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
    ```
  - **PR #69** (`4732bbe`) — régénération de `uv.lock` pour refléter la
    contrainte (`[manifest] constraints = [{ name = "torch" }]`), sans quoi le
    lock restait désaligné du `pyproject.toml`.
- **Vérification** — Build de l'image API sur le VPS sans téléchargement des
  wheels CUDA ; image nettement plus légère.
- **Prévention** — Épingler explicitement la variante CPU des dépendances ML
  lourdes dès qu'un environnement de build ne dispose pas de GPU.

---

## Traçabilité : issues vs pull requests

Vérifié par `git log` : les commits de correction (`fix/*`) de ce projet sont
tracés par leur **numéro de pull request** (via le commit de merge), **pas** par
un numéro d'*issue* GitHub. Aucun des commits d'incident ci-dessus (`da4f786`,
`b48cf4c`, `56a18a2`, `4732bbe`) ne référence d'issue. Les *issues* n'ont été
utilisées que sur les commits de fonctionnalité (`feat:` / `ci:` — ex. issues
#10 à #39). Je le note honnêtement plutôt que d'inventer des liens d'issue
inexistants ; la chaîne branche `fix/*` → commit → PR → merge reste vérifiable
intégralement par `git` pour chaque incident.

---

*Accessibilité : document Markdown structuré par hiérarchie de titres (H1→H3),
lisible par un lecteur d'écran et navigable au clavier depuis GitHub.*
