# Tests de sécurité OWASP — headers HTTP et rate limiting
import os

NOM_ADMIN = os.getenv("ADMIN_USERNAME", "admin_test")
MOT_DE_PASSE_ADMIN = os.getenv("ADMIN_PASSWORD", "motdepasse_test_123")


async def test_headers_securite(client):
    """Vérifie la présence des 3 headers de sécurité sur GET /health (OWASP API7)."""
    reponse = await client.get("/health")
    assert reponse.status_code == 200
    assert reponse.headers.get("x-content-type-options") == "nosniff"
    assert reponse.headers.get("x-frame-options") == "DENY"
    assert reponse.headers.get("x-xss-protection") == "1; mode=block"


async def test_rate_limiting(client):
    """6 requêtes rapides sur /auth/token — la 6ème doit retourner 429 (OWASP API4)."""
    # Les 5 premières requêtes doivent passer (quelle que soit la réponse auth)
    statuts = []
    for _ in range(6):
        reponse = await client.post(
            "/auth/token", json={"username": "x", "password": "y"}
        )
        statuts.append(reponse.status_code)
    assert statuts[5] == 429, (
        f"La 6ème requête devrait être 429 — statuts obtenus : {statuts}"
    )
    assert all(s != 429 for s in statuts[:5]), (
        f"Les 5 premières ne devraient pas être 429 — statuts : {statuts}"
    )


async def test_5_echecs_consecutifs_bloquent_meme_si_le_debit_reste_bas(client):
    """Un attaquant qui espace ses tentatives (fenêtre de rate limiting par IP
    réinitialisée entre chaque essai, comme le ferait un temps d'attente réel)
    doit quand même être bloqué après 5 échecs consécutifs sur le même compte —
    c'est précisément le cas que le rate limiting par IP seul ne couvre pas."""
    from tomatoscan.api.core.limiter import limiteur

    statuts = []
    for _ in range(6):
        limiteur._storage.reset()  # simule l'écoulement du temps pour le débit par IP
        reponse = await client.post(
            "/auth/token",
            json={"username": "attaquant_patient", "password": "faux_mdp"},
        )
        statuts.append(reponse.status_code)

    assert statuts[:5] == [401, 401, 401, 401, 401], statuts
    assert statuts[5] == 429, statuts


async def test_connexion_reussie_reinitialise_le_compteur_d_echecs(client):
    """Une connexion réussie doit remettre à zéro le compteur d'échecs consécutifs
    — un utilisateur qui se trompe puis réussit ne doit pas être pénalisé ensuite
    comme s'il avait déjà des échecs à son actif."""
    from tomatoscan.api.core.limiter import limiteur

    for _ in range(3):
        limiteur._storage.reset()
        await client.post(
            "/auth/token",
            json={"username": NOM_ADMIN, "password": "mauvais_mot_de_passe"},
        )

    limiteur._storage.reset()
    reponse_ok = await client.post(
        "/auth/token",
        json={"username": NOM_ADMIN, "password": MOT_DE_PASSE_ADMIN},
    )
    assert reponse_ok.status_code == 200

    # Après le succès, 4 nouveaux échecs ne doivent pas suffire à déclencher le blocage
    statuts = []
    for _ in range(4):
        limiteur._storage.reset()
        reponse = await client.post(
            "/auth/token",
            json={"username": NOM_ADMIN, "password": "mauvais_mot_de_passe"},
        )
        statuts.append(reponse.status_code)
    assert all(s == 401 for s in statuts), statuts
