# Checklist OWASP API Security Top 10 — TomatoScan

Référence : [OWASP API Security Top 10 2023](https://owasp.org/API-Security/)

---

## API1 — Broken Object Level Authorization

**Risque :** Un utilisateur accède aux ressources d'un autre utilisateur sans contrôle.

**Mesure appliquée :** L'endpoint `POST /predict` est protégé par un token JWT Bearer.
Toute requête sans token valide reçoit une réponse 401.
TomatoScan est monocompte — il n'y a pas d'objets appartenant à des utilisateurs différents.

**Fichiers :**
- `src/tomatoscan/api/routes/predict.py` — `Depends(obtenir_utilisateur_courant)`
- `src/tomatoscan/api/core/security.py` — validation du token JWT

---

## API2 — Broken Authentication

**Risque :** Authentification faible ou tokens sans expiration permettant la prise de compte.

**Mesures appliquées :**
- Tokens JWT avec expiration configurable (`ACCESS_TOKEN_EXPIRE_MINUTES` en `.env`)
- Algorithme HS256 avec `SECRET_KEY` forte stockée en `.env` (jamais en dur)
- Connexion échouée loggée avec `loguru`

**Fichiers :**
- `src/tomatoscan/api/core/security.py` — `creer_token_acces()`, `obtenir_utilisateur_courant()`
- `.env.example` — `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`

---

## API4 — Unrestricted Resource Consumption

**Risque :** L'API ne limite pas les appels, permettant le brute-force ou le DoS.

**Mesures appliquées :**
- Rate limiting `5 requêtes/minute` sur `POST /auth/token` via `slowapi` (protection brute-force)
- Taille maximale des images limitée à **5 Mo** sur `POST /predict`
- Réponse 429 automatique en cas de dépassement

**Fichiers :**
- `src/tomatoscan/api/core/limiter.py` — instance `Limiter` slowapi
- `src/tomatoscan/api/routes/auth.py` — `@limiteur.limit("5/minute")`
- `src/tomatoscan/api/routes/predict.py` — `TAILLE_MAX_OCTETS = 5 * 1024 * 1024`
- `src/tomatoscan/api/main.py` — `SlowAPIMiddleware`, handler 429

---

## API7 — Security Misconfiguration

**Risque :** Configuration par défaut permissive, headers manquants, CORS trop ouvert.

**Mesures appliquées :**
- Headers de sécurité ajoutés sur toutes les réponses via `EnteteSecuriteMiddleware` :
  - `X-Content-Type-Options: nosniff` — bloque le MIME sniffing
  - `X-Frame-Options: DENY` — protège contre le clickjacking
  - `X-XSS-Protection: 1; mode=block` — active le filtre XSS des navigateurs anciens
- CORS configuré via `CORS_ORIGINS` en `.env` (restreindre à l'origine du frontend en production)
- `.env` dans `.gitignore` — secrets jamais commités

**Fichiers :**
- `src/tomatoscan/api/main.py` — `EnteteSecuriteMiddleware`, `CORSMiddleware`
- `.env.example` — `CORS_ORIGINS`
- `.gitignore` — `.env` exclu

---

## API8 — Security Misconfiguration (Injection)

**Risque :** Données non validées injectées dans des traitements sensibles (SQL, OS, etc.).

**Mesures appliquées :**
- Tous les inputs API sont validés par des schémas **Pydantic** (types stricts, champs requis)
- Les fichiers image sont validés par type MIME et extension avant traitement
- Aucune requête SQL dynamique — pas d'ORM utilisé sur ce chemin de prédiction
- L'image est traitée en mémoire (`io.BytesIO`) sans jamais être écrite sur disque

**Fichiers :**
- `src/tomatoscan/api/schemas/auth.py` — `LoginRequest`, `TokenResponse`
- `src/tomatoscan/api/schemas/predict.py` — `PredictionResponse`
- `src/tomatoscan/api/routes/predict.py` — validation MIME + taille avant traitement

---

## Résumé des contrôles

| Menace OWASP | Statut | Mécanisme |
|---|---|---|
| API1 — Object Auth | ✅ | JWT sur /predict |
| API2 — Authentication | ✅ | JWT expirable, SECRET_KEY en .env |
| API4 — Consommation | ✅ | Rate limit 5/min, taille max 5 Mo |
| API7 — Misconfiguration | ✅ | Headers sécurité, CORS configurable |
| API8 — Injection | ✅ | Validation Pydantic, traitement mémoire |
