# Métriques Prometheus exposées sur GET /metrics
# Importées dans routes/predict.py pour être incrémentées à chaque prédiction.
from prometheus_client import Counter, Histogram

# Nombre de prédictions réussies, ventilées par classe MobileNetV2 et statut
predictions_total = Counter(
    "tomatoscan_predictions_total",
    "Nombre total de prédictions effectuées, par classe détectée et statut",
    ["classe", "statut"],
)

# Durée d'inférence du modèle MobileNetV2 en secondes (buckets par défaut Prometheus)
prediction_duration_seconds = Histogram(
    "tomatoscan_prediction_duration_seconds",
    "Durée des prédictions MobileNetV2 en secondes",
)

# Erreurs rencontrées lors du traitement d'une requête /predict, par type
errors_total = Counter(
    "tomatoscan_errors_total",
    "Nombre total d'erreurs par type (format_invalide, image_corrompue, erreur_prediction…)",
    ["type_erreur"],
)
