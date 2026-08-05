import os
from dotenv import load_dotenv

load_dotenv();

DB_URI = os.getenv("POSTGRES_DATABASE_URI", "postgresql://postgres:2765581@localhost:5432/simplificando")