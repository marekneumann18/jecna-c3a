#!/usr/bin/env python3
import http.server
import json
import os
import sys
import threading
import time
import urllib.parse
from supl_service import (
    load_config,
    save_config,
    fetch_raw_api_data,
    parse_schedule_for_class,
    check_and_notify_changes,
    create_discord_payload,
    send_discord_webhook,
    CONFIG_FILE
)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
BACKGROUND_STOP = threading.Event()


def background_watcher():
    print("[Watcher] Automatická kontrola spuštěna v pozadí.")
    while not BACKGROUND_STOP.is_set():
        cfg = load_config()
        interval = max(60, int(cfg.get("check_interval_seconds", 300)))
        try:
            res = check_and_notify_changes(force_notify=False)
            if res.get("sent_count", 0) > 0:
                print(f"[Watcher] Odesláno {res['sent_count']} notifikací na Discord: {res['logs']}")
        except Exception as e:
            print(f"[Watcher] Chyba při kontrole suplování: {e}")

        # Sleep interval in small chunks to allow quick termination
        for _ in range(interval):
            if BACKGROUND_STOP.is_set():
                break
            time.sleep(1)


class SuplRequestHandler(http.server.BaseHTTPRequestHandler):
    def end_headers(self):
        # Enable CORS and disable caching for API
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def send_json(self, status_code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/data":
            try:
                cfg = load_config()
                target_class = cfg.get("target_class", "C3a")
                raw = fetch_raw_api_data()
                parsed = parse_schedule_for_class(raw, target_class=target_class)
                self.send_json(200, parsed)
            except Exception as e:
                self.send_json(500, {"error": f"Chyba při stahování dat ze školy: {str(e)}"})
            return

        elif path == "/api/config":
            cfg = load_config()
            safe_cfg = dict(cfg)
            self.send_json(200, safe_cfg)
            return

        elif path == "/api/timetable":
            from supl_service import load_timetable
            tt = load_timetable()
            self.send_json(200, tt)
            return

        # Serve static files
        if path == "/" or path == "":
            file_path = os.path.join(STATIC_DIR, "index.html")
        else:
            safe_name = os.path.normpath(path.lstrip("/"))
            file_path = os.path.join(STATIC_DIR, safe_name)

        if os.path.exists(file_path) and os.path.isfile(file_path):
            content_type = "text/plain"
            if file_path.endswith(".html"):
                content_type = "text/html; charset=utf-8"
            elif file_path.endswith(".css"):
                content_type = "text/css; charset=utf-8"
            elif file_path.endswith(".js"):
                content_type = "application/javascript; charset=utf-8"
            elif file_path.endswith(".json"):
                content_type = "application/json; charset=utf-8"
            elif file_path.endswith(".svg"):
                content_type = "image/svg+xml"

            with open(file_path, "rb") as f:
                content = f.read()

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            req_data = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            req_data = {}

        if path == "/api/config":
            cfg = load_config()
            if "discord_webhook_url" in req_data:
                cfg["discord_webhook_url"] = req_data["discord_webhook_url"].strip()
            if "target_class" in req_data and req_data["target_class"]:
                cfg["target_class"] = req_data["target_class"].strip()
            if "check_interval_seconds" in req_data:
                cfg["check_interval_seconds"] = max(60, int(req_data["check_interval_seconds"]))
            if "notify_on_in_work" in req_data:
                cfg["notify_on_in_work"] = bool(req_data["notify_on_in_work"])

            save_config(cfg)
            self.send_json(200, {"success": True, "message": "Nastavení uloženo", "config": cfg})
            return

        elif path == "/api/test-discord":
            cfg = load_config()
            webhook_url = req_data.get("discord_webhook_url") or cfg.get("discord_webhook_url")

            if not webhook_url:
                self.send_json(400, {"error": "Chybí Discord Webhook URL. Zadejte ji prosím nejprve do nastavení."})
                return

            try:
                target_class = cfg.get("target_class", "C3a")
                raw = fetch_raw_api_data()
                parsed = parse_schedule_for_class(raw, target_class=target_class)

                # Use selected date from request or the first available day
                day_date = req_data.get("date")
                selected_day = None
                if day_date:
                    selected_day = next((d for d in parsed["days"] if d["date"] == day_date), None)
                if not selected_day and parsed["days"]:
                    selected_day = parsed["days"][0]

                if not selected_day:
                    self.send_json(400, {"error": "Nebyla nalezena žádná data o suplování pro test."})
                    return

                payload = create_discord_payload(selected_day, target_class=target_class, is_test=True)
                ok, msg = send_discord_webhook(webhook_url, payload)

                if ok:
                    self.send_json(200, {"success": True, "message": "Testovací zpráva byla úspěšně odeslána na Discord!"})
                else:
                    self.send_json(400, {"error": f"Discord odmítl zprávu: {msg}"})
            except Exception as e:
                self.send_json(500, {"error": f"Chyba při odesílání testovací zprávy: {str(e)}"})
            return

        elif path == "/api/check-now":
            try:
                force = req_data.get("force", False)
                res = check_and_notify_changes(force_notify=force)
                self.send_json(200, {
                    "success": True,
                    "message": f"Kontrola dokončena. Odesláno: {res['sent_count']}",
                    "logs": res["logs"],
                    "data": res["parsed_data"]
                })
            except Exception as e:
                self.send_json(500, {"error": f"Chyba při kontrole: {str(e)}"})
            return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"404 Not Found")


def run_server(port=8080):
    cfg = load_config()
    server_port = int(cfg.get("port", port))
    server_address = ("0.0.0.0", server_port)

    # Start watcher thread
    watcher_thread = threading.Thread(target=background_watcher, daemon=True)
    watcher_thread.start()

    httpd = http.server.ThreadingHTTPServer(server_address, SuplRequestHandler)
    print(f"===========================================================")
    print(f" Ječná Suplování C3a běží na:")
    print(f" -> http://localhost:{server_port}")
    print(f" -> http://127.0.0.1:{server_port}")
    print(f"===========================================================")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nUkončuji server...")
        BACKGROUND_STOP.set()
        httpd.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    p = 8080
    if len(sys.argv) > 1:
        try:
            p = int(sys.argv[1])
        except ValueError:
            pass
    run_server(p)
