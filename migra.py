import sqlite3
import psycopg2
from psycopg2.extras import execute_values

# Sostituisci con la tua stringa di connessione reale di Neon
PG_URL = "postgresql://neondb_owner:npg_uAj1qWLD0QiP@ep-steep-boat-athblpep.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require"

s_conn = sqlite3.connect("finanze.sqlite")
s_cur = s_conn.cursor()
p_conn = psycopg2.connect(PG_URL)
p_cur = p_conn.cursor()

# Recupera le tabelle da SQLite
s_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
tables = [t[0] for t in s_cur.fetchall()]

for table in tables:
    s_cur.execute(f"PRAGMA table_info({table});")
    cols = [c[1] for c in s_cur.fetchall()]
    
    s_cur.execute(f"SELECT * FROM {table};")
    rows = s_cur.fetchall()
    
    if rows:
        print(f"Copia di {table}...")
        p_cur.execute(f"TRUNCATE TABLE {table} CASCADE;")
        query = f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s"
        execute_values(p_cur, query, rows)

p_conn.commit()
s_conn.close()
p_conn.close()
print("Migrazione completata con successo!")