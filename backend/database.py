from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any
import psycopg2
from psycopg2.extras import RealDictCursor


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")
LEGACY_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalize_categoria(value: str) -> str:
    """Unifica varianti come 'mangiare fuori' e 'mangiare_fuori'."""
    cleaned = re.sub(r"\s+", " ", str(value).strip().lower())
    cleaned = cleaned.replace(" ", "_")
    return re.sub(r"_+", "_", cleaned)


def migrate_normalize_categorie(cursor: Any) -> None:
    cursor.execute("SELECT id, categoria FROM transazioni")
    rows = cursor.fetchall()
    for row in rows:
        normalized = normalize_categoria(row["categoria"])
        if normalized != row["categoria"]:
            cursor.execute(
                "UPDATE transazioni SET categoria = %s WHERE id = %s",
                (normalized, row["id"]),
            )


def get_connection() -> Any:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL non impostata nelle variabili d'ambiente.")
    return psycopg2.connect(db_url, cursor_factory=RealDictCursor)


@contextmanager
def db_cursor():
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                yield cursor
    finally:
        connection.close()


def init_db() -> None:
    with db_cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS transazioni (
                id SERIAL PRIMARY KEY,
                tipo TEXT NOT NULL CHECK (tipo IN ('entrata', 'spesa')),
                importo REAL NOT NULL CHECK (importo >= 0),
                data TEXT NOT NULL,
                categoria TEXT NOT NULL,
                nota TEXT DEFAULT '',
                evitabile INTEGER NOT NULL DEFAULT 0 CHECK (evitabile IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS')
            )
            """
        )

        # Modulo OBIETTIVI
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS obiettivi (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                costo REAL NOT NULL CHECK (costo >= 0),
                data_target TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS')
            )
            """
        )

        # Modulo AI: persistenza report
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS report_ai (
                id SERIAL PRIMARY KEY,
                periodo TEXT NOT NULL,
                input_json TEXT NOT NULL,
                output_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS')
            )
            """
        )

        migrate_normalize_categorie(cursor)


def validate_data_target(value: str) -> str:
    raw = str(value or "").strip()
    if LEGACY_DATE_PATTERN.match(raw):
        raw = raw[:7]
    if not MONTH_PATTERN.match(raw):
        raise ValueError("La data target deve essere nel formato anno-mese.")
    return raw


def validate_obiettivo_payload(payload: dict[str, Any]) -> tuple[str, float, str]:
    nome = str(payload.get("nome", "")).strip()
    costo = payload.get("costo")
    data_target = payload.get("data_target")

    if not nome:
        raise ValueError("Il nome è obbligatorio.")

    try:
        costo_float = float(costo)
    except (TypeError, ValueError) as error:
        raise ValueError("Il costo deve essere un numero.") from error

    if costo_float < 0:
        raise ValueError("Il costo non può essere negativo.")

    if not data_target:
        raise ValueError("La data target è obbligatoria.")

    normalized_target = validate_data_target(data_target)

    return nome, costo_float, normalized_target


def create_obiettivo(payload: dict[str, Any]) -> dict[str, Any]:
    nome, costo_float, normalized_target = validate_obiettivo_payload(payload)

    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO obiettivi (nome, costo, data_target)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (nome, costo_float, normalized_target),
        )
        obiettivo_id = cursor.fetchone()["id"]

    return get_obiettivo(obiettivo_id)  # type: ignore[return-value]


def get_obiettivo(obiettivo_id: int) -> dict[str, Any] | None:
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, nome, costo, data_target, created_at
            FROM obiettivi
            WHERE id = %s
            """,
            (obiettivo_id,),
        )
        row = cursor.fetchone()

    if not row:
        return None
    return dict(row)


def list_obiettivi() -> list[dict[str, Any]]:
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, nome, costo, data_target, created_at
            FROM obiettivi
            ORDER BY data_target ASC, id DESC
            """
        )
        rows = cursor.fetchall()

    return [dict(row) for row in rows]


def update_obiettivo(obiettivo_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    nome, costo_float, normalized_target = validate_obiettivo_payload(payload)

    with db_cursor() as cursor:
        cursor.execute(
            """
            UPDATE obiettivi
            SET nome = %s, costo = %s, data_target = %s
            WHERE id = %s
            """,
            (nome, costo_float, normalized_target, obiettivo_id),
        )
        rowcount = cursor.rowcount

    if rowcount == 0:
        return None

    return get_obiettivo(obiettivo_id)


def delete_obiettivo(obiettivo_id: int) -> bool:
    with db_cursor() as cursor:
        cursor.execute(
            "DELETE FROM obiettivi WHERE id = %s",
            (obiettivo_id,),
        )
        rowcount = cursor.rowcount

    return rowcount > 0


def create_report_ai(periodo: str, input_obj: dict[str, Any], output_obj: dict[str, Any]) -> None:
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO report_ai (periodo, input_json, output_json)
            VALUES (%s, %s, %s)
            """,
            (periodo, json_dumps(input_obj), json_dumps(output_obj)),
        )


