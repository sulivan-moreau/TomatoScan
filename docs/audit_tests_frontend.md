# Audit indépendant — Tests d'intégration frontend (`api_client.py`)

Audit en lecture seule de `feature/front-tests` : `tests/test_frontend/test_api_client.py` (+ `tests/test_frontend/__init__.py`). Aucun fichier de code n'a été modifié pour produire ce rapport ; toutes les commandes ont été réexécutées indépendamment.

---

## 1. Liste exhaustive des fichiers modifiés/créés

Sortie brute de `git status --porcelain` :

```
 M .gitignore
?? Makefile
?? tests/test_frontend/
```

`.gitignore` et `Makefile` sont hérités de sessions antérieures, sans rapport avec cette brique (déjà signalé dans les deux audits précédents). `tests/test_frontend/` est nouveau et contient `__init__.py` (vide, marqueur de package, cohérent avec `tests/test_api/__init__.py` et `tests/test_model/__init__.py`) et `test_api_client.py` (13 tests).

---

## 2. Confirmation de non-régression — **OK**

```
$ git diff src/tomatoscan/front/utils/api_client.py | wc -l
0
$ git diff src/tomatoscan/front/pages/predict.py | wc -l
0
$ git diff tests/test_api/ | wc -l
0
$ git diff tests/test_model/ | wc -l
0
```

Les 4 diffs demandés sont vides — confirmé par exécution, pas par lecture du rapport précédent.

---

## 3. Vérification des 13 tests un par un

| Test | Vérifie réellement | Conforme au nom ? |
|---|---|---|
| `test_login_extrait_bien_le_token_de_la_reponse_200` | `token == "faux.jwt.token"` sur une réponse 200 mockée | Oui |
| `test_login_envoie_bien_les_identifiants_au_bon_endpoint` | URL exacte (`{API_URL}/auth/token`) + payload JSON exact | Oui |
| `test_login_identifiants_invalides_leve_apierror_401` | `ApiError` levée, `status_code == 401` | Oui |
| `test_login_reponse_sans_token_leve_apierror` | `ApiError` levée si `access_token` absent du corps 200 | Oui, mais docstring légèrement trompeur — voir §4 |
| `test_predict_envoie_le_header_authorization_correct` | Égalité stricte du dict `headers` (pas juste présence) | Oui — voir §5, confirmé exact |
| `test_predict_envoie_le_fichier_dans_le_bon_champ_multipart` | Nom de champ `"fichier"` + contenu du tuple (nom, octets, content-type) | Oui — voir §5, cohérence bout-en-bout confirmée |
| `test_predict_reponse_200_retourne_le_format_attendu_par_la_page` | Égalité complète du dict retourné + 3 lectures `.get()` individuelles | Oui |
| `test_predict_reponse_tomate_saine_est_distinguee_par_la_page` | `resultat["classe"] == "Tomato_healthy"` | Le nom dit "est distinguée" — mais le test vérifie seulement que la valeur `"Tomato_healthy"` traverse intacte jusqu'au dict retourné, pas que `pages/predict.py:86` fait effectivement la distinction (impossible à tester sans Streamlit réel, comme le docstring l'assume correctement). Le nom surpromet légèrement : "distinguée" suggère que le branchement lui-même est vérifié, alors que seule sa précondition l'est. Le docstring, lui, est honnête sur cette limite. |
| `test_calcul_pourcentage_confiance_logique_de_predict_py` | Reproduction de la logique de `predict.py:81-84` sur 5 valeurs connues | Oui — voir §4, reproduction vérifiée fidèle |
| `test_predict_401_leve_apierror_avec_le_bon_status_code` | `ApiError`, `status_code == 401` | Oui |
| `test_predict_401_le_message_d_erreur_reprend_le_detail_de_l_api` | `"Token invalide ou expiré" in str(erreur.value)` | Oui |
| `test_predict_401_ne_retourne_jamais_de_dict_ni_none` | `pytest.fail()` explicite si `predict()` retourne au lieu de lever | Oui — pattern `try/except` plutôt que `pytest.raises()` (fonctionnellement correct mais moins idiomatique ; sans impact) |
| `test_predict_erreur_reseau_leve_aussi_apierror` | `ApiError(status_code=None)` sur `requests.ConnectionError` | Oui |

