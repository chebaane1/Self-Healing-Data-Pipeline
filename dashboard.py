import json
import os
import threading
from collections import deque
from datetime import datetime, timezone
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import duckdb

import agent_repair
import run_pipeline


PROJECT_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = PROJECT_ROOT / "dashboard"
DATABASE_PATH = PROJECT_ROOT / "data" / "pipeline.duckdb"
RUN_RESULTS_PATH = PROJECT_ROOT / "target" / "run_results.json"
EVENTS_PATH = PROJECT_ROOT / "logs" / "dashboard_events.jsonl"
MAX_EVENTS = 300
EVENTS = deque(maxlen=MAX_EVENTS)
STATE = {"running": False, "operation": None, "status": "idle"}
LOCK = threading.RLock()


def load_events():
    if not EVENTS_PATH.is_file():
        return
    try:
        for line in EVENTS_PATH.read_text(encoding="utf-8").splitlines()[-MAX_EVENTS:]:
            EVENTS.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        EVENTS.clear()


def redact(value):
    if isinstance(value, str):
        value = re.sub(
            r"(?i)(api[_ -]?key|authorization|bearer)(\s*[:=]\s*)[^\s,;]+",
            r"\1\2[redacted]",
            value,
        )
        value = re.sub(r"\bAQ\.[A-Za-z0-9._-]{12,}", "[redacted API key]", value)
        value = re.sub(r"\bAIza[A-Za-z0-9_-]{20,}", "[redacted API key]", value)
        return value
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def publish(event):
    with LOCK:
        item = redact({
            **event,
            "id": EVENTS[-1]["id"] + 1 if EVENTS else 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        EVENTS.append(item)
        EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with EVENTS_PATH.open("a", encoding="utf-8") as event_file:
            event_file.write(json.dumps(item, ensure_ascii=True) + "\n")


def get_overview():
    overview = {"dbt": None, "tables": [], "source": None}
    if RUN_RESULTS_PATH.is_file():
        try:
            artifact = json.loads(RUN_RESULTS_PATH.read_text(encoding="utf-8"))
            overview["dbt"] = {
                "generated_at": artifact.get("metadata", {}).get("generated_at"),
                "invocation_id": artifact.get("metadata", {}).get("invocation_id"),
                "results": [
                    {
                        "status": result.get("status"),
                        "unique_id": result.get("unique_id"),
                        "execution_time": result.get("execution_time"),
                        "message": result.get("message"),
                    }
                    for result in artifact.get("results", [])
                ],
            }
        except (OSError, json.JSONDecodeError):
            overview["dbt"] = {"error": "Artefact dbt illisible."}

    if not DATABASE_PATH.is_file():
        return overview

    try:
        connection = duckdb.connect(str(DATABASE_PATH), read_only=True)
        try:
            available = {
                row[0]
                for row in connection.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'main'"
                ).fetchall()
            }
            for table_name in ("raw_orders", "stg_orders"):
                if table_name not in available:
                    continue
                try:
                    cursor = connection.execute(f'SELECT * FROM "{table_name}" LIMIT 8')
                    columns = [column[0] for column in cursor.description]
                    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                    count = connection.execute(
                        f'SELECT COUNT(*) FROM "{table_name}"'
                    ).fetchone()[0]
                    overview["tables"].append(
                        {"name": table_name, "columns": columns, "rows": rows, "count": count}
                    )
                except duckdb.Error as error:
                    overview["tables"].append(
                        {"name": table_name, "error": str(error), "columns": [], "rows": []}
                    )
            if "raw_orders" in available:
                overview["source"] = connection.execute(
                    "SELECT COUNT(*) AS row_count, "
                    "COUNT(*) FILTER (WHERE TRY_CAST(amount AS FLOAT) IS NULL) "
                    "AS invalid_amounts FROM raw_orders"
                ).fetchone()
                overview["source"] = {
                    "row_count": overview["source"][0],
                    "invalid_amounts": overview["source"][1],
                }
        finally:
            connection.close()
    except duckdb.Error as error:
        overview["data_error"] = str(error)
    return overview


def run_operation(operation, worker):
    with LOCK:
        if STATE["running"]:
            return False
        STATE.update(running=True, operation=operation, status="running")
    publish(
        {
            "type": "operation_started",
            "message": "Nouvelle opération démarrée.",
            "operation": operation,
        }
    )

    def execute():
        try:
            code = worker()
            status = "succeeded" if code == 0 else "failed"
            message = "Opération terminée avec succès." if code == 0 else "L’opération a échoué."
        except Exception as error:
            status = "failed"
            message = f"Erreur : {error}"
        with LOCK:
            STATE.update(running=False, status=status)
        publish(
            {
                "type": "operation_finished" if status == "succeeded" else "operation_failed",
                "message": message,
                "operation": operation,
                "status": status,
            }
        )

    threading.Thread(target=execute, daemon=True).start()
    return True


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format_string, *args):
        print(f"Dashboard: {format_string % args}")

    def send_json(self, payload, status=200):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            after = int(parse_qs(parsed.query).get("after", ["0"])[0])
            with LOCK:
                events = [event for event in EVENTS if event["id"] > after]
                state = dict(STATE)
                last_id = EVENTS[-1]["id"] if EVENTS else 0
            self.send_json({"state": state, "events": events, "last_id": last_id})
            return
        if parsed.path == "/api/overview":
            self.send_json(get_overview())
            return

        static_files = {
            "/": "index.html",
            "/app.css": "app.css",
            "/app.js": "app.js",
        }
        filename = static_files.get(parsed.path)
        if filename is None:
            self.send_error(404)
            return
        content_type = "text/html; charset=utf-8" if filename.endswith(".html") else (
            "text/css; charset=utf-8" if filename.endswith(".css") else "text/javascript; charset=utf-8"
        )
        try:
            body = (STATIC_ROOT / filename).read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            self.send_json({"error": "Content-Type application/json requis."}, 415)
            return
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            self.send_json({"error": "Origine non autorisée."}, 403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 4096:
                raise ValueError("Requête trop volumineuse.")
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self.send_json({"error": "Corps JSON invalide."}, 400)
            return

        if self.path == "/api/pipeline":
            started = run_operation(
                "pipeline", lambda: run_pipeline.main(on_event=publish)
            )
        elif self.path == "/api/repair":
            dry_run = payload.get("dry_run") is not False
            if not dry_run and payload.get("confirm") is not True:
                self.send_json({"error": "Confirmation requise pour promouvoir le SQL."}, 400)
                return
            if not os.environ.get("GEMINI_API_KEY") and os.environ.get(
                "LITELLM_MODEL", "gemini/gemini-3.1-flash-lite"
            ).startswith("gemini/"):
                self.send_json(
                    {"error": "GEMINI_API_KEY absente. Configure-la dans .env puis redémarre le tableau de bord."},
                    400,
                )
                return
            started = run_operation(
                "repair",
                lambda: agent_repair.repair_model(
                    Path("error_logs.txt"),
                    os.environ.get("LITELLM_MODEL", "gemini/gemini-3.1-flash-lite"),
                    dry_run,
                    16,
                    3,
                    on_event=publish,
                ),
            )
        else:
            self.send_json({"error": "Action inconnue."}, 404)
            return

        if not started:
            self.send_json({"error": "Une opération est déjà en cours."}, 409)
            return
        self.send_json({"started": True}, 202)


def main():
    load_events()
    requested_port = int(os.environ.get("DASHBOARD_PORT", "8765"))
    try:
        server = ThreadingHTTPServer(("127.0.0.1", requested_port), DashboardHandler)
    except OSError:
        server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    port = server.server_address[1]
    print(f"Self-Healing Pipeline dashboard: http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du tableau de bord.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()