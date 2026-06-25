# Métriques Prometheus pour TomatoScan
# Expose les compteurs et jauges accessibles via /metrics (à brancher avec starlette-exporter si besoin)
from prometheus_client import Counter

# Compteur total de requêtes reçues par l'API, toutes routes confondues
requetes_totales = Counter(
    "tomatoscan_requests_total",
    "Nombre total de requêtes reçues par l'API TomatoScan",
    ["method", "endpoint", "status_code"],
)
