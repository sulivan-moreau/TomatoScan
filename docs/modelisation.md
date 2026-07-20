# Modélisation — TomatoScan (C14 / C15)

> **Ce fichier est la source de vérité de la modélisation.**
> Il est écrit en Markdown + diagrammes **Mermaid** : éditable, *diffable* et
> versionné avec le code. Il fait foi sur toute autre représentation.
>
> Les PDF de conception issus des issues **#26 / #27**
> (`docs/specs_fonctionnelles.pdf`, `docs/specs_techniques.pdf`,
> `docs/modelisation.pdf`) sont des exports binaires **non éditables** qui ont
> **divergé du code réel**. Ils doivent être **régénérés depuis cette source**.
> Éléments obsolètes qu'ils contiennent encore et qui n'existent pas dans le
> système réel :
>
> | Élément du PDF (obsolète) | Réalité du code |
> |---|---|
> | Entité `MODEL` dans le MCD | **Aucune table modèle** — le modèle est un fichier `.pt` chargé en mémoire au démarrage (voir note sous le MCD) |
> | TensorFlow / fichier `.keras` | **PyTorch** — checkpoint `models/mobilenetv2_best_*.pt` |
> | MLflow (suivi d'expériences) | **Pas de MLflow** — rapports d'entraînement/évaluation en JSON/CSV versionnés dans `docs/` |
> | Colonnes `disease_class` / `confidence_score` | Colonnes réelles **`classe_predite`** / **`confiance`** |
>
> **Preuves (fichiers réels du dépôt) :** schéma de base de données
> `src/tomatoscan/database/modeles.py` ; chargement du modèle
> `src/tomatoscan/api/services/model_service.py` ; entraînement PyTorch
> `src/tomatoscan/model/train.py`.

---

## 1. Modèle conceptuel de données (MCD / entités-relations)

Reflète **exactement** les deux tables déclarées dans
`src/tomatoscan/database/modeles.py` (classes SQLAlchemy `User` → table
`users`, `Prediction` → table `predictions`). Noms de colonnes et types
Python/SQLAlchemy repris tels quels.

```mermaid
erDiagram
    users ||--o{ predictions : "déclenche"

    users {
        Uuid     id              PK "clé primaire, défaut uuid4, indexée"
        String   username        UK "unique, non nul, indexée"
        String   email           UK "unique, non nul"
        String   hashed_password    "non nul (bcrypt)"
        String   role               "non nul, défaut : agriculteur (ou admin)"
        DateTime created_at         "timezone=True, non nul, défaut : now() UTC"
    }

    predictions {
        Integer  id              PK "clé primaire, entier auto-incrémenté"
        Uuid     user_id         FK "-> users.id, non nul"
        String   nom_fichier        "non nul"
        String   classe_predite     "non nul (ex. Tomato_Early_blight)"
        Float    confiance          "non nul, score 0.0 à 1.0"
        DateTime created_at         "timezone=True, non nul, défaut : now() UTC"
    }
```

**Cardinalité** : un `users` possède 0..N `predictions` ; chaque `predictions`
appartient à exactement un `users` (relation SQLAlchemy `User.predictions` ↔
`Prediction.utilisateur`, FK `predictions.user_id`).

> **Note — pas d'entité `MODEL` en base.** Le modèle de classification n'est
> **pas** une table. C'est un **checkpoint PyTorch** (`.pt`) —
> `models/mobilenetv2_best_20260624_161841.pt` par défaut, surchargé par la
> variable d'environnement `MODEL_PATH` — chargé **une seule fois au démarrage**
> de l'API (singleton `initialiser_modele()` dans
> `src/tomatoscan/api/services/model_service.py`). Le checkpoint embarque les
> poids (`model_state_dict`) et la liste des classes (`class_names`, 10 classes
> tomate). Il n'est donc ni stocké ni versionné en base de données. De même, les
> **images ne sont pas persistées** : seul le **nom du fichier** (`nom_fichier`)
> est conservé, pas l'image elle-même.

---

## 2. Diagramme de flux de données

Chaîne réelle : navigateur → **Streamlit** (front) → **FastAPI** (API) →
**MobileNetV2 (PyTorch)** → **PostgreSQL**, avec **Prometheus + Grafana** pour le
monitoring. Les libellés de données utilisent les **vrais** noms de colonnes
(`classe_predite`, `confiance`).

