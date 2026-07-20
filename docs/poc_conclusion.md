# Conclusion de la preuve de concept (POC) — TomatoScan (C15)

Ce document conclut la preuve de concept de TomatoScan : un service de détection
des maladies de la feuille de tomate à partir d'une photo. Il s'appuie sur des
**mesures réelles vérifiables dans le dépôt**, énonce honnêtement les limites du
moment, et rend un **avis GO / NO-GO argumenté**.

Périmètre : projet de diplôme (DevIA Simplon, RNCP). L'ambition est un POC
fonctionnel et honnête, pas un produit industrialisé à l'échelle.

---

## 1. Ce qui est démontré

| Élément | Statut |
|---|---|
| Modèle entraîné et évalué (MobileNetV2, PyTorch) | Oui — rapport versionné |
| API d'inférence (FastAPI, `POST /predict`, auth JWT) | Oui |
| Front utilisateur (Streamlit : login, analyse, historique, admin) | Oui |
| Persistance des prédictions (PostgreSQL) | Oui — table `predictions` |
| Monitoring (Prometheus + Grafana) | Oui — `GET /metrics` |
| Déploiement conteneurisé (Docker Compose, Coolify) | Oui, mais **préprod non joignable au dernier constat** (voir §5) |

---

## 2. Performance du modèle (mesures réelles)

**Source : `docs/rapport_evaluation_20260624_163236.json`** (rapport
d'évaluation versionné, généré par `src/tomatoscan/model/evaluate.py`).

| Mesure | Valeur | Champ source du JSON |
|---|---|---|
| Modèle | MobileNetV2 (transfer learning, PyTorch) | `modele` |
| **Accuracy sur le jeu de test** | **0,9355 (≈ 93,6 %)** | `accuracy_test` |
| Meilleure accuracy en validation | 0,9455 | `meilleure_accuracy_validation` |
| Meilleure epoch | 13 | `meilleure_epoch` |
| Nombre de classes | **10** classes tomate | clés de `rapport_classification` |
| Taille du jeu de test | **2 402 images** | `rapport_classification.weighted avg.support` |
| Classes sous-performantes signalées | aucune (`[]`) | `classes_sous_performantes` |

Les 10 classes : `Tomato_Bacterial_spot`, `Tomato_Early_blight`,
`Tomato_Late_blight`, `Tomato_Leaf_Mold`, `Tomato_Septoria_leaf_spot`,
`Tomato_Spider_mites_Two_spotted_spider_mite`, `Tomato__Target_Spot`,
`Tomato__Tomato_YellowLeaf__Curl_Virus`, `Tomato__Tomato_mosaic_virus`,
`Tomato_healthy`.

**Lecture honnête.** 93,6 % d'accuracy sur 10 classes est un bon résultat pour un
POC. Le rapport par classe montre toutefois une faiblesse réelle sur
`Tomato_Early_blight` (rappel ≈ 0,73 : environ un cas sur quatre manqué), à
surveiller avant tout usage terrain. Le jeu provient de PlantVillage (images
cadrées, fond neutre) : la performance en conditions réelles (photo de champ,
éclairage variable) reste à valider et sera probablement inférieure.

---

## 3. Latence / durée d'inférence

La latence d'inférence est instrumentée mais **je ne fabrique pas de valeur
chiffrée** ici faute de mesure sous charge disponible.

- **Métrique** : `tomatoscan_prediction_duration_seconds` — un `Histogram`
  Prometheus défini dans `src/tomatoscan/api/metrics.py` et observé dans
  `src/tomatoscan/api/routes/predict.py` (bloc `finally`, `time.perf_counter()`
  encadrant **uniquement** l'appel `model_service.predire`, donc l'inférence
  seule, hors réseau).
- **Comment l'obtenir** : exposée sur `GET /metrics`, elle est agrégée par
  Grafana. Pour un quantile (ex. p95), requête PromQL type
  `histogram_quantile(0.95, rate(tomatoscan_prediction_duration_seconds_bucket[5m]))`.
  En local, on peut aussi la lire directement après quelques prédictions via
  `curl http://localhost:8000/metrics | grep prediction_duration`.
- **Attendu qualitatif** : MobileNetV2 est un réseau léger, l'inférence tourne
  en **CPU** sur une image 224×224 — de l'ordre de la fraction de seconde par
  image. À confirmer par la métrique ci-dessus une fois la préprod rétablie.

---

## 4. Empreinte / éco-conception (C17)

Choix réels du dépôt limitant le coût de calcul, de stockage et de bande
passante :

- **CPU uniquement** : `Dockerfile.api` installe `torch`/`torchvision` depuis
  l'index CPU (`--index-url .../whl/cpu`), ce qui évite ~2 Go de wheels CUDA
  inutiles (voir aussi `docs/incidents.md`, incident 3). Pas de GPU requis.
- **Images Docker légères** : base `python:3.11-slim`, dépendances de dev
  exclues (`uv sync --no-dev`).
- **Pas de stockage d'image** : seul le `nom_fichier` est persisté en base
  (table `predictions`), jamais l'image — voir §1 de `docs/modelisation.md` et
  `src/tomatoscan/api/routes/predict.py`.
- **Compression côté client avant envoi** : `_compresser_image` dans
  `src/tomatoscan/front/pages/predict.py` borne l'image à 1024 px / JPEG 85
  avant l'upload (le modèle infère de toute façon en 224×224) ; l'upload est
  plafonné à 5 Mo.
- **Mise en cache** des appels du tableau de bord (`@st.cache_data`,
  `src/tomatoscan/front/pages/dashboard.py`) pour éviter des requêtes réseau
  redondantes à chaque re-run Streamlit.

---

## 5. Limites identifiées (honnêtes)

1. **Préproduction non joignable au dernier constat.** L'application est
   conteneurisée et déployée via Coolify sur un VPS (OVH), mais
   l'environnement de préproduction n'est **pas joignable actuellement** :
   domaine de préprod non résolu et production répondant `503` au dernier
   constat. **Ce n'est pas un échec masqué mais une limite réelle et une action
   à mener.** Aucune URL publique n'est codée en dur dans le dépôt (les hôtes
   sont configurés côté Coolify), la vérification doit donc être refaite sur le
   domaine réel, par exemple :
   `curl -I https://<domaine-preprod>/health` et
   `curl -I https://<domaine-prod>/health`.
   **Action** : diagnostiquer le déploiement Coolify (DNS du domaine préprod,
   état des conteneurs, healthcheck de l'API — cf. incident 2 de
   `docs/incidents.md`) puis re-tester le parcours complet en préprod.
