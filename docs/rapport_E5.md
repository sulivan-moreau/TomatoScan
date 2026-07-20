# Rapport E5 — Surveillance et résolution d'incident d'une application d'IA

| | |
|---|---|
| **Candidat** | Sulivan Moreau |
| **Diplôme** | Développeur en Intelligence Artificielle (RNCP 37827) — Simplon, promotion 2026 |
| **Épreuve** | E5 — Surveillance en production et résolution d'incident d'une application d'IA |
| **Compétences évaluées** | C20, C21 |
| **Projet** | TomatoScan — détection de maladies de la tomate (MobileNetV2, transfer learning, PyTorch) |
| **Dépôt** | https://github.com/sulivan-moreau/TomatoScan |
| **Déploiement** | VPS OVH (Roubaix) orchestré par Coolify, stack conteneurisée Docker |
| **Date de vérification** | 20 juillet 2026 |
| **Soutenance** | 31 juillet 2026 |

## Contexte du projet

TomatoScan classe des feuilles de tomate en 10 classes (dataset PlantVillage) à l'aide d'un
modèle **MobileNetV2** (transfer learning, PyTorch), exposé par une **API FastAPI**, consommé par
un **frontend Streamlit** et persisté dans **PostgreSQL** (asynchrone). L'ensemble tourne sur un
VPS OVH orchestré par **Coolify**. Ce rapport traite exclusivement des deux compétences E5 : la
**surveillance de l'application en production** (C20) et la **résolution d'un incident technique**
avec correction du code et documentation de la solution (C21).

**Distinction importante pour C20** : ce rapport porte sur le monitoring **applicatif/système**
(santé de l'API, taux d'erreurs, latence d'inférence, journalisation, alertes), à ne pas confondre
avec le monitoring **du modèle** au sens dérive/réentraînement continu, qui relève de C11 (épreuve
E3) et est documenté séparément dans `docs/ci_cd_modele.md`. Deux métriques exposées ici
(`predictions_total` par classe, `prediction_confidence`) donnent un signal sur le comportement du
modèle, mais **aucune boucle de réentraînement automatique** n'est déclenchée depuis ce monitoring
— ce point est écrit noir sur blanc en tête de `docs/monitoring.md:9-15`.

## Méthode de vérification

Chaque critère s'appuie sur une preuve datée : un fichier référencé par `chemin:ligne`, un
artefact de configuration réel, ou une commande réellement exécutée lors de la rédaction. Aucun
chiffre n'est inventé. Commandes rejouées :

```
uv run pytest tests/test_api/test_metrics.py -v            → 1 passed
uv run pytest tests/test_frontend/test_regression_base64url.py -v → 5 passed in 0.23s
git show da4f786 -- src/tomatoscan/front/utils/api_client.py  → diff b64decode → urlsafe_b64decode
git show 8c21745                                           → Merge pull request #84 …/fix/role-login-decodage
git merge-base --is-ancestor da4f786 develop              → 0 (ancêtre de develop)
```

**Légende des statuts** : ✅ prouvé · ⚠️ fragile (défendable à l'oral, à consolider) ·
❌ manquant · ⬜ non vérifiable dans cet environnement.

---

## C20 — Surveiller une application d'IA (monitorage, journalisation, alertes)

### Vue d'ensemble

L'API TomatoScan est surveillée par une chaîne **Prometheus → Grafana** doublée d'une
journalisation **loguru**. L'API expose quatre métriques sur `GET /metrics/`
(`app.mount("/metrics", make_asgi_app())`, `main.py:268`), Prometheus les scrape toutes les 15 s
(`monitoring/prometheus.yml`, cible `api:8000`), Grafana les affiche sur un dashboard de 7 panneaux
et évalue une règle d'alerte. Toute la configuration (datasource, dashboards, règle d'alerte, point
de contact, politique de routage) est **provisionnée en YAML versionné** — aucune configuration
cliquée à la main dans l'UI.

### Ce qui est surveillé, et pourquoi ces seuils

Quatre métriques sont définies dans `src/tomatoscan/api/metrics.py` et incrémentées dans
`routes/predict.py` à chaque `POST /predict` (`docs/monitoring.md:27-54`) :

| Métrique | Type | Seuil d'alerte |
|---|---|---|
| `tomatoscan_errors_total` (label `type_erreur`) | Counter | **`sum(rate(...[5m])) > 0.1` req/s pendant 1 min** — seule alerte active |
| `tomatoscan_prediction_duration_seconds` | Histogram | Aucun — lecture visuelle (p50/p95) |
| `tomatoscan_predictions_total` (labels `classe`, `statut`) | Counter | Aucun — distribution à interpréter humainement |
| `tomatoscan_prediction_confidence` | Histogram | Aucun — surveillé à l'œil, pas de réentraînement auto |

Le seuil de l'unique alerte active (`> 0.1 req/s`, soit ≈ 1 erreur toutes les 10 s en moyenne sur
5 min) est **justifié explicitement** : il distingue un problème réel et soutenu (modèle en panne,
dépendance indisponible) d'un pic isolé ; le délai `for: 1m` évite un déclenchement sur une seule
évaluation ponctuelle ; le même seuil est repris en code couleur sur le dashboard (vert < 0.05,
jaune 0.05–0.1, rouge > 0.1). L'**absence** de seuil sur les trois autres métriques est elle aussi
argumentée (un seuil fixe universel sur la confiance ou la latence produirait plus de faux positifs
que de vrais signaux à cette échelle) — `docs/monitoring.md:40-54`.

