from __future__ import annotations

import csv
import io
import re
from typing import Any

MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")


def validate_export_month(value: str) -> str:
    raw = str(value or "").strip()
    if not MONTH_PATTERN.match(raw):
        raise ValueError("Il parametro month deve essere nel formato YYYY-MM.")
    month = int(raw[5:7])
    if month < 1 or month > 12:
        raise ValueError("Il mese deve essere compreso tra 01 e 12.")
    return raw


def normalize_mese(value: str) -> str:
    return str(value).strip()[:7]


def tipo_export_label(tipo: str) -> str:
    if tipo == "entrata":
        return "entrata"
    if tipo == "spesa":
        return "uscita"
    return tipo


def evitabile_export_label(evitabile: bool) -> str:
    return "sì" if evitabile else "no"


def build_transactions_csv(transazioni: list[dict[str, Any]], month: str) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output, delimiter=",", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")

    writer.writerow(
        [
            "id",
            "data",
            "mese",
            "importo",
            "descrizione",
            "categoria",
            "tipo",
            "evitabile",
        ]
    )

    for item in transazioni:
        mese = normalize_mese(item["data"])
        writer.writerow(
            [
                item["id"],
                item["data"],
                mese,
                f"{float(item['importo']):.2f}",
                item.get("nota") or "",
                item["categoria"],
                tipo_export_label(str(item["tipo"])),
                evitabile_export_label(bool(item.get("evitabile"))),
            ]
        )

    # BOM UTF-8 per compatibilità Google Sheets / Excel con caratteri accentati
    return ("\ufeff" + output.getvalue()).encode("utf-8")
