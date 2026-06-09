from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from database import normalize_categoria


PERIODI_MESI = {
    "3m": 2,
    "6m": 5,
    "1y": 11,

    # Compat legacy
    "3_mesi": 2,
    "6_mesi": 5,
    "1_anno": 11,
}


def build_storico(transazioni: list[dict[str, Any]], periodo: str) -> dict[str, Any]:
    oggi = date.today()
    mesi_transazioni = [mese_index_from_value(item["data"]) for item in transazioni]
    periodo_norm = str(periodo).strip()
    start_index, end_index = resolve_period_range(periodo_norm, oggi, mesi_transazioni)

    mesi_periodo = list(range(start_index, end_index + 1))
    saldo_iniziale = 0.0
    movimenti_mensili: dict[int, float] = defaultdict(float)
    totale_entrate = 0.0
    totale_spese = 0.0
    spese_evitabili = 0.0
    categorie: dict[str, float] = defaultdict(float)

    for transazione in transazioni:
        transazione_mese = mese_index_from_value(transazione["data"])
        importo = float(transazione["importo"])
        valore = importo if transazione["tipo"] == "entrata" else -importo

        if transazione_mese < start_index:
            saldo_iniziale += valore
            continue

        if transazione_mese > end_index:
            continue

        movimenti_mensili[transazione_mese] += valore

        if transazione["tipo"] == "entrata":
            totale_entrate += importo
        else:
            totale_spese += importo
            categoria = normalize_categoria(transazione["categoria"])
            categorie[categoria] += importo
            if transazione.get("evitabile"):
                spese_evitabili += importo

    saldo = saldo_iniziale
    punti = []

    for mese in mesi_periodo:
        saldo += movimenti_mensili[mese]
        punti.append(
            {
                "mese": format_month_index(mese),
                "saldo": round(saldo, 2),
                "movimento": round(movimenti_mensili[mese], 2),
            }
        )

    saldo_finale = punti[-1]["saldo"] if punti else round(saldo_iniziale, 2)
    categorie_ordinate = sorted(categorie.items(), key=lambda item: item[1], reverse=True)
    categorie_lista = [
        {"categoria": categoria, "totale": round(totale, 2)}
        for categoria, totale in categorie_ordinate
    ]
    totale_categorie = round(sum(item["totale"] for item in categorie_lista), 2)

    return {
        "periodo": periodo_norm,
        "mese_inizio": format_month_index(start_index),
        "mese_fine": format_month_index(end_index),
        "saldo_iniziale": round(saldo_iniziale, 2),
        "saldo_finale": round(saldo_finale, 2),
        "totale_entrate": round(totale_entrate, 2),
        "totale_spese": round(totale_spese, 2),
        "totale_categorie": totale_categorie,
        "spese_evitabili": round(spese_evitabili, 2),
        "punti": punti,
        "categorie": categorie_lista,
    }


def resolve_period_range(
    periodo: str,
    oggi: date,
    mesi_transazioni: list[int],
) -> tuple[int, int]:
    mese_corrente = mese_index(oggi.year, oggi.month)

    if periodo in {"all", "tutto"}:
        if mesi_transazioni:
            return min(mesi_transazioni), mese_corrente
        return mese_corrente, mese_corrente

    if periodo in {"scorso_mese", "mese_scorso"}:
        scorso = mese_corrente - 1
        return scorso, scorso

    if periodo in {"1m", "mese_corrente", "1w", "2w"}:
        return mese_corrente, mese_corrente

    offset_mesi = PERIODI_MESI.get(periodo, PERIODI_MESI["6m"])
    return mese_corrente - offset_mesi, mese_corrente


def mese_index_from_value(value: str) -> int:
    year, month = value[:7].split("-")
    return mese_index(int(year), int(month))


def mese_index(year: int, month: int) -> int:
    return year * 12 + month - 1


def format_month_index(value: int) -> str:
    year = value // 12
    month = value % 12 + 1
    return f"{year:04d}-{month:02d}"


def mese_diff_in_mesi(from_month: str, to_month: str) -> int:
    """
    Differenza in mesi tra due date mensili (YYYY-MM).
    Esempio: da 2026-01 a 2026-03 => 2.
    """
    from_idx = mese_index_from_value(from_month)
    to_idx = mese_index_from_value(to_month)
    return to_idx - from_idx


def build_obiettivi_summary(
    obiettivi: list[dict[str, Any]],
    saldo_attuale: float,
    risparmio_medio_mensile: float,
) -> list[dict[str, Any]]:
    """
    Calcola per ogni obiettivo:
      - accumulato
      - percentuale completamento
      - stima tempo (in mesi)
    """
    from datetime import date as _date

    oggi = _date.today()
    mese_corrente_str = f"{oggi.year:04d}-{oggi.month:02d}"

    def stima_tempo_mesi(remaining: float) -> str:
        if remaining <= 0:
            return "Raggiunto"
        if risparmio_medio_mensile <= 0:
            return "Non stimabile (risparmio medio <= 0)"
        import math as _math

        mesi = int(_math.ceil(remaining / risparmio_medio_mensile))
        if mesi <= 0:
            mesi = 1
        return f"Circa {mesi} mesi"

    results: list[dict[str, Any]] = []
    for obj in obiettivi:
        costo = float(obj["costo"])
        accumulato_raw = max(0.0, float(saldo_attuale))
        accumulato = min(costo, accumulato_raw) if costo > 0 else 0.0

        percent = 0.0
        if costo > 0:
            percent = min(100.0, (accumulato / costo) * 100.0)

        remaining = max(0.0, costo - accumulato)
        stima = stima_tempo_mesi(remaining)

        mesi_al_target = mese_diff_in_mesi(mese_corrente_str, str(obj["data_target"]))
        if mesi_al_target < 0:
            stima = f"{stima} (target passato)"

        results.append(
            {
                "id": obj["id"],
                "nome": obj["nome"],
                "costo": round(costo, 2),
                "data_target": obj["data_target"],
                "accumulato": round(accumulato, 2),
                "percentuale": round(percent, 1),
                "stima_tempo": stima,
                "mesi_al_target": mesi_al_target,
            }
        )

    return results
