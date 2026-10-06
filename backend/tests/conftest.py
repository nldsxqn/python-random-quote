import os

# Keep pytest off the developer SQLite file. Set before app import.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
