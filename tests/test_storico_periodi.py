from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from calcoli import build_storico
from database import normalize_categoria


def test_normalize_categoria_unifica_mangiare_fuori() -> None:
    assert normalize_categoria("mangiare_fuori") == "mangiare_fuori"
    assert normalize_categoria("mangiare fuori") == "mangiare_fuori"
    assert normalize_categoria("Mangiare Fuori") == "mangiare_fuori"


def test_scorso_mese_mostra_solo_mese_precedente() -> None:
    transazioni = [
        {"tipo": "spesa", "importo": 10, "data": "2026-05", "categoria": "spesa", "evitabile": False},
        {"tipo": "spesa", "importo": 20, "data": "2026-06", "categoria": "spesa", "evitabile": False},
    ]

    with patch("calcoli.date") as mock_date:
        mock_date.today.return_value = date(2026, 6, 15)
        storico = build_storico(transazioni, "scorso_mese")

    assert storico["mese_inizio"] == "2026-05"
    assert storico["mese_fine"] == "2026-05"
    assert storico["totale_spese"] == 10.0
    assert len(storico["punti"]) == 1
    assert storico["punti"][0]["mese"] == "2026-05"


def test_categorie_unite_nello_storico() -> None:
    transazioni = [
        {"tipo": "spesa", "importo": 15, "data": "2026-06", "categoria": "mangiare_fuori", "evitabile": False},
        {"tipo": "spesa", "importo": 25, "data": "2026-06", "categoria": "mangiare fuori", "evitabile": False},
    ]

    with patch("calcoli.date") as mock_date:
        mock_date.today.return_value = date(2026, 6, 15)
        storico = build_storico(transazioni, "1m")

    assert len(storico["categorie"]) == 1
    assert storico["categorie"][0]["categoria"] == "mangiare_fuori"
    assert storico["categorie"][0]["totale"] == 40.0
    assert storico["totale_spese"] == 40.0


if __name__ == "__main__":
    test_normalize_categoria_unifica_mangiare_fuori()
    test_scorso_mese_mostra_solo_mese_precedente()
    test_categorie_unite_nello_storico()
    print("OK - storico periodi e categorie verificati.")