def json_dumps(obj: dict[str, Any]) -> str:
    import json as _json
    return _json.dumps(obj, ensure_ascii=False)


def create_transazione(payload: dict[str, Any]) -> dict[str, Any]:
    values = validate_transazione_payload(payload)

    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO transazioni (tipo, importo, data, categoria, nota, evitabile)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """,
            values,
        )
        transazione_id = cursor.fetchone()["id"]

    transazione = get_transazione(transazione_id)
    if transazione is None:
        raise RuntimeError("Transazione salvata ma non riletta dal database.")
    return transazione


def update_transazione(transazione_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    values = validate_transazione_payload(payload)

    with db_cursor() as cursor:
        cursor.execute(
            """
            UPDATE transazioni
            SET tipo = %s, importo = %s, data = %s, categoria = %s, nota = %s, evitabile = %s
            WHERE id = %s
            """,
            (*values, transazione_id),
        )
        rowcount = cursor.rowcount

    if rowcount == 0:
        return None

    return get_transazione(transazione_id)


def delete_transazione(transazione_id: int) -> bool:
    with db_cursor() as cursor:
        cursor.execute(
            "DELETE FROM transazioni WHERE id = %s",
            (transazione_id,),
        )
        rowcount = cursor.rowcount

    return rowcount > 0


def validate_transazione_payload(payload: dict[str, Any]) -> tuple[str, float, str, str, str, int]:
    tipo = str(payload.get("tipo", "")).strip().lower()
    importo = payload.get("importo")
    data = str(payload.get("data", "")).strip()
    categoria = normalize_categoria(str(payload.get("categoria", "")).strip())
    nota = str(payload.get("nota", "")).strip()
    evitabile = 1 if bool(payload.get("evitabile")) else 0

    if tipo not in {"entrata", "spesa"}:
        raise ValueError("Il tipo deve essere 'entrata' oppure 'spesa'.")

    try:
        importo_float = float(importo)
    except (TypeError, ValueError) as error:
        raise ValueError("L'importo deve essere un numero.") from error

    if importo_float < 0:
        raise ValueError("L'importo non può essere negativo.")

    if not data:
        raise ValueError("La data è obbligatoria.")

    if LEGACY_DATE_PATTERN.match(data):
        data = data[:7]

    if not MONTH_PATTERN.match(data):
        raise ValueError("La data deve essere nel formato anno-mese.")

    month = int(data[5:7])
    if month < 1 or month > 12:
        raise ValueError("Il mese deve essere compreso tra 01 e 12.")

    if not categoria:
        raise ValueError("La categoria è obbligatoria.")

    return tipo, importo_float, data, categoria, nota, evitabile


def get_transazione(transazione_id: int) -> dict[str, Any] | None:
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, tipo, importo, data, categoria, nota, evitabile, created_at
            FROM transazioni
            WHERE id = %s
            """,
            (transazione_id,),
        )
        row = cursor.fetchone()

    return row_to_dict(row) if row else None


def list_transazioni() -> list[dict[str, Any]]:
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, tipo, importo, data, categoria, nota, evitabile, created_at
            FROM transazioni
            ORDER BY id DESC
            """
        )
        rows = cursor.fetchall()

    return [row_to_dict(row) for row in rows]


def list_transazioni_by_month(month: str) -> list[dict[str, Any]]:
    month_value = str(month).strip()[:7]
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, tipo, importo, data, categoria, nota, evitabile, created_at
            FROM transazioni
            WHERE substr(data, 1, 7) = %s
            ORDER BY id DESC
            """,
            (month_value,),
        )
        rows = cursor.fetchall()

    return [row_to_dict(row) for row in rows]


def row_to_dict(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["evitabile"] = bool(item["evitabile"])
    return item