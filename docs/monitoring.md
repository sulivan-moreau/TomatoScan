# Monitoring — Prometheus & Grafana

Documente la chaîne de monitoring de l'API TomatoScan : installation, métriques
surveillées, seuils d'alerte, et utilisation du dashboard.

Ferme le ticket [#18 — docs: documentation de la chaîne de monitoring](https://github.com/sulivan-moreau/tomatoscan/issues/18).

## Sommaire

1. [Architecture](#architecture)
2. [Installation](#installation)
3. [Métriques surveillées](#métriques-surveillées)
4. [Seuils d'alerte](#seuils-dalerte)
5. [Utiliser le dashboard](#utiliser-le-dashboard)

## Architecture

```
API FastAPI (/metrics/)  →  Prometheus (scrape 15s)  →  Grafana (dashboards + alertes)
```

- L'API expose ses métriques via `prometheus_client` sur `GET /metrics/` (montage
  Starlette `app.mount("/metrics", ...)`).
- Prometheus scrape cet endpoint toutes les 15 secondes (`monitoring/prometheus.yml`)
  et conserve 30 jours d'historique (`--storage.tsdb.retention.time=30d`, voir
  `docker-compose.yml`).
- Grafana lit Prometheus comme source de données et affiche le dashboard
  `TomatoScan — Monitoring` (`monitoring/grafana/dashboards/tomatoscan.json`),
  provisionné automatiquement au démarrage (pas de configuration manuelle dans
  l'UI Grafana requise).

Les trois services (API, Prometheus, Grafana) tournent sur le même réseau Docker
`coolify` — Prometheus résout l'API par son nom de service (`api:8000`), pas par IP.

## Installation

### En production / préprod (Coolify)

Prometheus et Grafana sont déjà définis comme services dans `docker-compose.yml` et
se déploient automatiquement avec le reste de la stack (`just up` ou déploiement
Coolify sur push `develop`/`main`). Rien à installer séparément.

Variables requises dans `.env` (voir `.env.example`) :

| Variable | Rôle |
|---|---|
| `GRAFANA_PASSWORD` | Mot de passe du compte admin Grafana |
| `GRAFANA_URL` | URL affichée par le bouton « Ouvrir le monitoring » du tableau de bord admin (frontend) |

### En local (développement)

```bash
just up-dev
# ou directement :
docker compose -f docker-compose.yml -f docker-compose.override.yml up
```

`docker-compose.override.yml` expose Prometheus sur `localhost:9090` et Grafana sur
`localhost:3000` (non exposés par défaut en production, seulement accessibles via le
réseau interne `coolify`).

Accès local :
- Prometheus : http://localhost:9090
- Grafana : http://localhost:3000 (login `admin`, mot de passe `GRAFANA_PASSWORD`)

## Métriques surveillées

Définies dans [`src/tomatoscan/api/metrics.py`](../src/tomatoscan/api/metrics.py),
incrémentées dans [`src/tomatoscan/api/routes/predict.py`](../src/tomatoscan/api/routes/predict.py)
à chaque appel à `POST /predict`.

| Métrique | Type | Labels | Explication |
|---|---|---|---|
| `tomatoscan_predictions_total` | Counter | `classe`, `statut` | Nombre total de prédictions effectuées, ventilé par classe MobileNetV2 détectée (ex. `Tomato_healthy`, `Tomato_Early_blight`) et par statut. Métrique de comportement du modèle : sa distribution par classe permet de repérer un déséquilibre inattendu des diagnostics posés. |
| `tomatoscan_prediction_duration_seconds` | Histogram | — | Durée d'inférence du modèle MobileNetV2 en secondes. Sert à calculer les percentiles p50/p95 de temps de réponse — métrique de performance applicative, indépendante de la qualité des prédictions. |
| `tomatoscan_prediction_confidence` | Histogram | — | Distribution des scores de confiance des prédictions réussies (buckets `0.5` à `1.0`). Métrique de qualité du modèle (pas applicative) : une baisse continue de la confiance moyenne peut signaler une dérive du modèle ou des images d'entrée hors distribution, avant même que l'accuracy réelle ne soit mesurable (celle-ci nécessite un vrai label, jamais disponible en production). |
| `tomatoscan_errors_total` | Counter | `type_erreur` | Nombre total d'erreurs rencontrées sur `/predict`, par type (`format_invalide`, `image_corrompue`, `erreur_prediction`, etc.). Métrique applicative : distingue un problème côté client (image mal formée) d'un problème côté modèle/serveur. |

Distinction volontaire entre métriques **applicatives** (`errors_total`,
`prediction_duration_seconds` — santé du service) et métriques **de comportement du
modèle** (`predictions_total` par classe, `prediction_confidence` — qualité des
prédictions) : les secondes ne remplacent pas une vraie évaluation sur dataset labellisé
(voir [docs/ci_cd_modele.md](ci_cd_modele.md)), mais donnent un signal continu en
production, là où aucun label réel n'est disponible.

## Seuils d'alerte

Définis dans
[`monitoring/grafana/provisioning/alerting/alertes.yml`](../monitoring/grafana/provisioning/alerting/alertes.yml)
(Grafana Unified Alerting, provisionné automatiquement — pas de configuration
manuelle dans l'UI).

| Alerte | Condition | Justification du seuil |
|---|---|---|
| Taux d'erreurs TomatoScan élevé | `sum(rate(tomatoscan_errors_total[5m])) > 0.1` req/s pendant 1 minute continue | 0.1 req/s (soit ~1 erreur toutes les 10 secondes en moyenne sur 5 minutes) distingue un problème réel et soutenu d'un pic isolé (un seul utilisateur envoyant une mauvaise image). La fenêtre de 5 min lisse les à-coups ; le délai `for: 1m` évite de déclencher sur une seule évaluation ponctuelle au-dessus du seuil. |

Le panneau « Erreurs / seconde » du dashboard reprend visuellement ce même seuil
(vert < 0.05, jaune 0.05–0.1, rouge > 0.1 req/s) pour que l'écart avec le seuil
d'alerte soit visible avant même qu'elle se déclenche.

Aucun seuil d'alerte n'est actuellement défini sur `prediction_confidence` ou sur le
temps de réponse (p95) : ces deux métriques sont surveillées visuellement sur le
dashboard mais ne déclenchent pas d'alerte automatique — une dérive de confiance
demande une lecture humaine du contexte (nouvelle variété de tomate photographiée,
mauvais éclairage...) plutôt qu'un seuil fixe universel.

## Utiliser le dashboard

1. Se connecter à Grafana (voir [Installation](#installation)).
2. Le dashboard **TomatoScan — Monitoring** est provisionné automatiquement — pas
   besoin de l'importer manuellement.
3. Rafraîchissement automatique toutes les 30 secondes, fenêtre par défaut : dernière heure.

Panneaux disponibles :

| Panneau | Ce qu'il montre |
|---|---|
| Prédictions / seconde | Débit instantané de prédictions réussies (moyenne 5 min) |
| Prédictions totales | Compteur cumulé depuis le démarrage du service |
| Erreurs / seconde | Taux d'erreurs, coloré selon le seuil d'alerte (vert/jaune/rouge) |
| Temps de réponse — inférence MobileNetV2 | Percentiles p50 (médiane) et p95 du temps d'inférence |
| Erreurs par type | Débit d'erreurs ventilé par `type_erreur` |
| Prédictions par classe détectée | Distribution des diagnostics posés par le modèle, par classe |
| Confiance moyenne des prédictions | Score de confiance moyen glissant (5 min), coloré rouge < 0.7, jaune 0.7–0.85, vert > 0.85 |

Depuis l'application, le tableau de bord **admin** du frontend Streamlit affiche un
bouton « Ouvrir le monitoring » qui pointe vers `GRAFANA_URL` — accès réservé aux
comptes admin.

**Pourquoi cet accès est réservé aux comptes admin (choix produit tranché pour ce
projet)** : les métriques exposées (taux d'erreurs applicatif, latence d'inférence,
dérive de confiance du modèle) sont des indicateurs opérationnels, destinés à qui
exploite la plateforme — pas des informations utiles au métier d'un agriculteur, dont
le seul besoin fonctionnel est d'obtenir un diagnostic sur sa photo de feuille
(`POST /predict`) et de consulter son propre historique (`GET /predictions/history`,
déjà accessible à tous les rôles, filtré par utilisateur). Exposer ce dashboard à
tous les comptes ajouterait une surface fonctionnelle sans bénéfice pour l'utilisateur
final, pour un projet dont le périmètre reste volontairement simple. Détail complet
et mise en contexte architecturale : [docs/architecture.md](architecture.md#pourquoi-le-monitoring-est-réservé-aux-comptes-admin).

En cas d'alerte « Taux d'erreurs élevé », l'annotation Grafana recommande de
vérifier les logs de l'API FastAPI et l'état du modèle MobileNetV2 (`GET /health`) —
premier réflexe avant d'investiguer plus loin.


---

*Accessibilité : document Markdown structuré par hiérarchie de titres (H1→H3), tableaux avec en-têtes de colonnes, aucune information portée uniquement par la couleur ; lisible par un lecteur d'écran et navigable au clavier depuis GitHub.*
