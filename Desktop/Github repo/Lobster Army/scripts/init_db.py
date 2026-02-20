import sys
import os

# Ensure repo root is in path
sys.path.insert(0, os.getcwd())

from workflows.storage.db import DB
from workflows.storage.models import Base

def init_db():
    print("Initializing Database...")
    engine = DB.get_engine()
    print(f"Engine: {engine}")
    Base.metadata.create_all(engine)
    print("Tables created.")

if __name__ == "__main__":
    init_db()
