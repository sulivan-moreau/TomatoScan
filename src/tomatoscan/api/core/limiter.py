"""
Rate limiter slowapi — protection contre les attaques par force brute.
Implémente OWASP API4 : Unrestricted Resource Consumption.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Instance partagée du rate limiter — identifie chaque client par son adresse IP
# Cette instance est importée dans main.py (state) et dans les routes décorées
limiteur = Limiter(key_func=get_remote_address)
