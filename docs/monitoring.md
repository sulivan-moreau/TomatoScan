# Monitoring — Prometheus & Grafana

Documente la chaîne de monitoring système (C20) de l'API TomatoScan : métriques
suivies et leurs seuils d'alerte, choix des outils, logs applicatifs, installation
en local, canal de notification, et utilisation du dashboard.

Ferme le ticket [#18 — docs: documentation de la chaîne de monitoring](https://github.com/sulivan-moreau/tomatoscan/issues/18).

> Ce document couvre le monitoring **système** (santé de l'API, taux d'erreurs,
> latence) — pas le monitoring du **modèle** au sens dérive/réentraînement continu,
> qui est un sujet séparé documenté dans [docs/ci_cd_modele.md](ci_cd_modele.md)
> (C11). Deux métriques ci-dessous (`predictions_total` par classe,
> `prediction_confidence`) donnent un signal sur le comportement du modèle, mais
> aucune boucle de feedback ou de réentraînement automatique n'est déclenchée
> depuis ce monitoring-ci.

## Sommaire

1. [Métriques suivies et seuils d'alerte](#métriques-suivies-et-seuils-dalerte)
2. [Pourquoi Prometheus, Grafana et loguru](#pourquoi-prometheus-grafana-et-loguru)
3. [Logs applicatifs conservés et pourquoi](#logs-applicatifs-conservés-et-pourquoi)
4. [Installation et configuration en local](#installation-et-configuration-en-local)
5. [Canal d'alerte](#canal-dalerte)
6. [Architecture](#architecture)
7. [Utiliser le dashboard](#utiliser-le-dashboard)

## Métriques suivies et seuils d'alerte

Définies dans [`src/tomatoscan/api/metrics.py`](../src/tomatoscan/api/metrics.py),
incrémentées dans [`src/tomatoscan/api/routes/predict.py`](../src/tomatoscan/api/routes/predict.py)
à chaque appel à `POST /predict`.

| Métrique | Type | Ce qu'elle mesure | Seuil d'alerte |
|---|---|---|---|
| `tomatoscan_errors_total` | Counter (label `type_erreur`) | Erreurs sur `/predict` par type (`format_invalide`, `image_corrompue`, `erreur_prediction`, `modele_indisponible`) — distingue une erreur côté client d'une panne côté serveur/modèle | **`sum(rate(...[5m])) > 0.1` req/s pendant 1 min continue** — voir justification ci-dessous |
| `tomatoscan_prediction_duration_seconds` | Histogram | **Durée d'inférence** MobileNetV2 (percentiles p50/p95) — le chronomètre n'encadre que l'appel à `model_service.predire()` dans [`routes/predict.py`](../src/tomatoscan/api/routes/predict.py) : ce n'est **pas** la latence HTTP de bout en bout de `POST /predict` (validation du fichier, lecture du corps de requête et sérialisation de la réponse en sont exclues) | Aucun — surveillé visuellement sur le dashboard (courbe p50/p95), pas d'alerte : une durée d'inférence élevée isolée n'est pas nécessairement un incident (image plus lourde, pic de charge ponctuel), contrairement à un taux d'erreurs soutenu |
| `tomatoscan_predictions_total` | Counter (labels `classe` **et** `statut`) | Nombre de prédictions par classe MobileNetV2 détectée et par statut (`succes` — seule valeur émise à ce jour, les échecs étant comptés par `tomatoscan_errors_total`) | Aucun — un déséquilibre de distribution demande une lecture humaine du contexte (saison, campagne de collecte), pas un seuil fixe |
| `tomatoscan_prediction_confidence` | Histogram (buckets `0.5`→`1.0`) | Distribution des scores de confiance des prédictions réussies — une baisse continue peut signaler une dérive du modèle ou des images hors distribution | Aucun — même raison que ci-dessus ; ce n'est pas un signal de réentraînement automatique (voir avertissement en tête de ce document) |

**Justification du seuil de la seule alerte active** (`> 0.1 req/s` sur 5 min,
déclenchement après 1 min continue) : 0.1 req/s correspond à environ une erreur
toutes les 10 secondes en moyenne sur la fenêtre — suffisant pour distinguer un
problème réel et soutenu (modèle en panne, dépendance indisponible) d'un pic isolé
(un seul utilisateur envoyant une mauvaise image, qui ne dépasse pas ce taux
moyenné sur 5 minutes). Le délai `for: 1m` évite de déclencher sur une seule
évaluation ponctuelle juste au-dessus du seuil. Ce même seuil est repris
visuellement sur le panneau « Erreurs / seconde » du dashboard (vert < 0.05, jaune
0.05–0.1, rouge > 0.1 req/s), pour que l'écart soit visible avant même que
l'alerte se déclenche.

Aucun seuil n'est posé sur les trois autres métriques : un seuil fixe universel
sur la confiance ou la latence produirait plus de faux positifs que de vrais
signaux pour un projet de cette taille — elles restent surveillées à l'œil sur le
dashboard plutôt qu'en alerte automatique.

## Pourquoi Prometheus, Grafana et loguru

**Prometheus + Grafana**, plutôt qu'un service SaaS (Datadog, New Relic) ou une
stack plus lourde (ELK, Loki) :
- **Open source et auto-hébergeable** sur le même VPS OVH que le reste du projet —
  cohérent avec le choix éco-responsable déjà documenté dans
  [docs/architecture.md](architecture.md#éco-conception) (pas de dépendance à une
  plateforme cloud tierce), et sans coût récurrent.
- **Alerting intégré** : Grafana Unified Alerting évalue les règles et route les
  notifications sans outil supplémentaire (pas besoin d'un Alertmanager séparé,
  pas besoin de Loki pour agréger des logs alors que `docker logs`/Coolify le font
  déjà pour un déploiement mono-instance comme celui-ci).
- **Standard de facto** pour le monitoring d'API Python/FastAPI : bibliothèque
  cliente officielle (`prometheus_client`), format texte simple à exposer
  (`GET /metrics/`), documentation abondante — pas de courbe d'apprentissage
  disproportionnée pour la taille du projet.
- **Provisioning déclaratif** (fichiers YAML versionnés pour dashboards,
  datasources, règles d'alerte, points de contact, politique de notification) :
  aucune configuration cliquée à la main dans l'UI. Ce qui a été **réellement
  vérifié en local** : au démarrage, Grafana charge bien les quatre fichiers de
  provisioning et l'API d'administration renvoie ensuite la datasource, le
  dashboard, la règle d'alerte, le point de contact `email-tomatoscan` et la
  politique de routage attendus. La configuration de préprod/prod n'a **pas** été
  comparée poste à poste à celle du local : les deux environnements partagent les
  mêmes fichiers versionnés et les mêmes images Docker, mais diffèrent par leurs
  valeurs de `.env` (SMTP, destinataire d'alerte, mot de passe admin) et par la
  publication des ports (voir [Installation](#installation-et-configuration-en-local)).

**loguru**, plutôt qu'un stack de logs séparé (ELK, Loki, un service cloud) :
- Bibliothèque Python native, zéro configuration pour un usage correct par
  défaut (contrairement au module `logging` standard, plus verbeux à configurer).
- Déjà adoptée dans tout `src/tomatoscan/` avant même ce lot de travail — rester
  dessus évite d'introduire une deuxième façon de logger dans le même projet.
- Un déploiement conteneurisé (Docker/Coolify) centralise déjà la sortie standard
  des conteneurs (`docker logs`) : un agrégateur de logs dédié (Loki, ELK)
  ajouterait un service de plus à maintenir sans bénéfice proportionné pour un
  projet à cette échelle — c'est un choix de simplicité assumé, pas un manque
  (détaillé juste en dessous).

## Logs applicatifs conservés et pourquoi

Complémentaires aux métriques : une métrique dit *qu'il y a eu* une erreur, un
log dit *laquelle*, *pour qui*, et *pourquoi*.

| Catégorie de log | Fichier | Risque/question qu'il permet de surveiller |
|---|---|---|
| Connexions réussies/échouées, avec compteur d'échecs consécutifs | `routes/auth.py` | Tentative de brute-force ou de credential stuffing sur un compte précis ; distingue une simple erreur de frappe d'un pattern d'attaque |
| Erreurs de prédiction : format invalide, image corrompue, échec du modèle, modèle indisponible | `routes/predict.py` | Sépare un problème côté utilisateur (mauvais fichier envoyé) d'une vraie panne côté serveur/modèle — sans ça, impossible de savoir si un pic d'erreurs vient des utilisateurs ou de l'infrastructure |
| Erreurs de lecture BDD/CSV | `routes/history.py`, `routes/reports.py` | Dépendance externe indisponible ou fichier de rapport manquant/corrompu — utile pour distinguer un bug applicatif d'un problème d'infrastructure (BDD down, disque plein) |
| Toute exception non prévue ailleurs | `main.py::gestionnaire_erreur_generique` | Filet de sécurité : un bug réel jamais anticipé par le code existant (donc jamais couvert par les trois catégories ci-dessus) ne doit jamais passer complètement inaperçu |

**Configuration retenue : sortie standard uniquement, pas de fichier, pas de
rotation, pas de niveau personnalisé** — choix assumé, pas un oubli. Sur un
déploiement conteneurisé, `docker logs`/Coolify centralisent déjà la sortie
standard de chaque conteneur ; ajouter un fichier avec rotation dupliquerait ce
que la plateforme fait déjà, pour un bénéfice nul à l'échelle de ce projet. Une
configuration plus élaborée (niveaux par module, sinks multiples) serait de la
complexité sans problème réel à résoudre ici.

## Installation et configuration en local

### En production / préprod (Coolify)

Prometheus et Grafana sont déjà définis comme services dans `docker-compose.yml` et
se déploient automatiquement avec le reste de la stack (`just up` ou déploiement
Coolify sur push `develop`/`main`). Rien à installer séparément.

Variables requises dans `.env` (voir `.env.example`) :

| Variable | Rôle |
|---|---|
| `GRAFANA_PASSWORD` | Mot de passe du compte admin Grafana |
| `GRAFANA_URL` | URL affichée par le bouton « Ouvrir le monitoring » du tableau de bord admin (frontend) |
| `ALERTES_EMAIL_DESTINATAIRE` | Adresse qui reçoit les alertes — lue par `contact_points.yml` |
| `GF_SMTP_ENABLED` | Active l'envoi d'e-mails par Grafana (`false` par défaut : la règle se déclenche mais ne notifie pas) |
| `GF_SMTP_HOST` | Serveur SMTP, au format `hote:port` |
| `GF_SMTP_USER` / `GF_SMTP_PASSWORD` | Identifiants SMTP |
| `GF_SMTP_FROM_ADDRESS` / `GF_SMTP_FROM_NAME` | Expéditeur affiché dans les e-mails d'alerte |

Ces variables sont transmises au conteneur `grafana` par `docker-compose.yml`
(section `environment` du service) — voir [Canal d'alerte](#canal-dalerte).

### En local (développement)

Prérequis unique, à faire une seule fois par machine : les services `prometheus`
et `grafana` de `docker-compose.yml` référencent un réseau Docker externe
`coolify` (créé automatiquement par Coolify sur le VPS, mais pas par
`docker compose up` seul). Sur un poste de développement qui n'a jamais eu
Coolify, ce réseau n'existe pas encore :

```bash
docker network create coolify
```

Cette commande échoue avec un message explicite (`network with name coolify
already exists`) si le réseau existe déjà — sans danger de le relancer par erreur.

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

[`docker-compose.local.yml`](../docker-compose.local.yml) est versionné dans le
dépôt (pas un fichier à recréer soi-même). Son unique rôle est de **publier vers
l'hôte** les ports de Prometheus (`9090`) et de Grafana (`3000`) : `docker-compose.yml`
ne les publie jamais, car en préprod et en production ces deux services restent
volontairement joignables uniquement depuis le réseau Docker interne `coolify`.
Sans cette surcouche, `docker compose ps` affiche `9090/tcp` et `3000/tcp` sans
mapping, et `curl localhost:9090` ne répond pas. Coolify ne charge jamais ce
fichier : il faut le demander explicitement avec `-f`.

Attention à deux pièges vérifiés en local :
- **`--build` est nécessaire après toute modification de `monitoring/`.** Les
  fichiers de provisioning sont copiés dans l'image au build
  (`COPY grafana/provisioning …` dans `monitoring/Dockerfile.grafana`), pas montés
  en volume : sans reconstruction, Grafana redémarre avec l'ancienne configuration.
- **Passer `-f` désactive le chargement automatique de `docker-compose.override.yml`**
  (préprod). Pour reproduire la préprod en local, l'ajouter explicitement :
  `docker compose -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.local.yml up --build`.

Accès local :
- Prometheus : http://localhost:9090
- Grafana : http://localhost:3000 (login `admin`, mot de passe `GRAFANA_PASSWORD`)

Cet environnement local sert de bac à sable avant tout déploiement, utilisé pour
de vrai à deux reprises :
- **2026-07-07** : le dashboard Grafana provisionné au build se retrouvait vide
  après redémarrage — la configuration était masquée par le volume persistant
  `grafana_data` (voir [docs/agile.md](agile.md)). Diagnostiqué et corrigé en
  local avant toute mise en production.
- **2026-07-20** : le démarrage local de la stack de monitoring a révélé trois
  défauts que la seule relecture du YAML n'avait pas fait apparaître — les
  fichiers `contact_points.yml` et `policies.yml` étaient absents (l'alerte se
  déclenchait sans notifier personne), la condition de seuil de la règle d'alerte
  n'était pas réductible, et les ports n'étaient publiés vers l'hôte par aucun
  fichier Compose. Voir [Canal d'alerte](#canal-dalerte).

## Canal d'alerte

L'alerte « Taux d'erreurs TomatoScan élevé » est routée vers un point de contact
**e-mail**
([`contact_points.yml`](../monitoring/grafana/provisioning/alerting/contact_points.yml)
+ [`policies.yml`](../monitoring/grafana/provisioning/alerting/policies.yml)),
provisionné automatiquement comme le reste (pas de configuration manuelle dans
l'UI). Choix de l'e-mail plutôt que Slack/Telegram/webhook : c'est le canal le
plus simple à mettre en place avec Grafana (SMTP standard intégré, pas de compte
tiers ni d'application à créer), suffisant pour un projet avec un seul
destinataire et une seule règle d'alerte — pas besoin de routage plus fin par
sévérité ou par équipe.

L'adresse de destination n'est jamais écrite en dur dans le dépôt :
`contact_points.yml` lit la variable d'environnement `${ALERTES_EMAIL_DESTINATAIRE}`,
passée au conteneur `grafana` par `docker-compose.yml` et définie dans `.env`
(voir `.env.example`). Grafana interpole les variables d'environnement dans les
fichiers de provisioning à son démarrage.

### Correction d'une règle d'alerte non évaluable

La condition de seuil de `alertes.yml` s'appliquait directement à la requête
Prometheus `A`, une série temporelle. Grafana Unified Alerting exige que la
condition d'une règle produise **une valeur unique par série**, pas une série
entière (« *only reduced data can be alerted on* »).

Un nœud de réduction `refId: B` (`type: reduce`, `reducer: last`, `expression: A`)
a donc été inséré entre la requête et le seuil, et la condition `C` pointe
désormais sur `B` plutôt que sur `A`. Le champ `reducer:` qui figurait auparavant
dans le bloc `conditions` de `C` a été retiré : c'est un vestige de la syntaxe
`classic_conditions`, sans effet sur un nœud de type `threshold`.

Ce qui a été **vérifié en local** sur cette chaîne (Grafana 13.1.0) :
- la règle est bien provisionnée avec les trois nœuds `A → B → C`, et Grafana
  l'évalue en boucle sans erreur (`lastError` vide sur l'API des règles) ;
- en soumettant la chaîne à l'endpoint d'évaluation de Grafana avec une requête
  de test au-dessus du seuil, `B` renvoie bien une valeur scalaire unique et `C`
  renvoie `1` (condition remplie) ;
- soumise à la même évaluation, l'ancienne configuration (seuil directement sur
  `A`) renvoyait pour `C` une série de 301 points au lieu d'un scalaire — soit
  exactement la forme de données qu'une règle d'alerte ne peut pas évaluer.

**Limite assumée** : aucun trafic d'erreurs réel n'a été rejoué contre l'API pour
observer le cycle complet jusqu'à la réception d'un e-mail. Le seuil dépassé, la
transition d'état `pending → firing` et la remise effective du message par le
serveur SMTP restent à confirmer en conditions réelles.

Une chose reste donc à faire avant que les e-mails partent réellement (la règle et
le routage sont en place entre-temps ; seule la remise sortante est concernée) :
renseigner un vrai serveur SMTP et un vrai destinataire dans `.env`
(`GF_SMTP_ENABLED=true`, `GF_SMTP_HOST`, `GF_SMTP_USER`, `GF_SMTP_PASSWORD`,
`GF_SMTP_FROM_ADDRESS`, `GF_SMTP_FROM_NAME`, `ALERTES_EMAIL_DESTINATAIRE` — voir
`.env.example`). Avec la valeur par défaut `GF_SMTP_ENABLED=false`, la règle
s'évalue et se déclenche normalement dans Grafana, mais aucune notification ne
part.

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

## Utiliser le dashboard

1. Se connecter à Grafana (voir [Installation](#installation-et-configuration-en-local)).
2. Le dashboard **TomatoScan — Monitoring** est provisionné automatiquement — pas
   besoin de l'importer manuellement.
3. Rafraîchissement automatique toutes les 30 secondes, fenêtre par défaut : dernière heure.

Panneaux disponibles :

| Panneau | Ce qu'il montre |
|---|---|
| Prédictions / seconde | Débit instantané de prédictions réussies (moyenne 5 min) |
| Prédictions totales | Compteur cumulé depuis le démarrage du service |
| Erreurs / seconde | Taux d'erreurs, coloré selon le seuil d'alerte (vert/jaune/rouge) |
| Durée d'inférence — MobileNetV2 | Percentiles p50 (médiane) et p95 de la durée d'inférence du modèle (hors latence HTTP de la requête) |
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

**Accessibilité de l'outil de restitution** : Grafana est une interface web standard
navigable au clavier, avec thèmes clair/sombre configurables. L'accès étant réservé
aux comptes admin (voir ci-dessus), le public concerné par ce critère se limite à
l'administrateur du projet — aucun audit WCAG dédié n'a été mené sur l'interface
Grafana elle-même (outil tiers, hors du code de ce projet) ; c'est une limite assumée,
pas un point vérifié.

---

*Accessibilité : document Markdown structuré par hiérarchie de titres (H1→H3), tableaux avec en-têtes de colonnes, aucune information portée uniquement par la couleur ; lisible par un lecteur d'écran et navigable au clavier depuis GitHub. Le Markdown brut est le format standard de la documentation technique développeur — aucune mise en forme visuelle propriétaire (police, couleur de fond, contraste personnalisé) à justifier séparément : le rendu (contraste, navigation clavier, lecteur d'écran) est entièrement délégué à la plateforme d'hébergement (GitHub), déjà conforme aux standards d'accessibilité web usuels.*