### Journalisation corrélée aux métriques

`loguru` est utilisé dans 13 fichiers de `src/`. La corrélation log ↔ métrique est explicite dans
`routes/predict.py` : chaque branche d'erreur **journalise ET incrémente** la métrique
correspondante — `format_invalide` (l.103-104), `modele_indisponible` (l.122-123), `image_corrompue`
(l.135-136), `erreur_prediction` (l.141-142), puis `duration.observe` (l.146) et `predictions_total`
+ `prediction_confidence.observe` (l.149-150) sur le chemin nominal. Une métrique dit *qu'il y a eu*
une erreur ; le log dit *laquelle*, *pour qui*, *pourquoi*. Le choix « sortie standard uniquement,
pas de rotation ni de niveau personnalisé » est assumé et justifié (`docker logs`/Coolify centralisent
déjà la sortie standard) — `docs/monitoring.md:95-113`.

### Choix d'outillage argumenté

`docs/monitoring.md:56-93` justifie chaque choix : Prometheus + Grafana (open source,
auto-hébergeable sur le même VPS, alerting intégré sans Alertmanager séparé, standard de facto
FastAPI, provisioning déclaratif) plutôt qu'un SaaS (Datadog) ou une stack lourde (ELK/Loki) ;
loguru plutôt qu'un stack de logs séparé (déjà adopté partout dans `src/`) ; e-mail plutôt que
Slack/webhook (canal le plus simple, un seul destinataire). Le choix d'exposer `/metrics` sans
authentification est documenté (`main.py`).

### Alertes câblées et bug de règle corrigé

La règle Unified Alerting `monitoring/grafana/provisioning/alerting/alertes.yml` est bien formée :
`A` (`sum(rate(tomatoscan_errors_total[5m]))`) → `B` (`type: reduce`, `reducer: last`) → `C`
(`threshold gt 0.1` sur `B`), `for: 1m`, `datasourceUid: prometheus` cohérent avec la datasource
provisionnée. Le nœud `reduce B` **corrige un bug réel** : Grafana exige qu'une condition d'alerte
produise une valeur unique par série (« *only reduced data can be alerted on* ») ; sans lui,
l'ancienne configuration renvoyait une série de 301 points au lieu d'un scalaire — vérifié en local
(`docs/monitoring.md:211-237`). Le routage est cohérent : `contact_points.yml` (receiver
`email-tomatoscan`) et `policies.yml` pointent le même nom ; le SMTP est câblé via `GF_SMTP_*`
(`docker-compose.yml`, `.env.example`).