**Aucun test ne triche sur son nom au sens strict.** Un seul écart réel trouvé : le nom de `test_predict_reponse_tomate_saine_est_distinguee_par_la_page` suggère que le branchement d'affichage est vérifié, alors que seule la donnée qui l'alimente l'est — nuance mineure, cohérente avec la limite assumée et documentée ailleurs dans le fichier (page Streamlit non testable sans navigateur).

---

## 4. Vérification des affirmations du rapport précédent

### Lectures `.get()` dans `predict.py` — **CONFIRMÉ, citation à préciser**

Relu directement (`cat -n`), pas fait confiance au rapport :

```
80        classe = resultat.get("classe")
81        confiance = resultat.get("confiance", 0) or 0
82        # La confiance peut arriver en 0-1 (proba) ou déjà en pourcentage.
83        pourcent = confiance * 100 if confiance <= 1 else confiance
84        pourcent = max(0.0, min(pourcent, 100.0))
...
114       message = resultat.get("message")
```

Les 3 lectures existent bien : `classe` (ligne 80), `confiance` (ligne 81), `message` (ligne 114). Le test cite "predict.py:80-82,114" — la ligne 82 est en réalité un **commentaire**, pas une lecture `.get()`. Imprécision de citation mineure (la plage inclut une ligne de commentaire), le fond (3 lectures, 3 clés attendues) reste exact.

### Reproduction de la logique de pourcentage — **CONFIRMÉ fidèle, ligne par ligne**

Code réel (lignes 81, 83, 84 — la ligne 82 est le commentaire déjà signalé) :
```python
confiance = resultat.get("confiance", 0) or 0
pourcent = confiance * 100 if confiance <= 1 else confiance
pourcent = max(0.0, min(pourcent, 100.0))
```

Code dupliqué dans le test :
```python
confiance = confiance or 0
pourcent = confiance * 100 if confiance <= 1 else confiance
return max(0.0, min(pourcent, 100.0))
```

**Aucune divergence** entre les deux : la seule différence est que le test prend `confiance` déjà extraite en paramètre (il ne duplique pas `resultat.get("confiance", 0)`, seulement le traitement numérique qui suit) — un choix de portée cohérent avec l'objectif du test (tester la transformation, pas l'extraction déjà couverte ailleurs), pas un bug de reproduction. Vérifié indépendamment sur les 5 cas testés :

| Entrée | Attendu | Recalculé indépendamment |
|---|---|---|
| 0.973 | 97.3 | 0.973×100 = 97.3 ✓ |
| 0.0 | 0.0 | `0 or 0` = 0, 0≤1 → 0×100=0 ✓ |
| None | 0.0 | `None or 0` = 0 → 0 ✓ |
| 1.0 | 100.0 | 1.0≤1 → 100.0 ✓ |
| 150.0 | 100.0 | 150.0>1 → pourcent=150.0, clampé à 100.0 ✓ |

### `ApiError(status_code=401)` — **CONFIRMÉ réel, pas supposé**

Reproduit indépendamment à l'instant :
```
$ uv run pytest tests/test_frontend/test_api_client.py::TestPredictErreur -v
test_predict_401_leve_apierror_avec_le_bon_status_code PASSED
test_predict_401_le_message_d_erreur_reprend_le_detail_de_l_api PASSED
test_predict_401_ne_retourne_jamais_de_dict_ni_none PASSED
test_predict_erreur_reseau_leve_aussi_apierror PASSED
```
Tracé dans le code réel de `predict()` : `if not reponse.ok: ... raise ApiError(detail, status_code=reponse.status_code)` — le chemin emprunté pour un 401 mocké (`ok=False` car `401 < 400` est faux) est bien celui-ci, pas un chemin différent supposé par erreur.

