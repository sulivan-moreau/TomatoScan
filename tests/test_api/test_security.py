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