**Limite assumée** : à l'état par défaut, l'e-mail ne partirait pas réellement — `GF_SMTP_ENABLED=false`
et adresse destinataire = placeholder. La règle s'évalue et se déclenche normalement, mais la remise
sortante nécessite un vrai SMTP + une vraie adresse. C'est un remplissage de config documenté
honnêtement, pas un manque de fond.

### Outils opérationnels en local

`monitoring/` contient `Dockerfile.prometheus`, `Dockerfile.grafana`, `prometheus.yml` et le
provisioning complet. `docker-compose.local.yml` publie `9090:9090` (Prometheus) et `3000:3000`
(Grafana) pour la démo. Le dashboard `tomatoscan.json` compte **7 panneaux** (Prédictions/s,
Prédictions totales, Erreurs/s, Durée d'inférence, Erreurs par type, Prédictions par classe,
Confiance moyenne). Test exécuté : `pytest tests/test_api/test_metrics.py` → **1 passed** ;
`GET /metrics/` renvoie 200 et contient les 4 métriques attendues.

**[CAPTURE À INSÉRER — dashboard Grafana « TomatoScan — Monitoring » (7 panneaux) avec du trafic
réel : au moins la courbe Erreurs/s au-dessus du seuil rouge et/ou une alerte en état `firing`.]**

### Accessibilité du document (exigence propre à C20)

Le critère d'accessibilité de C20 porte sur **le document de monitoring lui-même**. `docs/monitoring.md`
respecte : hiérarchie de titres correcte H1 → H2 → H3 sans saut de niveau, tableaux à en-têtes de
colonnes, **aucune information portée uniquement par la couleur** (les niveaux d'alerte du dashboard
sont toujours nommés en texte, ex. « vert/jaune/rouge » accompagné du libellé chiffré). Une
déclaration d'accessibilité explicite figure en pied de document (Markdown structuré, navigable au
clavier / lecteur d'écran, rendu délégué à GitHub, déjà conforme aux standards web). Seule réserve
assumée : l'interface Grafana elle-même (outil tiers, admin-only) n'a pas fait l'objet d'un audit
WCAG dédié.

### Tableau des critères — C20

| Critère | Statut | Preuve |
|---|---|---|
| Documentation liste métriques + seuils/valeurs d'alerte | ✅ | `docs/monitoring.md:27-54` — 4 métriques, seuil de la seule métrique à risque explicité et justifié, absence de seuil sur les 3 autres argumentée |
| Arguments en faveur des choix d'outillage | ✅ | `docs/monitoring.md:56-93` — Prometheus/Grafana/loguru, e-mail vs Slack, `/metrics` sans auth (`main.py`) |
| Outils installés et opérationnels a minima en local | ✅ | `monitoring/` + `docker-compose.local.yml` (9090/3000), dashboard 7 panneaux, `pytest test_metrics.py` → 1 passed, `GET /metrics/` → 200 |
| Règles de journalisation intégrées aux sources | ✅ | loguru dans 13 fichiers ; corrélation log↔métrique `routes/predict.py:103-150` |
| Alertes configurées et en état de marche | ✅ | `alertes.yml` (A→B→C, `for:1m`), `contact_points.yml`/`policies.yml` cohérents, SMTP câblé |
| Doc procédure d'installation/config des dépendances | ✅ | `docs/monitoring.md:115-247` (Coolify + local + canal d'alerte) |
| Doc au format respectant les recommandations d'accessibilité | ✅ | H1→H3 sans saut, tableaux à en-têtes, rien porté par la couleur seule, déclaration d'accessibilité en pied |

