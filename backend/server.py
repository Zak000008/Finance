from __future__ import annotations

import json
import mimetypes
import os
import base64
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from calcoli import build_obiettivi_summary, build_storico
from database import (
    create_transazione,
    delete_transazione,
    create_obiettivo,
    delete_obiettivo,
    update_obiettivo,
    init_db,
    list_transazioni,
    list_transazioni_by_month,
    list_obiettivi,
    create_report_ai,
    update_transazione,
)
from export_csv import build_transactions_csv, validate_export_month


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"


def load_dotenv_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if not key:
            continue

        # Non sovrascrive variabili già presenti nella shell.
        os.environ.setdefault(key, value)


load_dotenv_file(PROJECT_ROOT / ".env")
load_dotenv_file(PROJECT_ROOT / "backend" / ".env")

HOST = os.environ.get("FINANZE_HOST") or ("0.0.0.0" if os.environ.get("RENDER") else "127.0.0.1")
PORT = int(os.environ.get("PORT") or os.environ.get("FINANZE_PORT", "8000"))
AUTH_USER = os.environ.get("FINANZE_AUTH_USER", "finanze")
AUTH_PASSWORD = os.environ.get("FINANZE_APP_PASSWORD", "")


class FinanceRequestHandler(BaseHTTPRequestHandler):
    server_version = "FinanzePersonali/0.1"

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)

        if parsed_url.path == "/api/health":
            self.send_json({"ok": True, "message": "Backend attivo"})
            return

        if not self.ensure_authorized():
            return

        if parsed_url.path == "/api/transazioni":
            self.send_json({"transazioni": list_transazioni()})
            return

        if parsed_url.path == "/api/storico":
            query = parse_qs(parsed_url.query)
            periodo = query.get("periodo", ["6_mesi"])[0]
            self.send_json({"storico": build_storico(list_transazioni(), periodo)})
            return

        if parsed_url.path == "/api/obiettivi":
            transazioni = list_transazioni()
            storio_all = build_storico(transazioni, "all")
            saldo_attuale = float(storio_all["saldo_finale"])

            # Stima progresso: media netta mensile sull'ultimo orizzonte (6 mesi)
            storico_stima = build_storico(transazioni, "6m")
            punti_len = max(1, len(storico_stima["punti"]))
            net_change = float(storico_stima["saldo_finale"]) - float(storico_stima["saldo_iniziale"])
            risparmio_medio_mensile = net_change / punti_len

            obiettivi = list_obiettivi()
            summary = build_obiettivi_summary(
                obiettivi=obiettivi,
                saldo_attuale=saldo_attuale,
                risparmio_medio_mensile=risparmio_medio_mensile,
            )
            self.send_json({"obiettivi": summary})
            return

        if parsed_url.path in {"/api/export/csv", "/export/csv"}:
            self.serve_export_csv(parsed_url)
            return

        self.serve_static_file(parsed_url.path)

    def do_POST(self) -> None:
        parsed_url = urlparse(self.path)

        if not self.ensure_authorized():
            return

        if parsed_url.path == "/api/transazioni":
            try:
                payload = self.read_json_body()
                transazione = create_transazione(payload)
            except ValueError as error:
                self.send_json({"ok": False, "error": str(error)}, status=400)
                return
            except json.JSONDecodeError:
                self.send_json({"ok": False, "error": "JSON non valido."}, status=400)
                return

            self.send_json({"ok": True, "transazione": transazione}, status=201)
            return

        if parsed_url.path == "/api/obiettivi":
            try:
                payload = self.read_json_body()
                obiettivo = create_obiettivo(payload)
            except ValueError as error:
                self.send_json({"ok": False, "error": str(error)}, status=400)
                return
            self.send_json({"ok": True, "obiettivo": obiettivo}, status=201)
            return

        if parsed_url.path == "/api/ai/analisi":
            try:
                payload = self.read_json_body()
                periodo = str(payload.get("periodo") or "6m").strip()
            except Exception:
                periodo = "6m"

            try:
                report = self.run_ai_analisi(periodo=periodo)
            except ValueError as error:
                self.send_json({"ok": False, "error": str(error)}, status=400)
                return
            except RuntimeError as error:
                self.send_json({"ok": False, "error": str(error)}, status=503)
                return

            self.send_json({"ok": True, "report": report}, status=200)
            return

        self.send_json({"ok": False, "error": "Endpoint non trovato."}, status=404)

    def do_PUT(self) -> None:
        parsed_url = urlparse(self.path)

        if not self.ensure_authorized():
            return

        transazione_id = parse_transazione_id(parsed_url.path)

        if transazione_id is not None:
            try:
                payload = self.read_json_body()
                transazione = update_transazione(transazione_id, payload)
            except ValueError as error:
                self.send_json({"ok": False, "error": str(error)}, status=400)
                return
            except json.JSONDecodeError:
                self.send_json({"ok": False, "error": "JSON non valido."}, status=400)
                return

            if transazione is None:
                self.send_json({"ok": False, "error": "Transazione non trovata."}, status=404)
                return

            self.send_json({"ok": True, "transazione": transazione})
            return

        obiettivo_id = parse_obiettivo_id(parsed_url.path)
        if obiettivo_id is not None:
            try:
                payload = self.read_json_body()
                obiettivo = update_obiettivo(obiettivo_id, payload)
            except ValueError as error:
                self.send_json({"ok": False, "error": str(error)}, status=400)
                return
            except json.JSONDecodeError:
                self.send_json({"ok": False, "error": "JSON non valido."}, status=400)
                return

            if obiettivo is None:
                self.send_json({"ok": False, "error": "Obiettivo non trovato."}, status=404)
                return

            self.send_json({"ok": True, "obiettivo": obiettivo})
            return

        self.send_json({"ok": False, "error": "Endpoint non trovato."}, status=404)

    def do_DELETE(self) -> None:
        parsed_url = urlparse(self.path)

        if not self.ensure_authorized():
            return

        transazione_id = parse_transazione_id(parsed_url.path)

        if transazione_id is None:
            obiettivo_id = parse_obiettivo_id(parsed_url.path)
            if obiettivo_id is None:
                self.send_json({"ok": False, "error": "Endpoint non trovato."}, status=404)
                return

            deleted = delete_obiettivo(obiettivo_id)
            if not deleted:
                self.send_json({"ok": False, "error": "Obiettivo non trovato."}, status=404)
                return
            self.send_json({"ok": True})
            return

        deleted = delete_transazione(transazione_id)
        if not deleted:
            self.send_json({"ok": False, "error": "Transazione non trovata."}, status=404)
            return

        self.send_json({"ok": True})

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_common_headers()
        self.end_headers()

    def read_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8")
        if not raw_body:
            return {}
        return json.loads(raw_body)

    def serve_static_file(self, request_path: str) -> None:
        relative_path = request_path.lstrip("/") or "index.html"
        file_path = (APP_DIR / relative_path).resolve()

        if not str(file_path).startswith(str(APP_DIR.resolve())):
            self.send_json({"ok": False, "error": "Percorso non valido."}, status=403)
            return

        if not file_path.exists() or not file_path.is_file():
            self.send_json({"ok": False, "error": "File non trovato."}, status=404)
            return

        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        content = file_path.read_bytes()

        self.send_response(200)
        self.send_common_headers(content_type=content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, payload: dict, status: int = 200) -> None:
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

        self.send_response(status)
        self.send_common_headers(content_type="application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def ensure_authorized(self) -> bool:
        if not AUTH_PASSWORD:
            return True

        if self.has_valid_basic_auth():
            return True

        self.send_unauthorized()
        return False

    def has_valid_basic_auth(self) -> bool:
        header = self.headers.get("Authorization", "")
        prefix = "Basic "
        if not header.startswith(prefix):
            return False

        try:
            decoded = base64.b64decode(header.removeprefix(prefix), validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return False

        username, separator, password = decoded.partition(":")
        if not separator:
            return False

        return (
            hmac.compare_digest(username, AUTH_USER)
            and hmac.compare_digest(password, AUTH_PASSWORD)
        )

    def send_unauthorized(self) -> None:
        payload = {"ok": False, "error": "Autenticazione richiesta."}
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

        self.send_response(401)
        self.send_common_headers(content_type="application/json; charset=utf-8")
        self.send_header("WWW-Authenticate", 'Basic realm="Le mie Finanze"')
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def serve_export_csv(self, parsed_url) -> None:
        from datetime import date

        query = parse_qs(parsed_url.query)
        month_raw = query.get("month", [""])[0]
        if not month_raw:
            today = date.today()
            month_raw = f"{today.year:04d}-{today.month:02d}"

        try:
            month = validate_export_month(month_raw)
        except ValueError as error:
            self.send_json({"ok": False, "error": str(error)}, status=400)
            return

        transazioni = list_transazioni_by_month(month)
        content = build_transactions_csv(transazioni, month)
        filename = f"report_{month}.csv"
        self.send_csv(content, filename)

    def send_csv(self, content: bytes, filename: str) -> None:
        self.send_response(200)
        self.send_common_headers(content_type="text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_common_headers(self, content_type: str | None = None) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if content_type:
            self.send_header("Content-Type", content_type)

    def log_message(self, format: str, *args) -> None:
        print(f"[server] {self.address_string()} - {format % args}")

    def run_ai_analisi(self, periodo: str) -> dict:
        transazioni = list_transazioni()
        storico_periodo = build_storico(transazioni, periodo)

        storico_all = build_storico(transazioni, "all")
        saldo_attuale = float(storico_all["saldo_finale"])

        storico_stima = build_storico(transazioni, "6m")
        punti_len = max(1, len(storico_stima["punti"]))
        net_change = float(storico_stima["saldo_finale"]) - float(storico_stima["saldo_iniziale"])
        risparmio_medio_mensile = net_change / punti_len

        obiettivi = list_obiettivi()
        obiettivi_summary = build_obiettivi_summary(
            obiettivi=obiettivi,
            saldo_attuale=saldo_attuale,
            risparmio_medio_mensile=risparmio_medio_mensile,
        )

        input_ai = {
            "categorie_spesa": storico_periodo["categorie"],
            "evitabili": float(storico_periodo["spese_evitabili"]),
            "saldo": float(storico_periodo["saldo_finale"]),
            "obiettivi": obiettivi_summary,
        }

        output_ai = self.call_openrouter(input_ai=input_ai, periodo=periodo)

        # Salvataggio report
        create_report_ai(periodo=periodo, input_obj=input_ai, output_obj=output_ai)
        return output_ai

    def call_openrouter(self, input_ai: dict[str, object], periodo: str) -> dict:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY mancante nel backend (variabili d'ambiente).")

        model = os.environ.get("OPENROUTER_MODEL", "openclaw")
        url = os.environ.get("OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")

        # Richiesta: JSON strutturato con chiavi fisse
        system = (
            "Sei un assistente esperto di finanze personali. "
            "Rispondi in italiano e segui rigorosamente il formato JSON richiesto."
        )

        user = {
            "periodo": periodo,
            "dati": input_ai,
            "richiesta": {
                "output_json": {
                    "analisi": "testo",
                    "consigli": ["stringa"],
                    "stime": "testo"
                }
            },
        }

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ]

        body = {
            "model": model,
            "messages": messages,
            "temperature": 0.4,
        }

        import urllib.request
        import urllib.error

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.URLError as error:
            raise RuntimeError(f"Errore chiamata OpenRouter: {error}") from error

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"OpenRouter: risposta non valida (JSON).") from error
        content = (
            parsed.get("choices", [{}])[0]
            .get("message", {})
            .get("content")
        )
        if not content:
            raise RuntimeError("OpenRouter: risposta senza contenuto.")

        # Prova a interpretare come JSON; se non riesce, ritorna un wrapper.
        try:
            as_json = json.loads(content)
            if isinstance(as_json, dict):
                return as_json
        except json.JSONDecodeError:
            pass

        return {"analisi": str(content), "consigli": [], "stime": ""}


def main() -> None:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), FinanceRequestHandler)
    print(f"App avviata: http://{HOST}:{PORT}")
    print("Premi CTRL+C per fermare il server.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer fermato correttamente.")
    finally:
        server.server_close()


def parse_transazione_id(path: str) -> int | None:
    prefix = "/api/transazioni/"
    if not path.startswith(prefix):
        return None

    raw_id = path.removeprefix(prefix).strip("/")
    if not raw_id.isdigit():
        return None

    return int(raw_id)


def parse_obiettivo_id(path: str) -> int | None:
    prefix = "/api/obiettivi/"
    if not path.startswith(prefix):
        return None

    raw_id = path.removeprefix(prefix).strip("/")
    if not raw_id.isdigit():
        return None
    return int(raw_id)


if __name__ == "__main__":
    main()