Aucun test ne masque un retour `None`/dict silencieux : `test_predict_401_ne_retourne_jamais_de_dict_ni_none` échoue explicitement via `pytest.fail()` si `predict()` retournait quoi que ce soit au lieu de lever — testé et confirmé fonctionnel.

---

## 5. Vérification de l'authentification et du multipart — **OK**

**Header Authorization** : `test_predict_envoie_le_header_authorization_correct` fait `assert kwargs["headers"] == {"Authorization": "Bearer mon.token.valide"}` — une **égalité stricte de dict**, pas une vérification de présence de clé (`"Authorization" in kwargs["headers"]` aurait été plus faible). Confirmé exact.

**Champ multipart** : le test vérifie `"fichier" in kwargs["files"]`. Comparé au code serveur réel :
```
src/tomatoscan/api/routes/predict.py:58:    fichier: UploadFile = File(...),
```
Le paramètre FastAPI s'appelle littéralement `fichier` — cohérence bout-en-bout confirmée entre le nom de champ envoyé par le client et celui attendu par la route API réelle, pas une coïncidence de nommage supposée.

---

## 6. Suite complète

```
$ uv run pytest tests/ -v
[...]
90 passed, 26 warnings in 7.29s
```

**90 tests, pas 88.** Écart expliqué : `uv run pytest tests/` (le dossier complet) inclut aussi `tests/test_database/` (2 tests, `test_modeles.py`), présent depuis le commit `a9a5d57` (bien antérieur à cette session, sans rapport avec les rôles/tests modèle/tests frontend). Vérifié : `git diff tests/test_database/` est vide (non touché). Répartition exacte :

| Dossier | Tests |
|---|---|
| `tests/test_api/` | 31 |
| `tests/test_model/` | 44 |
| `tests/test_frontend/` | 13 |
| `tests/test_database/` | 2 |
| **Total** | **90** |

Le "88" du rapport précédent correspondait à `test_api + test_model + test_frontend` uniquement (31+44+13=88) — chiffre correct dans son périmètre, mais `test_database/` n'entre pas dans ce périmètre alors que la commande demandée ici (`pytest tests/ -v`, sans filtre) l'inclut nécessairement. Ce n'est pas une régression ni un problème : les 90 tests passent, 0 échec.

---

## Synthèse

| Section | Verdict |
|---|---|
| 1. Fichiers modifiés | OK |
| 2. Non-régression | OK — 4 diffs vides confirmés |
| 3. Tests un par un | OK — aucune triche sur les noms ; 1 nom légèrement surpromettant (`..._est_distinguee_par_la_page`), 1 docstring imprécis (mention KeyError alors que le code utilise déjà `.get()`) |
| 4. Affirmations du rapport précédent | CONFIRMÉES — citations de lignes légèrement imprécises (incluent une ligne de commentaire) mais fond exact |
| 5. Authentification/multipart | OK — vérifications par égalité stricte, cohérence bout-en-bout avec l'API confirmée par lecture du code serveur |
| 6. Suite complète | OK — 90/90 passent (88 dans le périmètre de cette session + 2 dans `test_database/`, préexistant et non lié) |

### Verdict global : **PRÊT À COMMITTER**

Aucun point bloquant. Deux imprécisions cosmétiques relevées (un nom de test légèrement surpromettant, une citation de ligne incluant un commentaire) — ni l'une ni l'autre n'affecte la validité de ce qui est réellement testé. Le chiffre "88 attendus" du prompt d'audit ne correspond pas au résultat de la commande demandée telle quelle (`pytest tests/ -v` → 90), mais l'écart est entièrement expliqué par `tests/test_database/`, préexistant et hors périmètre — aucune action requise avant commit.
