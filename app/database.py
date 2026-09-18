import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_conn():
    """
    Abre una conexión nueva a Postgres.
    Railway inyecta DATABASE_URL automáticamente cuando agregas el plugin de Postgres.
    """
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL no está configurada. Revisa tus variables de entorno.")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
