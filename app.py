from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
DB_PATH = ROOT / "data" / "helio.db"
TOKEN = "helio-demo-session-v1"
LOCK = threading.Lock()

SERVICES = [
    ("svc-1", "checkout-api", "Production", "healthy", "api", 99.98, 183, 42, "2m ago"),
    ("svc-2", "identity-service", "Production", "healthy", "api", 99.99, 76, 28, "1m ago"),
    ("svc-3", "billing-worker", "Production", "degraded", "worker", 99.43, 324, 81, "just now"),
    ("svc-4", "catalog-api", "Production", "healthy", "api", 99.97, 143, 38, "3m ago"),
    ("svc-5", "notifications", "Production", "healthy", "worker", 99.89, 51, 36, "4m ago"),
    ("svc-6", "search-indexer", "Staging", "warning", "worker", 98.77, 217, 72, "8m ago"),
]

def conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection

def init_db():
    with LOCK, conn() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, title TEXT, service TEXT, severity TEXT, status TEXT, opened_at TEXT, detail TEXT);
        CREATE TABLE IF NOT EXISTS actions(id INTEGER PRIMARY KEY AUTOINCREMENT, deployment TEXT, namespace TEXT, previous_replicas INTEGER, replicas INTEGER, actor TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, subject TEXT, created_at TEXT);
        """)
        if not db.execute("SELECT count(*) FROM alerts").fetchone()[0]:
            db.executemany("INSERT INTO alerts VALUES (?, ?, ?, ?, ?, ?, ?)", [
                (1, "Checkout latency exceeds SLO", "checkout-api", "critical", "open", "09:41", "p95 latency is 812ms against a 450ms objective."),
                (2, "Memory pressure trending up", "billing-worker", "high", "open", "09:28", "Container memory has grown 18% in the last 15 minutes."),
                (3, "Search replicas unavailable", "search-indexer", "medium", "acknowledged", "08:56", "One staging replica has not reported a ready probe."),
                (4, "Certificate rotation due", "identity-service", "low", "open", "Yesterday", "mTLS certificate expires in 13 days."),
            ])
        db.commit()

def rows(query, args=()):
    with conn() as db: return [dict(r) for r in db.execute(query, args).fetchall()]

def now(): return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

class HelioHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(ROOT / "web"), **kwargs)
    def log_message(self, fmt, *args): print(f"{self.log_date_time_string()} · {fmt % args}")
    def json(self, body, code=200):
        encoded = json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(encoded))); self.end_headers(); self.wfile.write(encoded)
    def body(self):
        size = int(self.headers.get("Content-Length", 0)); return json.loads(self.rfile.read(size) or "{}")
    def authorized(self):
        return self.headers.get("Authorization") == f"Bearer {TOKEN}"
    def do_GET(self):
        route = urlparse(self.path).path
        if route == "/health": return self.json({"status":"ok", "time":now()})
        if route.startswith("/api/") and not self.authorized(): return self.json({"error":"Authentication required"}, 401)
        if route == "/api/overview": return self.json(overview())
        if route == "/api/services": return self.json({"services":[service_dict(x) for x in SERVICES]})
        if route == "/api/alerts": return self.json({"alerts": rows("SELECT * FROM alerts ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END")})
        if route == "/api/kubernetes": return self.json(kubernetes())
        if route == "/api/predictions": return self.json(predictions())
        if route == "/api/logs": return self.json(logs())
        if route == "/api/audit": return self.json({"events":rows("SELECT * FROM audit ORDER BY id DESC LIMIT 10")})
        return super().do_GET()
    def do_POST(self):
        route = urlparse(self.path).path
        payload = self.body()
        if route == "/api/auth/login":
            if payload.get("email") == "operator@helio.dev" and payload.get("password") == "demo123":
                return self.json({"access_token":TOKEN,"user":{"name":"Avery Morgan","role":"Platform Operator","initials":"AM"}})
            return self.json({"error":"Invalid email or password"}, 401)
        if not self.authorized(): return self.json({"error":"Authentication required"}, 401)
        if route.startswith("/api/alerts/") and route.endswith("/acknowledge"):
            alert_id = route.split("/")[3]
            with LOCK, conn() as db:
                db.execute("UPDATE alerts SET status = 'acknowledged' WHERE id = ?", (alert_id,)); db.execute("INSERT INTO audit(action,subject,created_at) VALUES(?,?,?)", ("Acknowledged alert", f"Alert #{alert_id}", now())); db.commit()
            return self.json({"ok":True})
        if route == "/api/kubernetes/scale":
            deployment, namespace, replicas = payload.get("deployment"), payload.get("namespace", "production"), int(payload.get("replicas", 0))
            if not deployment or not 1 <= replicas <= 40: return self.json({"error":"Deployment and replicas (1–40) are required"}, 422)
            with LOCK, conn() as db:
                previous = 6 if deployment == "checkout-api" else 3
                db.execute("INSERT INTO actions(deployment,namespace,previous_replicas,replicas,actor,created_at) VALUES(?,?,?,?,?,?)", (deployment, namespace, previous, replicas, "Avery Morgan", now()))
                db.execute("INSERT INTO audit(action,subject,created_at) VALUES(?,?,?)", ("Scaled deployment", f"{deployment}: {previous} → {replicas}", now())); db.commit()
            return self.json({"ok":True,"message":f"{deployment} scaled to {replicas} replicas"})
        if route == "/api/logs/analyze":
            sample = payload.get("text", "")
            signal = "Connection pool exhaustion" if "pool" in sample.lower() or not sample else "Elevated request latency"
            return self.json({"summary":f"{signal} is the strongest correlated signal.","confidence":0.87,"recommendation":"Increase the checkout worker pool temporarily, then inspect slow database queries and recent deploy changes.","sources":3})
        return self.json({"error":"Not found"}, 404)

def service_dict(x):
    return dict(id=x[0], name=x[1], environment=x[2], status=x[3], kind=x[4], uptime=x[5], rps=x[6], latency=x[7], last_seen=x[8])
def overview():
    alert_count = len(rows("SELECT id FROM alerts WHERE status = 'open'"))
    return {"health":99.94,"open_alerts":alert_count,"services":len(SERVICES),"nodes":12,"requests":"1.84M","change":"+12.4%", "traffic":[41,45,43,54,52,61,69,66,74,83,77,91,96,88,102,108,112,106,119,126,121,139,147,142], "regions":[{"name":"us-east-1","value":99.99},{"name":"eu-west-1","value":99.96},{"name":"ap-south-1","value":99.87}]}
def kubernetes():
    actions = rows("SELECT deployment,namespace,previous_replicas,replicas,actor,created_at FROM actions ORDER BY id DESC LIMIT 5")
    return {"cluster":{"name":"core-production","version":"v1.30.2","nodes":12,"pods":146,"deployments":28,"cpu":64,"memory":71}, "deployments":[{"name":"checkout-api","namespace":"production","ready":"6 / 6","replicas":6,"cpu":78,"status":"degraded"},{"name":"identity-service","namespace":"production","ready":"4 / 4","replicas":4,"cpu":39,"status":"healthy"},{"name":"billing-worker","namespace":"production","ready":"3 / 3","replicas":3,"cpu":86,"status":"warning"},{"name":"catalog-api","namespace":"production","ready":"5 / 5","replicas":5,"cpu":42,"status":"healthy"}], "actions": actions or [{"deployment":"checkout-api","namespace":"production","previous_replicas":4,"replicas":6,"actor":"Autoscaler","created_at":"Today, 09:34 UTC"}]}
def predictions():
    return {"traffic":{"service":"checkout-api","expected":268,"unit":"req/s","confidence":[232,301],"recommendation":8,"current":6,"points":[132,144,151,168,179,204,223,242,257,268]}, "maintenance":[{"service":"billing-worker","risk":78,"cause":"Memory saturation","recommendation":"Raise memory limit to 1.5Gi and investigate the invoice batch leak."},{"service":"checkout-api","risk":42,"cause":"Database connection pressure","recommendation":"Review connection pool configuration before peak traffic."},{"service":"catalog-api","risk":12,"cause":"Stable baseline","recommendation":"No action required."}]}
def logs():
    return {"entries":[{"time":"09:43:12.194","level":"ERROR","service":"checkout-api","message":"timeout acquiring database connection from pool"},{"time":"09:42:51.009","level":"WARN","service":"checkout-api","message":"p95 request duration above configured objective"},{"time":"09:41:23.881","level":"INFO","service":"billing-worker","message":"invoice batch 2026-09-02 started"},{"time":"09:40:04.335","level":"ERROR","service":"billing-worker","message":"container memory working set over 91 percent"},{"time":"09:39:14.221","level":"INFO","service":"identity-service","message":"token signing key rotation check completed"}]}

if __name__ == "__main__":
    init_db(); print("Helio Operations at http://localhost:8080")
    ThreadingHTTPServer(("0.0.0.0", 8080), HelioHandler).serve_forever()
