import os
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    return psycopg.connect(
        host="localhost",
        port=5432,
        dbname="subscriptions",
        user="postgres",
        password=os.getenv("DB_PASSWORD"),
        row_factory=dict_row,
    )