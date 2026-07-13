# Audit du frontend existant — issue #33, compétence C17

Audit en lecture seule de `src/tomatoscan/front/`. Aucune modification. Chaque fichier a été relu intégralement pour cet audit (pas de résumé basé sur le nom des fichiers).

---

## 1. Inventaire complet

| Fichier | Ce qu'il fait réellement (lu, pas supposé) |
|---|---|
| `app.py` | Point d'entrée Streamlit : configure la page, injecte le CSS custom (thème vert/rouge), affiche la sidebar (logo, statut API via `ping()`, nom d'utilisateur, bouton déconnexion), vérifie la validité du JWT à chaque rerun, et construit dynamiquement la liste des pages passées à `st.navigation()` selon la présence d'un token et le rôle en session. |
| `pages/login.py` | Formulaire de connexion (username + mot de passe) dans un `st.form`, appelle `api_client.login()`, stocke `token`/`username`/`role` en `session_state`, affiche un message si la session vient d'expirer (`session_expiree`). |
| `pages/predict.py` | Upload d'image (`st.file_uploader`), bouton "Analyser" qui appelle `api_client.predict()`, affiche un bandeau vert ("Tomate saine") ou rouge (maladie + libellé français + message API) et une barre de confiance en pourcentage. Gère spécifiquement 401/400/503. |
| `pages/history.py` | Récupère et affiche dans un tableau (`st.dataframe`) l'historique des prédictions de l'utilisateur connecté (date, fichier, maladie en français, confiance) via `GET /predictions/history`. Aucune métrique agrégée — uniquement la liste brute. |
| `pages/dashboard.py` | Réservée admin : lien vers Grafana, liste de tous les utilisateurs (`GET /users`) avec rôle/date de création, résumé chiffré (nb agriculteurs + nb prédictions total via `get_history()`, qui renvoie tout pour un admin grâce au filtrage serveur), et suppression de compte agriculteur avec confirmation à deux clics. |
| `pages/creer_membre.py` | Réservée admin : formulaire (username + mot de passe) qui appelle `POST /users` pour créer un compte agriculteur. |
| `utils/api_client.py` | Client HTTP unique vers l'API FastAPI — `ping`, `login`, `predict`, `get_history`, `list_users`, `create_user`, `delete_user`, `is_token_valid`, `obtenir_role`, `fr_label`. Toutes les erreurs HTTP/réseau remontent via une exception `ApiError` typée (avec `status_code`). |
| `components/__init__.py` | Vide — le dossier `components/` ne contient aucun composant, juste le marqueur de package. |
| `pages/__init__.py`, `front/__init__.py` | Vides, marqueurs de package uniquement. |
| `utils/__init__.py` | Un commentaire d'une ligne, marqueur de package. |
| `.streamlit/config.toml` | Thème natif Streamlit : `primaryColor=#2d6a4f`, `backgroundColor=#f6f8f6`, `secondaryBackgroundColor=#ffffff`, `textColor=#1b2420` — cohérent avec le CSS custom d'`app.py` (mêmes teintes). |
| `requirements.txt` | `streamlit>=1.36`, `requests>=2.31`, `pandas>=2.0`, `python-dotenv>=1.0` — dépendances du build Docker frontend, séparées de `pyproject.toml`. |
| `.env.example` | Non lu en détail ici (hors périmètre de l'audit frontend), présent pour la config locale du frontend. |

**Constat structurel** : `components/` existe en tant que dossier mais n'est jamais utilisé — toute la logique d'affichage est directement dans les fichiers `pages/*.py`, aucune extraction de composants réutilisables (ex. le bandeau résultat de `predict.py` ou le pattern de confirmation à deux clics de `dashboard.py` sont écrits en dur, non factorisés).

---

## 2. Couverture des tâches de l'issue #33

### Page d'accueil — **ABSENTE au sens strict**
Il n'existe aucune page "accueil"/"bienvenue" distincte. Le parcours réel est : non connecté → `login.py` (seule page visible) → connecté → **`predict.py` sert de landing page** (`default=True` dans `st.navigation`, `app.py:115`). Si l'issue attend une page de présentation/accueil séparée de la page d'analyse, elle n'existe pas. Si "page d'accueil" désigne juste "la première chose vue en arrivant", `login.py` en tient lieu pour un visiteur non connecté.

### Page upload image + résultat — **COUVERTE**
`predict.py` est complet : upload avec validation de type (`type=["jpg","jpeg","png"]`), aperçu de l'image, bouton désactivé tant qu'aucun fichier n'est choisi, appel API avec spinner, gestion différenciée de 401/400/503, affichage du résultat (classe traduite en français, message API, barre + pourcentage de confiance), et persistance du dernier résultat en session (`dernier_resultat`) pour survivre aux reruns Streamlit.

### Page dashboard historique + métriques — **PARTIELLEMENT COUVERTE, deux pages non reliées**
`history.py` et `dashboard.py` sont deux pages **totalement indépendantes**, avec des publics différents :
- `history.py` : accessible à **tout utilisateur connecté**, affiche uniquement **son propre** historique de prédictions (liste brute, aucune métrique calculée — pas de taux de réussite, pas de répartition par maladie, pas de graphique).
- `dashboard.py` : accessible **admin uniquement**, affiche des métriques (nb agriculteurs, nb prédictions total) mais **pas d'historique détaillé** — pas de liste des prédictions individuelles, juste un compteur agrégé.

Aucune des deux ne correspond exactement à "historique + métriques" tel que formulé dans l'issue. Si l'attente est une seule page combinant liste détaillée ET métriques (graphiques, tendances, taux de maladies détectées...), **elle n'existe pas** — il faudrait soit enrichir `history.py` de métriques personnelles, soit enrichir `dashboard.py` d'un historique consultable, soit clarifier que ce sont deux besoins distincts (historique personnel vs tableau de bord admin) qui n'ont jamais été censés être une seule page.

### Navigation commune — **COUVERTE, mécanisme précis**
Gérée exclusivement par `st.navigation()` natif Streamlit, construit dans `app.py:main()` — pas de `session_state` manuel pour la navigation elle-même (le `session_state` sert à l'authentification, pas au routing). Un seul point de construction de la navigation dans tout le code (vérifié par recherche exhaustive, voir §4) : `app.py:108-144`. Sidebar toujours visible avec logo/statut API/déconnexion (`sidebar_header()`), séparée de la navigation de pages proprement dite.

---

## 3. Accessibilité WCAG AA — audit précis

### Labels de formulaire
| Page | Champ | Label explicite non vide ? |
|---|---|---|
| `login.py` | Nom d'utilisateur | Oui — `st.text_input("Nom d'utilisateur", ...)` |
| `login.py` | Mot de passe | Oui — `st.text_input("Mot de passe", type="password", ...)` |
| `creer_membre.py` | Nom d'utilisateur | Oui — identique |
| `creer_membre.py` | Mot de passe | Oui — identique |
| `predict.py` | Upload image | Oui, et informatif — `st.file_uploader("Image de la feuille (formats acceptés : JPG, JPEG, PNG)", ...)` |

Aucun `label_visibility="collapsed"` ou `"hidden"` trouvé nulle part dans le code (vérifié par lecture) — tous les labels sont visuellement rendus, pas seulement présents dans le DOM pour les lecteurs d'écran.

### Messages d'erreur
Tous les messages passent par `ApiError`, dont le constructeur exige un `message: str` — jamais une exception brute affichée directement. Vérifié un par un dans `api_client.py` : chaque `raise ApiError(...)` porte une phrase française complète ("Impossible de joindre le serveur...", "Identifiants invalides...", etc.), sauf un cas de repli :

- `api_client.py:211` : `_extraire_detail(reponse, f"Erreur {reponse.status_code}.")` — si l'API ne renvoie pas de champ `detail` JSON pour un code d'erreur imprévu, l'utilisateur verrait littéralement **"Erreur 500."** (ou autre code) plutôt qu'une phrase compréhensible. Cas de repli seulement (le cas normal renvoie le `detail` de l'API, qui est une phrase), mais c'est un point faible réel si l'API renvoie un jour une erreur 500 sans corps JSON exploitable.

Aucune trace de stack trace Python ou de nom d'exception brut affiché à l'utilisateur nulle part.

### Couleurs et contraste — valeurs exactes trouvées

Palette complète relevée dans `app.py` (CSS injecté) et `predict.py` (bandeaux inline) :

| Élément | Couleur texte | Couleur fond | Ratio de contraste calculé | Verdict WCAG AA |
|---|---|---|---|---|
| Bandeau "Tomate saine" / boutons primaires | `#ffffff` | `#2d6a4f` | **6.39:1** | Conforme (texte normal ET large) |
| Bandeau "Maladie détectée" | `#ffffff` | `#c1121f` | **6.22:1** | Conforme |
| Texte sidebar (règle `*` générique) | `#e8f1ea` | `#1b4332` | **9.60:1** | Conforme |
| Titres `h1`/`h2`/`h3` | `#1b2420` | `#f6f8f6` | **14.91:1** | Conforme |
| Bouton au survol | `#ffffff` | `#1b4332` | **11.08:1** | Conforme |

**Tous les couples texte/fond identifiés respectent WCAG AA**, calculé précisément (formule de luminance relative WCAG, seuil 4.5:1 texte normal), pas estimé. Note : le docstring de `predict.py` annonçait "≈5.6:1" et "≈6.5:1" pour les deux bandeaux — mes calculs donnent 6.39:1 et 6.22:1. Chiffres différents de ceux du commentaire mais la conclusion (conforme AA) ne change pas dans les deux cas.

**Point d'attention non résolu par ce calcul** : `app.py:40`, la règle CSS `section[data-testid="stSidebar"] * { color: #e8f1ea; }` utilise un sélecteur universel (`*`) sur tout le contenu de la sidebar. C'est une pratique fragile : elle peut affecter des éléments internes de Streamlit non anticipés (états `disabled`, liens, indicateurs de focus clavier) sans qu'on le voie dans le code source. Le bouton "Déconnexion" reste blanc grâce à la spécificité CSS plus élevée de `.stButton > button`, mais je n'ai **pas pu vérifier visuellement dans un navigateur réel** (pas d'accès navigateur dans cet environnement) que rien d'autre n'est cassé par cette règle générique — à tester manuellement.

### Boutons et liens — texte explicite
Tous les boutons trouvés ont un texte explicite, aucun bouton icône-seule sans alternative : "Se connecter", "Créer le compte", "Analyser", "Déconnexion", "Supprimer", "Oui, supprimer", "Annuler", "Ouvrir le monitoring". Les icônes de navigation (`:material/biotech:`, `:material/history:`, etc.) sont systématiquement accompagnées d'un `title` textuel dans `st.Page(...)` — jamais d'icône seule.

---

## 4. Filtrage par rôle dans la navigation — vérifié exhaustivement

Recherche exhaustive de toute construction de navigation ou lien vers les pages admin dans l'ensemble de `src/tomatoscan/front/` : **un seul point de construction existe**, `app.py:108-144`. Aucun `st.page_link`, aucune référence à `dashboard.py`/`creer_membre.py` ailleurs dans le code (vérifié par `grep` sur tout le dossier).

Le mécanisme : la liste `pages` passée à `st.navigation()` n'inclut `pages/dashboard.py` et `pages/creer_membre.py` que si `st.session_state.get("role") == "admin"` (`app.py:123-137`). Pour une session agriculteur, ces entrées **ne sont jamais construites**, pas seulement masquées visuellement — `st.navigation()` ne reçoit que 2 pages (Analyse, Historique) dans ce cas, donc son routing interne ne connaît même pas l'existence des pages admin pour cette session.

**Réponse à la question posée** : non, un agriculteur ne peut voir un lien vers une page qu'il n'a pas le droit d'utiliser nulle part — il n'y a qu'un seul endroit où la navigation est construite, et le filtrage y est appliqué avant toute construction de lien. Pas de fuite possible par un autre chemin dans le code actuel.

**Nuance déjà documentée dans un audit précédent** (`docs/audit_tests_frontend.md`, aujourd'hui absent du disque suite au nettoyage git — voir conversation) : ce filtrage repose sur `session_state.role`, lu depuis le JWT côté client sans revérification cryptographique locale. La vraie garantie de sécurité reste côté API (`verifier_role_admin` sur chaque route `/users`), pas ce filtrage frontend qui est une couche d'UX, pas une seconde barrière de sécurité indépendante.

---

## 5. Conclusion — ce qu'il reste à faire, priorisé

1. **Clarifier/construire "dashboard historique + métriques"** (URGENT, effort MOYEN) — actuellement deux pages disjointes ne couvrent aucune ni l'autre le besoin tel que formulé. Décision à prendre : fusionner, ou documenter que ce sont deux besoins distincts et que l'issue doit être scindée. Si fusion : ajouter des métriques personnelles à `history.py` (taux de maladies, tendance dans le temps) ou un historique consultable dans `dashboard.py`.

2. **Page d'accueil dédiée** (MOYEN, effort RAPIDE) — si l'issue exige une page de bienvenue distincte de `predict.py`, c'est un ajout simple (texte de présentation + liens vers les fonctionnalités), mais actuellement inexistante.

3. **Corriger le message d'erreur générique "Erreur {code}."** (RAPIDE, effort RAPIDE) — `api_client.py:211`, remplacer par un message plus informatif même en l'absence de `detail` JSON de l'API.

4. **Vérification manuelle en navigateur réel de la règle CSS `*` sur la sidebar** (MOYEN, effort RAPIDE) — je n'ai pas pu la tester visuellement depuis cet environnement ; à faire avant de considérer l'accessibilité de la sidebar définitivement validée.

5. **Factoriser les composants répétés** (`components/` vide) (FAIBLE priorité, effort MOYEN) — pas un critère d'acceptation de l'issue #33 en soi, mais le bandeau résultat et le pattern de confirmation à deux clics sont dupliqués en l'état ; à envisager seulement si de nouvelles pages similaires arrivent.

6. **Wireframes formels** — limite déjà assumée dans le contexte du prompt, rien à corriger ici, juste rappelé pour mémoire dans la conclusion.
