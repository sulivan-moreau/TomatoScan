# Plan de tests et couverture — TomatoScan

Ce document décrit la stratégie de test du projet TomatoScan : cas testés, périmètre,
stratégie de mock, procédure d'installation, exécution et couverture.

Ferme le ticket [#21 — docs: plan de tests et rapport de couverture](https://github.com/sulivan-moreau/tomatoscan/issues/21).

## Sommaire

1. [Vue d'ensemble](#vue-densemble)
2. [Installation de l'environnement de test](#installation-de-lenvironnement-de-test)
3. [Exécution des tests et calcul de couverture](#exécution-des-tests-et-calcul-de-couverture)
4. [Génération du rapport de couverture HTML](#génération-du-rapport-de-couverture-html)
5. [Liste des cas testés](#liste-des-cas-testés)

## Vue d'ensemble

| Élément | Valeur |
|---|---|
| Nombre total de tests | 104 |
| Framework | pytest + pytest-asyncio (mode auto) |
| Couverture globale mesurée (`--cov=src/tomatoscan`) | ~83 % (tout le paquet : API + modèle + frontend + BDD) |
| Couverture API mesurée (`--cov=src/tomatoscan/api`) | ~78 % (seuil CI : 75 %) |
| Couverture modèle mesurée (`--cov=src/tomatoscan/model`) | ~85 % (seuil CI : 80 %) |
| Base de données de test | SQLite en mémoire (aiosqlite), l'application cible PostgreSQL/asyncpg en dev/préprod/prod |
| Modèle réel (poids MobileNetV2) | Jamais chargé en test — entièrement mocké |

Les trois chiffres de couverture mesurent des périmètres différents et ne sont pas
interchangeables : **~74 % est la couverture globale** du paquet `src/tomatoscan`
(commande d'en-tête de la section [couverture](#exécution-des-tests-et-calcul-de-couverture)),
tandis que les ~78 % et ~85 % sont des mesures **scopées** sur les seuls sous-arbres
`api/` et `model/`. La couverture globale reste légèrement en deçà de ces deux-là
parce qu'elle inclut en plus les points d'entrée / scripts moins couverts par les tests
unitaires (CLI d'entraînement, `__main__`) ; le frontend Streamlit (`front/`) est
désormais largement couvert en bout-en-bout via `AppTest` (pages `history`, `dashboard`,
`predict`, navigation par rôle). Les deux
seuils CLI appliqués en CI (`--cov-fail-under`) portent volontairement sur les périmètres
scopés (75 % API, 80 % modèle) — voir la justification en fin de section couverture.

Répartition par domaine :

| Domaine | Fichiers | Nombre de tests |
|---|---|---|
| API (auth, sécurité, routes) | `tests/test_api/*.py` | 39 |
| Modèle (prétraitement, entraînement, évaluation) | `tests/test_model/*.py` | 24 |
| Frontend (client API, pages métier, navigation, gestion 401, régression JWT) | `tests/test_frontend/*.py` | 39 |
| Base de données (modèles SQLAlchemy) | `tests/test_database/*.py` | 2 |

Deux principes appliqués sur l'ensemble de la suite :

- **Un test nominal + un test d'erreur obligatoire par fonction**, pas de variantes
  multiples d'un même scénario — évite le gonflement artificiel du nombre de tests
  sans gain de couverture réel.
- **Exception explicite** : une régression de bug réel (bug trouvé puis corrigé
  pendant l'écriture des tests) reste toujours testée, même si elle dépasse la règle
  ci-dessus — c'est le cas par exemple de `test_afficher_confusion_matrix_classe_absente_ne_plante_plus`
  ou `test_token_sans_role_rejete_en_401_pas_devine_en_agriculteur`.

## Installation de l'environnement de test

Prérequis : Python 3.11+, [uv](https://docs.astral.sh/uv/) installé.

```bash
# Cloner le repo puis, à la racine du projet :
uv sync --extra dev
```

Dépendances de test installées par ce groupe (`pyproject.toml`, `[project.optional-dependencies].dev`) :

| Paquet | Rôle |
|---|---|
| `pytest` | Framework de test |
| `pytest-asyncio` | Support des tests `async def` (routes FastAPI async) |
| `httpx` | Client HTTP async utilisé par les tests d'API (`AsyncClient`) |
| `pytest-cov` | Mesure de couverture (`--cov`) |
| `ruff` | Lint + formatage (vérifiés en CI, pas des tests à proprement parler) |
| `aiosqlite` | Pilote SQLite async — base de test uniquement, jamais utilisé en production |

Variables d'environnement nécessaires pour lancer les tests API en local (voir `.env.example`) :
`SECRET_KEY`, `ALGORITHM`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `DATABASE_URL` (une base
SQLite locale suffit, ex. `sqlite+aiosqlite:///./test.db`), `MODEL_PATH` (peut pointer
vers un fichier inexistant — les tests mockent le service modèle).

## Exécution des tests et calcul de couverture

```bash
# Suite complète avec couverture (équivalent à `just test`)
uv run pytest tests/ -v --cov=src/tomatoscan --cov-report=term-missing

# Uniquement l'API, avec le seuil appliqué en CI (échoue si < 75 %)
uv run pytest tests/ --cov=src/tomatoscan/api --cov-report=term-missing --cov-fail-under=75

# Uniquement le modèle, avec son seuil dédié (échoue si < 80 %) — pas de raccourci `just`
# dédié pour cette commande, utilisée directement telle quelle
uv run pytest tests/test_model/ --cov=src/tomatoscan/model --cov-report=term-missing --cov-fail-under=80
```

Ces trois commandes sont exactement celles exécutées par la CI (`.github/workflows/ci-app.yml`,
étapes « Tests (pytest + couverture) » et « Couverture du modèle (seuil dédié) ») — voir
[docs/ci_application.md](ci_application.md). Les deux seuils sont volontairement distincts
(75 % API / 80 % modèle) plutôt qu'un seuil unique combiné : chaque composant a une
couverture réelle différente, un seuil combiné masquerait une régression sur l'un des deux.

**Justification des valeurs retenues (75 % / 80 %)** : chaque seuil est fixé légèrement
en dessous de la couverture réellement mesurée au moment où il a été posé (78,15 %
mesuré sur l'API, seuil 75 % ; 84,86 % mesuré sur le modèle, seuil 80 %) — une marge
volontaire de quelques points, pas la couverture exacte, pour que `--cov-fail-under`
échoue sur une vraie régression sans casser la CI au moindre arrondi entre deux runs.
Ce ne sont pas des objectifs arbitraires (ex. "80 % partout" par convention) : ils
reflètent la couverture atteinte après la passe de réduction des tests redondants
(voir [docs/agile.md](agile.md)), pas un chiffre fixé a priori puis atteint en gonflant
artificiellement le nombre de tests.

## Génération du rapport de couverture HTML

```bash
uv run pytest tests/ --cov=src/tomatoscan --cov-report=html
open htmlcov/index.html   # macOS ; xdg-open sur Linux, start sur Windows
```

Le rapport HTML détaille, fichier par fichier et ligne par ligne, ce qui est couvert ou
non — plus lisible qu'un rapport terminal pour explorer la couverture en détail. Le
dossier `htmlcov/` est généré localement et n'est jamais versionné (voir `.gitignore`) :
c'est un artifact reproductible à la demande via la commande ci-dessus, pas une source.

## Liste des cas testés

### API — `tests/test_api/`

| Fichier | Cas testé | Périmètre / stratégie |
|---|---|---|
| `test_auth.py` | `test_login_valide` | Connexion avec identifiants corrects → token émis |
| `test_auth.py` | `test_login_invalide` | Mauvais mot de passe → 401 |
| `test_auth.py` | `test_session_courante_avec_token` | `GET /auth/me` avec token valide → identité retournée |
| `test_auth.py` | `test_session_courante_sans_token` | `GET /auth/me` sans token → 401 |
| `test_auth.py` | `test_predict_sans_token_ou_avec_token_invalide` | Route protégée sans/avec mauvais token → 401 |
| `test_auth.py` | `test_refresh_token_valide_retourne_un_nouveau_token` | `POST /auth/refresh` avec token valide → nouveau token, mêmes claims |
| `test_auth.py` | `test_refresh_sans_token` | `POST /auth/refresh` sans token → 401 |
| `test_auth.py` | `test_refresh_token_expire` | `POST /auth/refresh` avec token expiré → 401 (pas de renouvellement d'un token déjà expiré) |
| `test_health.py` | `test_health_repond_200_avec_le_bon_corps` | `GET /health` → 200 + corps attendu |
| `test_health.py` | `test_app_demarre_sans_erreur` | L'application FastAPI s'instancie sans lever d'exception |
| `test_history.py` | `test_history_sans_token` | `GET /predictions/history` sans token → 401 |
| `test_history.py` | `test_history_avec_token` | Avec token valide → 200 + liste (vide au départ) |
| `test_history.py` | `test_history_apres_prediction` | Après une prédiction → celle-ci apparaît dans l'historique |
| `test_history.py` | `test_history_filtree_par_role` | Un agriculteur ne voit que ses propres prédictions, un admin voit tout |
| `test_metrics.py` | `test_metrics_url_scrapee_par_prometheus_expose_les_metriques_attendues` | `GET /metrics/` (URL réellement scrapée par Prometheus) expose les métriques attendues |
| `test_predict.py` | `test_predict_image_valide_retourne_la_maladie_detectee` | Image valide → classe prédite + confiance |
| `test_predict.py` | `test_predict_image_corrompue` | Fichier non-image → 400 |
| `test_predict.py` | `test_predict_modele_indisponible` | Modèle non chargé → erreur explicite, pas un plantage silencieux |
| `test_predict.py` | `test_predict_rejette_avant_le_modele` | Requête invalide rejetée avant tout appel au modèle (validation en amont) |
| `test_reports.py` | `test_reports_sans_token` | `GET /reports` sans token → 401 |
| `test_reports.py` | `test_reports_avec_token` | Avec token valide → 200 + contenu du CSV d'historique d'entraînement |
| `test_reports.py` | `test_reports_fichier_introuvable` | CSV absent → erreur explicite, pas de 500 non géré |
| `test_security.py` | `test_headers_securite` | Présence des en-têtes de sécurité HTTP attendus sur les réponses |
| `test_security.py` | `test_rate_limiting` | Le rate limiting (slowapi) se déclenche au-delà du débit autorisé |
| `test_security.py` | `test_5_echecs_consecutifs_bloquent_meme_si_le_debit_reste_bas` | Verrouillage après 5 échecs de connexion consécutifs, même sous le seuil de débit |
| `test_security.py` | `test_connexion_reussie_reinitialise_le_compteur_d_echecs` | Une connexion réussie remet à zéro le compteur d'échecs consécutifs |
| `test_security_edge.py` | `test_token_sans_secret_key` | `SECRET_KEY` absente de l'environnement → 401 sur validation, `RuntimeError` sur création |
| `test_security_edge.py` | `test_token_sans_sub` | Token signé valide mais sans claim `sub` → 401 |
| `test_security_edge.py` | `test_token_sans_role_rejete_en_401_pas_devine_en_agriculteur` | Token signé valide mais sans claim `role` → 401 explicite (régression : ancien comportement devinait silencieusement `"agriculteur"`) |
| `test_users.py` | `test_agriculteur_recoit_403_sur_toutes_les_routes_users` | Un agriculteur (non-admin) reçoit 403 sur `/users` |
| `test_users.py` | `test_admin_peut_lister_creer_et_supprimer_des_utilisateurs` | Cycle complet CRUD utilisateurs côté admin |
| `test_users.py` | `test_creation_avec_username_deja_pris_retourne_409` | Doublon de username → 409 |
| `test_users.py` | `test_creation_avec_mot_de_passe_trop_court_retourne_422` | Mot de passe sous la longueur minimale → 422 |
| `test_users.py` | `test_admin_ne_peut_pas_se_supprimer_lui_meme` | Un admin ne peut pas supprimer son propre compte → 400 |
| `test_users.py` | `test_suppression_bloquee_si_utilisateur_a_des_predictions` | Suppression bloquée si l'utilisateur a des prédictions enregistrées → 409 |

Stratégie commune API : `httpx.AsyncClient` contre l'application FastAPI réelle (pas
de mock du framework), service modèle mocké (`unittest.mock.patch` sur `model_service`)
— jamais de poids MobileNetV2 réels chargés. La base de test est une **unique** base
SQLite en mémoire (aiosqlite + `StaticPool`), créée une seule fois par session
(`tests/conftest.py`, fixture `_preparer_bdd_test` en `scope="session"`) et **partagée
par tous les tests** — et non une base dédiée par test. Deux garde-fous préservent
l'isolation et l'idempotence de la suite : (1) les tables sont supprimées (`drop_all`)
au teardown de la session, et (2) chaque test créant un compte agriculteur génère un
`username` unique via `uuid4()`. Conséquence : deux exécutions consécutives contre une
base **persistante** réutilisée (fichier SQLite en local, ou service PostgreSQL de la
CI) donnent le même résultat, sans collision « username déjà pris » ni historique
résiduel d'un run à l'autre.

### Modèle — `tests/test_model/` (compétence C12)

| Fichier | Cas testé | Périmètre / stratégie |
|---|---|---|
| `test_donnees.py` | `test_obtenir_classes_tomates_filtre_correctement` | Filtrage des classes "Tomato" parmi le dataset complet |
| `test_donnees.py` | `test_obtenir_classes_tomates_dossier_introuvable` | Dossier dataset absent → erreur explicite |
| `test_donnees.py` | `test_dataset_fichier_corrompu_leve_une_erreur_non_geree` | Fichier image corrompu dans le dataset → erreur propagée, pas silencieuse |
| `test_donnees.py` | `test_mapping_labels_est_coherent` | Le mapping nom de classe ↔ index label reste cohérent |
| `test_donnees.py` | `test_charger_dataset_couvre_toutes_les_classes_et_toutes_les_images` | Toutes les classes et images du dataset factice sont bien chargées |
| `test_preprocessing.py` | `test_transform_nominal_produit_un_tensor_224x224_deterministe` | `creer_transforms()` sans augmentation → tensor 224×224 déterministe |
| `test_preprocessing.py` | `test_normalisation_imagenet` | Normalisation avec les moyennes/écarts-types ImageNet appliquée correctement |
| `test_preprocessing.py` | `test_transform_avec_augmentation_produit_un_tensor_valide` | Avec augmentation activée → tensor toujours valide (forme, plage de valeurs) |
| `test_train.py` | `test_selectionner_device_mps_disponible` | MPS (Apple Silicon) détecté → device `mps` sélectionné |
| `test_train.py` | `test_selectionner_device_cpu_par_defaut` | MPS indisponible → repli sur `cpu` |
| `test_train.py` | `test_construire_modele_gele_la_base_et_remplace_le_classifier` | Base MobileNetV2 gelée (`requires_grad=False`), classifier remplacé et entraînable |
| `test_train.py` | `test_executer_epoch_entrainement_appelle_forward_backward_step_par_batch` | Mode entraînement : forward/backward/step déclenchés à chaque batch |
| `test_train.py` | `test_executer_epoch_validation_n_appelle_jamais_backward_ni_optimizer` | Mode validation : aucun backward ni optimizer.step() |
| `test_train.py` | `test_sauvegarder_historique_ecrit_un_csv_correct` | L'historique d'entraînement est écrit dans un CSV correctement formé |
| `test_train.py` | `test_entrainer_modele_orchestration_complete` | Orchestration complète : nombre d'appels par epoch, config optimizer/scheduler, contenu du checkpoint sauvegardé |
| `test_train.py` | `test_entrainer_modele_early_stopping_sauvegarde_uniquement_aux_ameliorations` | Early stopping après 3 dégradations consécutives ; sauvegarde uniquement aux améliorations de val_loss |
| `test_evaluate.py` | `test_charger_checkpoint_extrait_les_bons_champs` | Chargement d'un checkpoint → bons champs extraits (poids, classes, accuracy) |
| `test_evaluate.py` | `test_executer_inference_collecte_labels_reels_et_predictions` | Inférence sur un jeu de données → labels réels et prédits correctement collectés |
| `test_evaluate.py` | `test_afficher_confusion_matrix_produit_une_matrice_dix_par_dix` | `afficher_confusion_matrix()` (fonction du projet) construit et normalise une matrice de confusion 10×10 couvrant les 10 classes — forme et proportions vérifiées via l'appel intercepté à `imshow()`, pas via un appel direct à sklearn |
| `test_evaluate.py` | `test_afficher_confusion_matrix_classe_absente_ne_plante_plus` | Régression : classe absente des labels réels/prédits ne fait plus planter `confusion_matrix()` |
| `test_evaluate.py` | `test_generer_rapport_calcule_l_accuracy_et_liste_les_classes_sous_performantes` | Le rapport JSON calcule l'accuracy et liste les classes sous le seuil F1 |
| `test_evaluate.py` | `test_generer_rapport_classe_totalement_absente_ne_plante_plus` | Régression : classe totalement absente du jeu de test ne fait plus planter `classification_report()` |
| `test_evaluate.py` | `test_verifier_seuil_reentrainement` | Détection du franchissement du seuil d'accuracy déclenchant une alerte de réentraînement |
| `test_evaluate.py` | `test_journaliser_declenchement_ecrit_puis_accumule_sans_dupliquer_l_en_tete` | Le journal CSV de déclenchement accumule les lignes sans dupliquer l'en-tête |

Stratégie commune modèle : jamais de poids MobileNetV2/ImageNet réels ni de dataset
PlantVillage réel. `construire_modele()` mocke la base pré-entraînée par un faux
`nn.Module` minimal ; `executer_epoch()`/`entrainer_modele()` mockent modèle,
optimizer et scheduler mais laissent les vrais tenseurs PyTorch circuler (accuracy,
loss calculés réellement) ; les fixtures de `tests/test_model/conftest.py` génèrent
des images factices en mémoire.

### Frontend — `tests/test_frontend/` (compétence C10)

| Fichier | Cas testé | Périmètre / stratégie |
|---|---|---|
| `test_api_client.py::TestLogin` | `test_login_extrait_le_token_et_envoie_les_bons_identifiants` | Connexion : bons identifiants envoyés, token extrait de la réponse |
| `test_api_client.py::TestLogin` | `test_login_identifiants_invalides_leve_apierror_401` | Identifiants invalides → `ApiError` avec code 401 |
| `test_api_client.py::TestSessionCourante` | `test_me_retourne_la_session_avec_le_bon_header` | `GET /auth/me` appelé avec le header Authorization correct |
| `test_api_client.py::TestListUsers` | `test_list_users_retourne_la_liste_et_le_bon_header` | Récupération de la liste des utilisateurs, header d'auth correct |
| `test_api_client.py::TestCreateUser` | `test_create_user_envoie_les_bons_identifiants` | Création d'utilisateur : bon payload envoyé à l'API |
| `test_api_client.py::TestDeleteUser` | `test_delete_user_appelle_le_bon_endpoint` | Suppression : bon endpoint/méthode appelés |
| `test_api_client.py::TestGetHistory` | `test_get_history_retourne_la_liste_des_predictions` | Historique des prédictions récupéré et formaté |
| `test_api_client.py::TestGetReports` | `test_get_reports_retourne_le_rapport_d_entrainement` | Rapport d'entraînement du modèle récupéré via `GET /reports` (consommé par `pages/dashboard.py`) |
| `test_api_client.py::TestGetReports` | `test_get_reports_401_leve_apierror` | 401 sur `GET /reports` → `ApiError` avec code 401 |
| `test_api_client.py::TestPing` | `test_ping_retourne_true_si_l_api_repond` | `ping()` : `GET /health` répond 2xx → `True` |
| `test_api_client.py::TestPing` | `test_ping_retourne_false_si_l_api_est_injoignable` | `ping()` : erreur réseau → `False` (jamais d'exception brute) |
| `test_api_client.py::TestPredict` | `test_predict_envoie_le_fichier_et_retourne_le_format_attendu` | Envoi d'image pour prédiction : fichier transmis, réponse au format attendu |
| `test_api_client.py::TestPredict` | `test_predict_401_leve_apierror_avec_le_detail_de_l_api` | 401 renvoyé par l'API → `ApiError` avec le détail transmis |
| `test_api_client.py::TestPredict` | `test_predict_erreur_reseau_leve_aussi_apierror` | Erreur réseau (timeout, connexion refusée) → `ApiError` aussi (pas d'exception non gérée) |
| `test_api_client.py::TestRenouvellementToken` | `test_refresh_token_retourne_le_nouveau_token` | `refresh_token()` retourne bien le nouveau token émis par l'API |
| `test_api_client.py::TestRenouvellementToken` | `test_renouveler_si_necessaire_selon_le_temps_restant` | Le renouvellement automatique ne se déclenche que si le temps restant passe sous le seuil |
| `test_api_client.py::TestDecodageJWT` | `test_decode_et_expiration` | Décodage du JWT côté frontend et calcul du temps restant avant expiration |
| `test_gestion_401.py::TestGestion401Factorisee` | `test_dashboard_401_vide_la_session` | Un 401 reçu sur une page vide bien la session (`st.session_state`) |
| `test_gestion_401.py::TestGestion401Factorisee` | `test_predict_erreur_400_n_efface_pas_la_session` | Une erreur 400 (métier) ne déclenche pas la déconnexion, contrairement à un 401 |
| `test_navigation_role.py` | `test_admin_a_acces_aux_pages_admin_et_a_la_section_administration` | Un admin connecté voit et accède aux pages/section admin |
| `test_navigation_role.py` | `test_agriculteur_est_bloque_sur_les_pages_admin` | Un agriculteur connecté est bloqué sur les pages admin |
| `test_navigation_role.py` | `test_changer_le_role_dans_le_token_change_immediatement_l_acces_affiche` | Un changement de rôle dans le token change immédiatement la navigation affichée |
| `test_regression_base64url.py` | 5 tests de régression (C21) | Verrouille la correction de l'incident de préproduction « rôle admin dégradé — décodage JWT base64 vs base64url » (voir [docs/incidents.md](incidents.md)) : `_decoder_payload_token()` (fonction du projet, déléguée à PyJWT) doit décoder une payload dont l'encodage base64url contient `-`/`_`, cas que l'ancien `base64.b64decode` corrompait silencieusement |

Stratégie commune frontend : `test_api_client.py` mocke tous les appels réseau
(`unittest.mock.patch` sur `requests.*`) — jamais de vraie requête HTTP.
`test_gestion_401.py` et `test_navigation_role.py` exécutent le vrai `app.py` et les
vraies pages via `streamlit.testing.v1.AppTest` (tests de bout en bout), seul
`requests` reste mocké.

### Base de données — `tests/test_database/`

| Fichier | Cas testé | Périmètre / stratégie |
|---|---|---|
| `test_modeles.py` | `test_creer_user` | Création d'un `User` SQLAlchemy, contraintes respectées |
| `test_modeles.py` | `test_creer_prediction` | Création d'une `Prediction` SQLAlchemy, relation avec `User` |

Stratégie : SQLite en mémoire, aucune dépendance à un PostgreSQL réel pour ces tests
unitaires (la CI teste par ailleurs les migrations Alembic contre un vrai PostgreSQL
— voir [docs/ci_application.md](ci_application.md)).


---

*Accessibilité : document Markdown structuré par hiérarchie de titres (H1→H3), tableaux avec en-têtes de colonnes, aucune information portée uniquement par la couleur ; lisible par un lecteur d'écran et navigable au clavier depuis GitHub. Le Markdown brut est le format standard de la documentation technique développeur — aucune mise en forme visuelle propriétaire (police, couleur de fond, contraste personnalisé) à justifier séparément : le rendu (contraste, navigation clavier, lecteur d'écran) est entièrement délégué à la plateforme d'hébergement (GitHub), déjà conforme aux standards d'accessibilité web usuels.*