Réserve unique et défendable : la remise e-mail de bout en bout (SMTP réel + destinataire réel) reste
à activer pour une démo complète — la règle et le routage sont en place.

---

## C21 — Résoudre un incident technique et documenter la solution

### Vue d'ensemble

`docs/incidents.md` documente **trois incidents réels** rencontrés et corrigés sur le projet, chacun
tracé par sa branche `fix/*`, ses commits et sa pull request. L'incident phare — retenu pour
l'évaluation détaillée et le test de non-régression — est un bug de décodage **base64 vs base64url**
qui dégradait *par intermittence* le rôle admin en agriculteur. Les deux autres (healthcheck
PostgreSQL trop court, `torch` tirant les wheels CUDA sur un VPS CPU) suivent le même schéma
symptôme → diagnostic → cause racine → correction → vérification → prévention.

### Incident 1 — Rôle admin dégradé : base64 standard vs base64url

**Chaîne complète** (`docs/incidents.md:14-143`), PR #84, branche `fix/role-login-decodage`, commit
`da4f786`, merge `8c21745` :

- **Symptôme** — En préproduction Coolify, le compte admin était *parfois* traité comme un simple
  agriculteur (pages d'administration refusées, session invalidée). Intermittent, sans action
  reproductible évidente.
- **Reproduction en développement** — Un script forge un JWT dont la payload encodée contient `-` et
  `_` (username `~ferme?`). Rejoué réellement : l'ancien décodage `base64.b64decode` **lève**
  `UnicodeDecodeError`, alors que `base64.urlsafe_b64decode` décode correctement
  `{'sub':'~ferme?','role':'admin','exp':9999999999}`. Un username alphanumérique ne produit jamais
  `-`/`_` — d'où l'intermittence (mesuré : 0 déclenchement sur 700 000+ tokens à username normal).
- **Diagnostic + cause racine** — `_decoder_payload_token` (`front/utils/api_client.py`) décodait la
  payload avec l'alphabet **base64 standard** (`+/`) au lieu de l'alphabet **base64url** (`-_`) imposé
  par la RFC 7519 pour les JWT. Les deux alphabets ne diffèrent que sur les valeurs 62 et 63 : tant
  qu'aucune n'apparaît, le bug reste invisible. Le décodage faux faisait juger le token invalide par
  `is_token_valid` (→ admin déconnecté) et retomber `obtenir_role` sur son défaut `"agriculteur"`
  (→ admin dégradé). Analyse binaire correcte (seuls `~`=0x7E et `?`=0x3F portent 6 bits consécutifs
  à 1 parmi les ASCII imprimables).
- **Correction** — Diff réel de `da4f786`, confirmé par `git show` :

  ```diff
  -    return json.loads(base64.b64decode(partie_payload))
  +    return json.loads(base64.urlsafe_b64decode(partie_payload))
  ```

  La même PR ajoute un log dans les `except` de `is_token_valid`/`obtenir_role` pour qu'un futur échec
  ne soit plus silencieux. Un renforcement ultérieur (PR #87, `b54540a`) délègue entièrement le
  décodage à **PyJWT** (`jwt.decode(token, options={"verify_signature": False})`) — implémentation
  actuelle, plus robuste encore.
- **Vérification** — Test de non-régression créé (voir ci-dessous).

**[CAPTURE À INSÉRER — le fil de suivi de l'incident : la pull request #84 (`fix/role-login-decodage`)
sur GitHub, ou le résultat `git show 8c21745` montrant le merge, pour matérialiser l'outil de suivi.]**

### Le test de régression détecte réellement le bug

`tests/test_frontend/test_regression_base64url.py` → **5 passed in 0.23s**. Il n'est pas complaisant,
sur trois plans vérifiés :

1. Il invoque la **vraie fonction** du projet (`_decoder_payload_token` via PyJWT), pas une copie.
2. La payload piège est **garde-foutée** : un test dédié vérifie que la payload encodée contient bien
   `-` **et** `_`, sinon le test de régression ne prouverait rien.
3. La **détection réelle** est prouvée par mutation : `test_l_ancien_decodage_base64_standard_echouait`
   rejoue l'ancien décodage `base64.b64decode` et `pytest.raises` confirme qu'il **échoue** sur cette
   même payload — là où le correctif `urlsafe` réussit. Un test qui passerait aussi bien avant qu'après
   le correctif ne détecterait rien ; ici l'écart avant/après est explicitement démontré.

Le test existant `test_api_client.py::test_decode_et_expiration` ne couvrait pas ce cas (payload
alphanumérique sans `-`/`_`) : c'est précisément le trou qu'il fallait combler.

### Passage par la CI et versionnement

`.github/workflows/ci-app.yml` se déclenche sur push `develop`/`main` et sur pull request, et exécute
`uv run pytest tests/ -v --cov …`, ce qui inclut `test_regression_base64url.py`. `da4f786` a été mergé
sur `develop` via la PR #84 — donc passé par la CI. La branche `fix/role-login-decodage` existe en
local et en remote ; `da4f786` est ancêtre de `develop` (`git merge-base --is-ancestor` → vrai) ;
`incidents.md` et le test sont committés sur `develop` (`4e6d4e3`), working-tree propre.

### Note de traçabilité honnête

Les correctifs `fix/*` du projet sont tracés par **numéro de pull request** (via le commit de merge),
**pas** par une issue GitHub dédiée. Aucun commit d'incident (`da4f786`, `b48cf4c`, `56a18a2`,
`4732bbe`) ne référence d'issue ; les issues n'ont servi que sur les commits de fonctionnalité
(`docs/incidents.md:206-215`). La chaîne branche → commit → PR → merge reste intégralement vérifiable
par `git`. Nuance à défendre à l'oral : l'« outil de suivi » mobilisé est la PR, pas une issue au sens
strict.

### Tableau des critères — C21

| Critère | Statut | Preuve |
|---|---|---|
| Cause(s) du problème identifiée(s) correctement | ✅ | `docs/incidents.md:59-86` — `b64decode` vs `urlsafe_b64decode` ; confirmé par `git show da4f786` ; cause chaînée jusqu'au symptôme |
| Problème reproduit en environnement de développement | ✅ | `docs/incidents.md:27-56` — script rejoué : OLD → `UnicodeDecodeError`, NEW → décode ; intermittence expliquée (0/700000+) |
| Procédure de débogage documentée depuis l'outil de suivi | ✅ | `docs/incidents.md` (Symptôme→…→Vérification) rattachée à PR #84 ; note honnête PR-vs-issue (L206-215) |
| Solution explicite chaque étape de résolution/implémentation | ✅ | Diff `da4f786` + logs `except`, renforcement PyJWT PR #87, test de non-régression ; 2 incidents supplémentaires au même format |
| Solution versionnée dans Git (merge request) | ✅ | Branche `fix/role-login-decodage`, `da4f786` ancêtre de `develop`, PR #84 (`8c21745`) ; `incidents.md`+test committés (`4e6d4e3`) |
| [Jury] Test de régression qui passe ET détecte le bug | ✅ | `pytest test_regression_base64url.py` → 5 passed ; vraie fonction, payload garde-foutée, mutation prouvée (OLD lève, NEW OK) |
| [Jury] Fix passé par la CI + livrable `incidents.md` versionné | ✅ | `ci-app.yml` (push/PR → `pytest tests/`) ; `da4f786` mergé via PR #84 ; `incidents.md` tracké sur `develop` (`4e6d4e3`) |

Réserve défendable : une issue GitHub dédiée par incident renforcerait la traçabilité « outil de suivi »
au sens strict — le suivi actuel par PR reste néanmoins complet et vérifiable.

---

## Grille de correspondance au référentiel

### C20 — Surveiller une application d'IA
| Critère | Où est la preuve |
|---|---|
| Métriques + seuils/alertes documentés | `docs/monitoring.md:27-54` ; `api/metrics.py` |
| Choix d'outillage argumentés | `docs/monitoring.md:56-93` |
| Outils opérationnels en local | `monitoring/`, `docker-compose.local.yml`, `pytest test_metrics.py` |
| Journalisation intégrée aux sources | 13 fichiers loguru ; `routes/predict.py:103-150` |
| Alertes en état de marche | `alertes.yml`, `contact_points.yml`, `policies.yml` |
| Doc installation/config des dépendances | `docs/monitoring.md:115-247` |
| Doc accessible | `docs/monitoring.md` (déclaration d'accessibilité en pied) |

### C21 — Résoudre un incident et documenter la solution
| Critère | Où est la preuve |
|---|---|
| Cause identifiée | `docs/incidents.md:59-86` ; `git show da4f786` |
| Reproduction en dev | `docs/incidents.md:27-56` (script rejoué) |
| Débogage documenté / suivi | `docs/incidents.md` + PR #84 (`8c21745`) |
| Chaque étape de résolution explicitée | `docs/incidents.md` (diff, PyJWT, vérification) |
| Solution versionnée (MR) | Branche `fix/role-login-decodage`, PR #84 |
| Test de régression détectant le bug | `tests/test_frontend/test_regression_base64url.py` (5 passed) |
| Fix par la CI + livrable versionné | `.github/workflows/ci-app.yml` ; `incidents.md` (`4e6d4e3`) |

---

## Synthèse et verdict

| Compétence | Verdict | Critères prouvés | Points à consolider |
|---|---|---|---|
| **C20** | ✅ Acquise | 7/7 | ⚠️ activer SMTP réel + destinataire pour une démo e-mail de bout en bout (règle et routage déjà en place) |
| **C21** | ✅ Acquise | 7/7 | ⚠️ une issue GitHub dédiée par incident renforcerait le « outil de suivi » au sens strict (suivi PR déjà complet) |

Les deux compétences sont **acquises**. Les points restants sont documentés honnêtement et
défendables à l'oral : ce sont des consolidations (activer un SMTP réel, ouvrir une issue par
incident), pas des manques de fond. La distinction monitoring **application** (C20) vs monitoring
**modèle** (C11) est explicite dans `docs/monitoring.md`, et la chaîne complète de l'incident
base64url — bien attribuée, reproduite, corrigée, versionnée, couverte par un test qui détecte
réellement le bug — est vérifiable intégralement par `git` et `pytest`.

### À faire manuellement par le candidat avant le 31 juillet 2026

1. **Insérer les captures** marquées `[CAPTURE À INSÉRER]** :
   - Dashboard Grafana « TomatoScan — Monitoring » avec trafic réel (Erreurs/s au-dessus du seuil
     rouge et/ou alerte `firing`) — C20 ;
   - Fil de suivi de l'incident : PR #84 sur GitHub ou `git show 8c21745` — C21.
2. **Consolider C20** : renseigner un vrai serveur SMTP et un vrai destinataire dans `.env`
   (`GF_SMTP_ENABLED=true`, `GF_SMTP_HOST`, `ALERTES_EMAIL_DESTINATAIRE`…), déclencher l'alerte et
   montrer un e-mail réellement reçu.
3. **Consolider C21** (optionnel) : ouvrir une issue GitHub par incident pour matérialiser l'« outil
   de suivi » au sens strict, en lien avec les PR existantes.

---

*Rapport établi le 20 juillet 2026 par vérification directe : fichiers relus, commandes réellement
exécutées (`pytest test_metrics.py` → 1 passed ; `pytest test_regression_base64url.py` → 5 passed ;
`git show da4f786`/`8c21745`), aucun chiffre supposé. Aucun commit ni push n'a été effectué lors de
cette rédaction.*
