# Configuration partagée pour tous les tests — chargée par pytest avant les fichiers de tests.
# Les variables d'environnement doivent être définies AVANT l'import de l'application
# pour que load_dotenv() ne les écrase pas (override=False par défaut).
import os

os.environ.setdefault("SECRET_KEY", "cle_secrete_test_uniquement")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("ADMIN_USERNAME", "admin_test")
os.environ.setdefault("ADMIN_PASSWORD", "motdepasse_test_123")
