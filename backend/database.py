from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "finanze.sqlite"
MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")
LEGACY_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalize_categoria(value: str) -> str:
    """Unifica varianti come 'mangiare fuori' e 'mangiare_fuori'."""
    cleaned = re.sub(r"\s+", " ", str(value).strip().lower())
    cleaned = cleaned.replace(" ", "_")
    return re.sub(r"_+", "_", cleaned)


def migrate_normalize_categorie(connection: sqlite3.Connection) -> None:
    rows = connection.execute("SELECT id, categoria FROM transazioni").fetchall()
    for row in rows:
        normalized = normalize_categoria(row["categoria"])
        if normalized != row["categoria"]:
            connection.execute(
                "UPDATE transazioni SET categoria = ? WHERE id = ?",
                (normalized, row["id"]),
            )


def get_db_path() -> Path:
    custom_path = os.environ.get("FINANZE_DB_PATH")
    if custom_path:
        return Path(custom_path).expanduser().resolve()
    return DEFAULT_DB_PATH


def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS transazioni (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL CHECK (tipo IN ('entrata', 'spesa')),
                importo REAL NOT NULL CHECK (importo >= 0),
                data TEXT NOT NULL,
                categoria TEXT NOT NULL,
                nota TEXT DEFAULT '',
                evitabile INTEGER NOT NULL DEFAULT 0 CHECK (evitabile IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()

        # Modulo OBIETTIVI
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS obiettivi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                costo REAL NOT NULL CHECK (costo >= 0),
                data_target TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Modulo AI: persistenza report
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS report_ai (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                periodo TEXT NOT NULL,
                input_json TEXT NOT NULL,
                output_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        migrate_normalize_categorie(connection)
        connection.commit()


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

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO obiettivi (nome, costo, data_target)
            VALUES (?, ?, ?)
            """,
            (nome, costo_float, normalized_target),
        )
        connection.commit()
        obiettivo_id = int(cursor.lastrowid)

    return get_obiettivo(obiettivo_id)  # type: ignore[return-value]


def get_obiettivo(obiettivo_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, nome, costo, data_target, created_at
            FROM obiettivi
            WHERE id = ?
            """,
            (obiettivo_id,),
        ).fetchone()

    if not row:
        return None
    return dict(row)


def list_obiettivi() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, nome, costo, data_target, created_at
            FROM obiettivi
            ORDER BY data_target ASC, id DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def update_obiettivo(obiettivo_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    nome, costo_float, normalized_target = validate_obiettivo_payload(payload)

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE obiettivi
            SET nome = ?, costo = ?, data_target = ?
            WHERE id = ?
            """,
            (nome, costo_float, normalized_target, obiettivo_id),
        )
        connection.commit()

    if cursor.rowcount == 0:
        return None

    return get_obiettivo(obiettivo_id)


def delete_obiettivo(obiettivo_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM obiettivi WHERE id = ?",
            (obiettivo_id,),
        )
        connection.commit()

    return cursor.rowcount > 0


def create_report_ai(periodo: str, input_obj: dict[str, Any], output_obj: dict[str, Any]) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO report_ai (periodo, input_json, output_json)
            VALUES (?, ?, ?)
            """,
            (periodo, json_dumps(input_obj), json_dumps(output_obj)),
        )
        connection.commit()


def json_dumps(obj: dict[str, Any]) -> str:
    # Wrapper minimalista per evitare import extra nel punto sbagliato.
    import json as _json

    return _json.dumps(obj, ensure_ascii=False)


def create_transazione(payload: dict[str, Any]) -> dict[str, Any]:
    values = validate_transazione_payload(payload)

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO transazioni (tipo, importo, data, categoria, nota, evitabile)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        connection.commit()
        transazione_id = int(cursor.lastrowid)

    transazione = get_transazione(transazione_id)
    if transazione is None:
        raise RuntimeError("Transazione salvata ma non riletta dal database.")
    return transazione


def update_transazione(transazione_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    values = validate_transazione_payload(payload)

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE transazioni
            SET tipo = ?, importo = ?, data = ?, categoria = ?, nota = ?, evitabile = ?
            WHERE id = ?
            """,
            (*values, transazione_id),
        )
        connection.commit()

    if cursor.rowcount == 0:
        return None

    return get_transazione(transazione_id)


def delete_transazione(transazione_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM transazioni WHERE id = ?",
            (transazione_id,),
        )
        connection.commit()

    return cursor.rowcount > 0


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
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, tipo, importo, data, categoria, nota, evitabile, created_at
            FROM transazioni
            WHERE id = ?
            """,
            (transazione_id,),
        ).fetchone()

    return row_to_dict(row) if row else None


def list_transazioni() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, tipo, importo, data, categoria, nota, evitabile, created_at
            FROM transazioni
            ORDER BY id DESC
            """
        ).fetchall()

    return [row_to_dict(row) for row in rows]


def list_transazioni_by_month(month: str) -> list[dict[str, Any]]:
    month_value = str(month).strip()[:7]
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, tipo, importo, data, categoria, nota, evitabile, created_at
            FROM transazioni
            WHERE substr(data, 1, 7) = ?
            ORDER BY id DESC
            """,
            (month_value,),
        ).fetchall()

    return [row_to_dict(row) for row in rows]


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["evitabile"] = bool(item["evitabile"])
    return item
