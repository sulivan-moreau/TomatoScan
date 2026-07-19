# Tests de l'endpoint GET /metrics (scrape Prometheus, sans authentification)
# Vérifie que les métriques attendues sont bien exposées, y compris la métrique
# de confiance ajoutée pour le monitoring de modèle (C11).


async def test_metrics_url_scrapee_par_prometheus_expose_les_metriques_attendues(
    client,
):
    """GET /metrics/ (avec slash final) est l'URL exacte configurée dans
    monitoring/prometheus.yml (metrics_path) — pas un contournement de test,
    c'est ce que Prometheus scrape réellement en production.

    Contient les métriques applicatives (prédictions, erreurs) et de modèle
    (confiance).
    """
    reponse = await client.get("/metrics/")
    assert reponse.status_code == 200

    corps = reponse.text
    assert "tomatoscan_predictions_total" in corps
    assert "tomatoscan_errors_total" in corps
    assert "tomatoscan_prediction_duration_seconds" in corps
    assert "tomatoscan_prediction_confidence" in corps
