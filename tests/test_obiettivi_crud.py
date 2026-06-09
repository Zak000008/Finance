from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = PROJECT_ROOT / "backend" / "server.py"


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_server(port: int) -> None:
    deadline = time.time() + 8
    while time.time() < deadline:
        try:
            response = get_json(port, "/api/health")
            if response.get("ok"):
                return
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.2)
    raise RuntimeError("Il server non si è avviato in tempo.")


def get_json(port: int, path: str) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def send_json(port: int, path: str, payload: dict, method: str) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(port: int, path: str, payload: dict) -> dict:
    return send_json(port, path, payload, "POST")


def delete_json(port: int, path: str) -> dict:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        method="DELETE",
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    port = find_free_port()

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_finanze.sqlite"
        env = os.environ.copy()
        env["FINANZE_PORT"] = str(port)
        env["FINANZE_DB_PATH"] = str(db_path)

        process = subprocess.Popen(
            [sys.executable, str(SERVER_PATH)],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            wait_for_server(port)

            created = post_json(
                port,
                "/api/obiettivi",
                {"nome": "Test", "costo": 100, "data_target": "2026-10"},
            )
            assert created["ok"] is True
            obiettivo_id = created["obiettivo"]["id"]
            assert obiettivo_id is not None

            listed = get_json(port, "/api/obiettivi")
            assert len(listed["obiettivi"]) == 1
            assert listed["obiettivi"][0]["nome"] == "Test"
            assert "accumulato" in listed["obiettivi"][0]
            assert "percentuale" in listed["obiettivi"][0]
            assert "stima_tempo" in listed["obiettivi"][0]

            updated = send_json(
                port,
                f"/api/obiettivi/{obiettivo_id}",
                {"nome": "Test aggiornato", "costo": 150, "data_target": "2026-11"},
                "PUT",
            )
            assert updated["ok"] is True
            assert updated["obiettivo"]["nome"] == "Test aggiornato"
            assert updated["obiettivo"]["costo"] == 150

            deleted = delete_json(port, f"/api/obiettivi/{obiettivo_id}")
            assert deleted["ok"] is True

            listed_after = get_json(port, "/api/obiettivi")
            assert listed_after["obiettivi"] == []

            print("OK - CRUD obiettivi verificato.")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()

