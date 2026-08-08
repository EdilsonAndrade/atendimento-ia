import os
from dotenv import load_dotenv
import psycopg

load_dotenv();

DB_URI = os.getenv("POSTGRES_DATABASE_URI", "postgresql://postgres:2765581@localhost:5432/simplificando")


def get_db_connection():
    """
    Retorna uma conexão com o banco de dados PostgreSQL usando psycopg.
    A conexão é criada a partir da variável de ambiente POSTGRES_DATABASE_URI.
    """
    return psycopg.connect(DB_URI, autocommit=True)