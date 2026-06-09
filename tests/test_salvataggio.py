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

            payload = {
                "tipo": "spesa",
                "importo": 12.5,
                "data": "2026-06-01",
                "categoria": "test",
                "nota": "salvataggio automatico",
                "evitabile": True,
            }

            created = post_json(port, "/api/transazioni", payload)
            assert created["ok"] is True
            assert created["transazione"]["categoria"] == "test"
            assert created["transazione"]["evitabile"] is True

            listed = get_json(port, "/api/transazioni")
            transazioni = listed["transazioni"]

            assert len(transazioni) == 1
            assert transazioni[0]["tipo"] == "spesa"
            assert transazioni[0]["importo"] == 12.5
            assert db_path.exists()

            print("OK - salvataggio su SQLite verificato.")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


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


def post_json(port: int, path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(request, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    main()