```mermaid
flowchart LR
    U["Utilisateur<br/>(agriculteur / admin)"]

    subgraph FRONT["Front — Streamlit"]
        UP["Upload image + compression<br/>client (1024 px, JPEG 85)"]
        HIST["Pages : login, predict,<br/>history, dashboard"]
    end

    subgraph API["API — FastAPI"]
        AUTH["Auth JWT<br/>POST /auth/token"]
        PRED["POST /predict<br/>(Bearer requis)"]
        GETH["GET /predictions/history<br/>GET /reports · GET /users"]
    end

    MODEL["MobileNetV2 (PyTorch)<br/>checkpoint .pt chargé au démarrage<br/>infère en 224x224"]
    DB[("PostgreSQL<br/>tables : users, predictions")]

    subgraph MON["Monitoring"]
        PROM["Prometheus<br/>GET /metrics"]
        GRAF["Grafana<br/>tableaux de bord"]
    end

    U --> FRONT
    UP -->|"image (multipart)"| PRED
    HIST -->|"identifiants"| AUTH
    HIST -->|"consultation"| GETH

    PRED -->|"tenseur 224x224"| MODEL
    MODEL -->|"classe_predite + confiance"| PRED
    PRED -->|"INSERT predictions<br/>(user_id, nom_fichier,<br/>classe_predite, confiance)"| DB
    AUTH -->|"vérifie users"| DB
    GETH -->|"SELECT predictions / users"| DB

    API -.->|"métriques d'inférence"| PROM
    PROM --> GRAF
```

> **Note — pas de MLflow.** Aucun suivi d'expériences MLflow n'est branché. Les
> métriques d'inférence en production sont exposées par l'API sur `GET /metrics`
> au format Prometheus (`src/tomatoscan/api/metrics.py`) :
> `tomatoscan_predictions_total`, `tomatoscan_prediction_duration_seconds`,
> `tomatoscan_prediction_confidence`, `tomatoscan_errors_total`. Les rapports
> d'entraînement / évaluation sont des artefacts **JSON / CSV versionnés** dans
> `docs/` (ex. `docs/rapport_evaluation_20260624_163236.json`), pas des runs
> MLflow.

---

## 3. Parcours utilisateurs

Cohérents avec les pages réelles de `src/tomatoscan/front/pages/`
(`accueil.py`, `login.py`, `predict.py`, `history.py`, `dashboard.py`,
`creer_membre.py`).

### 3.1 Agriculteur

```mermaid
flowchart TD
    A["Accueil (non connecté)<br/>accueil.py"] --> B["Connexion<br/>login.py"]
    B -->|"POST /auth/token"| C{"Identifiants<br/>valides ?"}
    C -->|"non"| B
    C -->|"oui"| D["Session : token JWT + rôle<br/>(rôle = agriculteur)"]
    D --> E["Nouvelle analyse<br/>predict.py"]
    E --> F["Import photo de feuille<br/>(jpg / jpeg / png, <= 5 Mo)"]
    F --> G["Compression côté client<br/>puis POST /predict (Bearer)"]
    G --> H["Diagnostic affiché<br/>classe_predite + confiance<br/>(+ recommandation si maladie)"]
    H --> I["Prédiction enregistrée en base<br/>(table predictions)"]
    D --> J["Historique de mes analyses<br/>history.py"]
    J -->|"GET /predictions/history"| K["Tableau : date, fichier,<br/>maladie détectée, confiance"]
```

### 3.2 Administrateur

```mermaid
flowchart TD
    A["Connexion<br/>login.py"] -->|"POST /auth/token"| B["Session : rôle = admin"]
    B --> C["Accueil : accès rapides + bloc Administration<br/>accueil.py"]
    C --> D["Tableau de bord<br/>dashboard.py"]
    D -->|"GET /reports"| D1["Rapport d'entraînement du modèle<br/>(epochs, meilleure accuracy val)"]
    D -->|"GET /users"| D2["Liste des utilisateurs<br/>+ suppression d'un agriculteur"]
    D -->|"GET /predictions/history"| D3["Prédictions de tous les utilisateurs<br/>(admin = vue globale)"]
    D --> D4["Lien Grafana<br/>(monitoring, si GRAFANA_URL défini)"]
    C --> E["Créer un membre<br/>creer_membre.py"]
    E -->|"POST création compte<br/>(rôle imposé : agriculteur)"| F["Compte agriculteur créé"]
    B --> G["Peut aussi utiliser predict.py<br/>et history.py comme un agriculteur"]
```

---

## 4. Standard d'accessibilité visé

Le front vise la conformité **WCAG 2.1 niveau AA**. Concrètement, côté code :
contrastes texte/fond calculés par formule de luminance relative WCAG (bandeaux
résultat : blanc sur `#2d6a4f` = 6.39:1 et blanc sur `#c1121f` = 6.22:1, tous
deux ≥ 4.5:1 requis en AA), textes alternatifs sur les aperçus d'image, icônes
décoratives marquées `aria-hidden`, et structure de pages navigable au clavier
(voir `src/tomatoscan/front/pages/predict.py` et `history.py`).

---

*Document éditable — toute évolution du schéma
(`src/tomatoscan/database/modeles.py`) ou des pages front doit être répercutée
ici, puis les PDF de conception régénérés depuis cette source.*
