import os
from dotenv import load_dotenv
import psycopg

load_dotenv();

DB_URI = os.getenv("POSTGRES_DATABASE_URI", "postgresql://postgres:2765581@localhost:5432/simplificando")


def get_db_connection():
    """
    Retorna uma conexão com o banco de dados PostgreSQL usando psycopg.
    A conexão é criada a partir da variável de ambiente POSTGRES_DATABASE_URI.

    A ESTRUTURA do banco NÃO é criada aqui nem por nenhum repositório: ela é gerenciada
    exclusivamente pelas migrations em `migrations/` (EDI-37), aplicadas no início do
    contêiner. Ver `infrastructure/db_url.py` para a variante da URL usada pelo Alembic.

    O fallback da constante DB_URI acima vale apenas para desenvolvimento local — em
    contêiner a variável de ambiente é sempre definida.
    """
    return psycopg.connect(DB_URI, autocommit=True)