2. **Généralisation terrain non prouvée** : performances établies sur
   PlantVillage uniquement (§2).
3. **Rappel faible sur `Tomato_Early_blight`** (≈ 0,73) : à améliorer.
4. **Latence non chiffrée sous charge** : instrumentée mais pas encore mesurée
   (§3).

---

## 6. Démonstration reproductible en local (en attendant la préprod)

En attendant le rétablissement de la préprod, le POC se démontre **entièrement
en local** de façon reproductible avec Docker Compose.

```bash
# À la racine du dépôt
docker network create coolify        # réseau attendu par la stack (une seule fois)
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

Parcours de démonstration :

1. **Connexion** : ouvrir le front Streamlit, se connecter avec un compte
   (l'admin est provisionné au démarrage via le bootstrap).
2. **Prédiction** : page « Nouvelle analyse » → importer une photo de feuille
   (jpg/png) → « Analyser » → le diagnostic s'affiche (classe + confiance, avec
   recommandation si une maladie est détectée).
3. **Historique** : page « Historique » → la prédiction qui vient d'être faite
   apparaît (date, fichier, maladie, confiance) — preuve de la persistance en
   base `predictions`.
4. **Monitoring** : Prometheus sur `http://localhost:9090`, Grafana sur
   `http://localhost:3000` (exposés uniquement par `docker-compose.local.yml`),
   ou lecture brute des métriques sur `http://localhost:8000/metrics`.

Ce parcours démontre la chaîne complète décrite dans `docs/modelisation.md`
(front → API → MobileNetV2 → PostgreSQL + monitoring) sans dépendre de la
préprod.

---

## 7. Avis final — **GO** (avec réserves)

**GO pour la poursuite du projet.** Les briques essentielles sont réelles et
fonctionnelles : un modèle évalué à **93,6 % d'accuracy** sur **10 classes** et
**2 402 images de test** (source : `docs/rapport_evaluation_20260624_163236.json`),
une API d'inférence authentifiée, un front complet couvrant les parcours
agriculteur et admin, la persistance en base et un monitoring branché. Le POC est
**démontrable de bout en bout en local** dès aujourd'hui.

**Réserves à lever avant tout passage en usage réel** (ordre de priorité) :

1. Rétablir et vérifier la **préproduction** (diagnostic Coolify / DNS / 503),
   puis rejouer le parcours complet en préprod.
2. **Mesurer la latence** réelle via `tomatoscan_prediction_duration_seconds`.
3. **Améliorer le rappel** sur `Tomato_Early_blight` et **valider la
   généralisation** sur des photos de terrain (hors PlantVillage).

Aucune de ces réserves ne remet en cause la faisabilité démontrée : elles
constituent la feuille de route de consolidation. D'où l'avis **GO**.
