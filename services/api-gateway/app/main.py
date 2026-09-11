"""Local API gateway/BFF runtime.

In production this service validates JWTs, rate-limits at Redis and routes to
the independently deployed services. Local development supplies deterministic
data when those dependencies are unavailable, so the React-equivalent UI can
exercise the full control-plane workflow offline.
"""
from __future__ import annotations

import asyncio
import json
import hashlib
from math import sin, pi
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[3]
DB_PATH = ROOT / "data" / "platform.db"
TOKEN = "helio-local-access-token"
app = FastAPI(title="Helio API Gateway", version="1.0.0", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:8080"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

SERVICES = [
    {"id":"svc-checkout","name":"checkout-api","environment":"production","status":"degraded","kind":"api","uptime":99.98,"rps":183,"latency":812,"last_seen":"just now"},
    {"id":"svc-identity","name":"identity-service","environment":"production","status":"healthy","kind":"api","uptime":99.99,"rps":76,"latency":28,"last_seen":"1m ago"},
    {"id":"svc-billing","name":"billing-worker","environment":"production","status":"warning","kind":"worker","uptime":99.43,"rps":324,"latency":81,"last_seen":"just now"},
    {"id":"svc-catalog","name":"catalog-api","environment":"production","status":"healthy","kind":"api","uptime":99.97,"rps":143,"latency":38,"last_seen":"3m ago"},
]

def utcnow() -> str: return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True); con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row; return con
def require_auth(authorization: str | None) -> None:
    if authorization != f"Bearer {TOKEN}": raise HTTPException(401, "Authentication required")
def audit(action: str, resource: str, before: str = "{}", after: str = "{}") -> None:
    with db() as con:
        con.execute("INSERT INTO audit_logs(event_id,actor,action,resource,before_state,after_state,created_at) VALUES(?,?,?,?,?,?,?)", (str(uuid4()),"operator@helio.dev",action,resource,before,after,utcnow()))
def initialize() -> None:
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS alerts (id TEXT PRIMARY KEY, title TEXT, service TEXT, severity TEXT, status TEXT, opened_at TEXT, detail TEXT);
        CREATE TABLE IF NOT EXISTS scaling_history (id TEXT PRIMARY KEY, deployment TEXT, namespace TEXT, previous_replicas INTEGER, replicas INTEGER, actor TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS audit_logs (event_id TEXT PRIMARY KEY, actor TEXT, action TEXT, resource TEXT, before_state TEXT, after_state TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS notifications (id TEXT PRIMARY KEY, alert_id TEXT, channel TEXT, status TEXT, sent_at TEXT);
        CREATE TABLE IF NOT EXISTS metric_points (event_id TEXT PRIMARY KEY, service_id TEXT, metric_name TEXT, value REAL, labels TEXT, occurred_at TEXT);
        CREATE TABLE IF NOT EXISTS configurations (id TEXT PRIMARY KEY, service_id TEXT, config_key TEXT, config_value TEXT, updated_by TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS registered_services (id TEXT PRIMARY KEY, name TEXT UNIQUE, environment TEXT, kind TEXT, namespace TEXT, owner_team TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS storage_objects (id TEXT PRIMARY KEY, object_name TEXT UNIQUE, bucket TEXT, size_kb INTEGER, storage_class TEXT, encrypted INTEGER, retention_days INTEGER, created_at TEXT);
        """)
        if not con.execute("SELECT count(*) FROM alerts").fetchone()[0]:
            con.executemany("INSERT INTO alerts VALUES(?,?,?,?,?,?,?)", [
              ("alert-001","Checkout latency exceeds SLO","checkout-api","critical","open","09:41","p95 latency is 812ms against a 450ms objective."),
              ("alert-002","Memory pressure trending up","billing-worker","high","open","09:28","Container memory has grown 18% in the last 15 minutes."),
              ("alert-003","Search replica unavailable","search-indexer","medium","acknowledged","08:56","One staging replica has not reported ready."),
              ("alert-004","Certificate rotation due","identity-service","low","open","Yesterday","mTLS certificate expires in 13 days.")])
        if not con.execute("SELECT count(*) FROM notifications").fetchone()[0]:
            con.executemany("INSERT INTO notifications VALUES(?,?,?,?,?)", [
              ("notice-001","alert-001","slack","delivered","09:42"),
              ("notice-002","alert-002","email","delivered","09:29"),
              ("notice-003","alert-004","slack","queued","Yesterday")])

class Login(BaseModel): email: str; password: str
class ScaleRequest(BaseModel): deployment: str; namespace: str = "production"; replicas: int = Field(ge=1, le=40)
class AnalyzeRequest(BaseModel): text: str = Field(min_length=4, max_length=20000)
class MetricIngest(BaseModel): service_id: str; metric_name: str; value: float; labels: dict[str, str] = {}; occurred_at: str | None = None
class NotificationRequest(BaseModel): alert_id: str; channel: Literal["email", "slack", "webhook"] = "slack"
class ConfigurationRequest(BaseModel): service_id: str; key: str; value: str
class ServiceRegistration(BaseModel):
    name: str = Field(min_length=3, max_length=64, pattern=r"^[a-z][a-z0-9-]+$")
    environment: Literal["production", "staging", "development"] = "production"
    kind: Literal["api", "worker", "cron"] = "api"
    namespace: str = Field(default="production", min_length=2, max_length=63)
    owner_team: str = Field(default="platform", min_length=2, max_length=64)
class StorageObject(BaseModel):
    object_name: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._/-]+$")
    bucket: str = Field(default="platform-audit-archive", min_length=3, max_length=63)
    size_kb: int = Field(default=128, ge=1, le=1048576)
    storage_class: Literal["standard", "nearline", "coldline", "archive"] = "standard"
    retention_days: int = Field(default=90, ge=1, le=3650)

@app.on_event("startup")
def startup(): initialize()
@app.get("/health", tags=["platform"])
def health(): return {"status":"ok","service":"api-gateway","time":utcnow()}
@app.get("/ready", tags=["platform"])
def ready(): return {"status":"ready","dependencies":{"postgres":"local-fallback","redis":"local-fallback","kafka":"local-fallback"}}
@app.post("/api/v1/auth/login", tags=["auth"])
@app.post("/api/auth/login", tags=["auth"])
def login(payload: Login):
    if payload.email != "operator@helio.dev" or payload.password != "demo123": raise HTTPException(401,"Invalid email or password")
    audit("user.login",payload.email)
    return {"access_token":TOKEN,"token_type":"bearer","expires_in":900,"user":{"name":"Anisha Verma","email":payload.email,"role":"Platform Operator","permissions":["services:read","alerts:acknowledge","scaling:trigger","logs:analyze"]}}
@app.get("/api/overview", tags=["dashboards"])
def overview(authorization: str | None = Header(default=None)):
    require_auth(authorization); open_count = len([x for x in alerts() if x["status"]=="open"])
    phase = datetime.now(timezone.utc).minute
    baseline = [41,45,43,54,52,61,69,66,74,83,77,91,96,88,102,108,112,106,119,126,121,139,147,142]
    traffic = [max(1, round(value + sin((index + phase) / 3 * pi) * 5)) for index, value in enumerate(baseline)]
    current_rps = traffic[-1]
    return {"health":round(99.90 + sin(phase / 60 * pi) * .04, 2),"open_alerts":open_count,"services":len(all_services()),"nodes":12,"requests":f"{1.80 + current_rps / 3500:.2f}M","change":f"{4 + current_rps / 15:.1f}%","traffic":traffic,"regions":[{"name":"us-east-1","value":99.99},{"name":"eu-west-1","value":99.96},{"name":"ap-south-1","value":99.87}],"data_mode":"simulated-local","generated_at":utcnow()}
def all_services():
    with db() as con: registered=[dict(row) for row in con.execute("SELECT * FROM registered_services ORDER BY created_at DESC")]
    return SERVICES + [{"id":row["id"],"name":row["name"],"environment":row["environment"],"status":"healthy","kind":row["kind"],"uptime":100.0,"rps":0,"latency":0,"last_seen":"just registered","namespace":row["namespace"],"owner_team":row["owner_team"]} for row in registered]
@app.get("/api/v1/services", tags=["monitoring"])
@app.get("/api/services", tags=["monitoring"])
def services(authorization: str | None = Header(default=None)):
    require_auth(authorization); return {"services":all_services()}
@app.post("/api/v1/services", tags=["monitoring"], status_code=201)
@app.post("/api/services", tags=["monitoring"], status_code=201)
def register_service(payload: ServiceRegistration, authorization: str | None = Header(default=None)):
    require_auth(authorization)
    if any(service["name"] == payload.name for service in SERVICES): raise HTTPException(409,"A built-in service already uses that name")
    service_id=f"svc-{uuid4().hex[:12]}"
    try:
        with db() as con: con.execute("INSERT INTO registered_services VALUES(?,?,?,?,?,?,?)",(service_id,payload.name,payload.environment,payload.kind,payload.namespace,payload.owner_team,utcnow()))
    except sqlite3.IntegrityError: raise HTTPException(409,"A registered service already uses that name")
    audit("service.registered",service_id)
    return {"id":service_id,**payload.model_dump(),"status":"healthy","created_at":utcnow()}
def alerts():
    with db() as con: return [dict(r) for r in con.execute("SELECT * FROM alerts ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END")]
@app.get("/api/v1/alerts", tags=["monitoring"])
@app.get("/api/alerts", tags=["monitoring"])
def list_alerts(authorization: str | None = Header(default=None)):
    require_auth(authorization); return {"alerts":alerts()}
@app.post("/api/v1/alerts/{alert_id}/acknowledge", tags=["monitoring"])
@app.post("/api/alerts/{alert_id}/acknowledge", tags=["monitoring"])
def acknowledge(alert_id: str, authorization: str | None = Header(default=None)):
    require_auth(authorization)
    with db() as con:
        alert=con.execute("SELECT title,service,severity FROM alerts WHERE id=? AND status='open'",(alert_id,)).fetchone()
        updated=con.execute("UPDATE alerts SET status='acknowledged' WHERE id=? AND status='open'",(alert_id,)).rowcount
    if not updated: raise HTTPException(404,"Open alert not found")
    followup_id=f"alert-followup-{uuid4().hex[:8]}"; notice_id=str(uuid4())
    followup_title=f"Follow-up investigation: {alert['service']}"
    with db() as con:
        con.execute("INSERT INTO alerts VALUES(?,?,?,?,?,?,?)",(followup_id,followup_title,alert["service"],"medium","open",utcnow(),f"Created after acknowledgement of {alert['title']}. Review remediation progress and close when verified."))
        con.execute("INSERT INTO notifications VALUES(?,?,?,?,?)",(notice_id,alert_id,"slack","delivered",utcnow()))
    audit("alert.acknowledged",alert_id); audit("alert.followup_created",followup_id)
    return {"ok":True,"event":"alerts.acknowledged","follow_up_alert":{"id":followup_id,"title":followup_title},"notification_id":notice_id}
@app.get("/api/v1/metrics/query", tags=["metrics"])
def metrics_query(service_id: str = "svc-checkout", metric_name: str = "request_count", authorization: str | None = Header(default=None)):
    require_auth(authorization); return {"service_id":service_id,"metric_name":metric_name,"aggregation":"avg","points":[{"time":f"{h:02}:00","value":v} for h,v in enumerate([41,45,43,54,52,61,69,66,74,83,77,91])],"source":"local-development"}
@app.post("/api/v1/metrics/ingest", tags=["metrics"])
def ingest_metric(payload: MetricIngest, authorization: str | None = Header(default=None)):
    require_auth(authorization); event_id=str(uuid4()); occurred=payload.occurred_at or utcnow()
    with db() as con: con.execute("INSERT INTO metric_points VALUES(?,?,?,?,?,?)",(event_id,payload.service_id,payload.metric_name,payload.value,json.dumps(payload.labels),occurred))
    return {"accepted":True,"event_id":event_id,"topic":"metrics.raw"}
@app.get("/api/v1/metrics/latest", tags=["metrics"])
def latest_metric(service_id: str, metric_name: str, authorization: str | None = Header(default=None)):
    require_auth(authorization)
    with db() as con: row=con.execute("SELECT * FROM metric_points WHERE service_id=? AND metric_name=? ORDER BY occurred_at DESC LIMIT 1",(service_id,metric_name)).fetchone()
    return dict(row) if row else {"service_id":service_id,"metric_name":metric_name,"value":64.0,"occurred_at":utcnow(),"source":"synthetic"}
@app.get("/api/kubernetes", tags=["kubernetes"])
def kubernetes(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    with db() as con: history=[dict(r) for r in con.execute("SELECT deployment,namespace,previous_replicas,replicas,actor,created_at FROM scaling_history ORDER BY created_at DESC LIMIT 5")]
    return {"cluster":{"name":"core-production","version":"v1.30.2","nodes":12,"pods":146,"deployments":28,"cpu":64,"memory":71},"deployments":[{"name":"checkout-api","namespace":"production","ready":"6 / 6","replicas":6,"cpu":78,"status":"degraded"},{"name":"identity-service","namespace":"production","ready":"4 / 4","replicas":4,"cpu":39,"status":"healthy"},{"name":"billing-worker","namespace":"production","ready":"3 / 3","replicas":3,"cpu":86,"status":"warning"},{"name":"catalog-api","namespace":"production","ready":"5 / 5","replicas":5,"cpu":42,"status":"healthy"}],"actions":history or [{"deployment":"checkout-api","namespace":"production","previous_replicas":4,"replicas":6,"actor":"Autoscaler","created_at":"Today, 09:34 UTC"}]}
@app.post("/api/kubernetes/scale", tags=["kubernetes"])
def scale(payload: ScaleRequest, authorization: str | None = Header(default=None)):
    require_auth(authorization); old=6 if payload.deployment=="checkout-api" else 3; action_id=str(uuid4())
    with db() as con: con.execute("INSERT INTO scaling_history VALUES(?,?,?,?,?,?,?)",(action_id,payload.deployment,payload.namespace,old,payload.replicas,"Anisha Verma",utcnow()))
    audit("scaling.executed",payload.deployment,f'{{"replicas":{old}}}',f'{{"replicas":{payload.replicas}}}')
    return {"ok":True,"event":"scaling.executed","message":f"{payload.deployment} scaled to {payload.replicas} replicas"}
@app.get("/api/predictions", tags=["prediction"])
def predictions(authorization: str | None = Header(default=None)):
    require_auth(authorization); return {"traffic":{"service":"checkout-api","expected":268,"unit":"req/s","confidence":[232,301],"recommendation":8,"current":6,"points":[132,144,151,168,179,204,223,242,257,268]},"maintenance":[{"service":"billing-worker","risk":78,"cause":"Memory saturation","recommendation":"Raise memory limit to 1.5Gi and investigate the invoice batch leak."},{"service":"checkout-api","risk":42,"cause":"Database connection pressure","recommendation":"Review connection pool configuration before peak traffic."},{"service":"catalog-api","risk":12,"cause":"Stable baseline","recommendation":"No action required."}]}
@app.get("/api/v1/predictions/traffic/{service_id}", tags=["traffic-prediction"])
def traffic_prediction(service_id: str, horizon_hours: int = Query(default=1, ge=1, le=168), authorization: str | None = Header(default=None)):
    require_auth(authorization); expected=268 + horizon_hours * 4
    return {"service_id":service_id,"horizon_hours":horizon_hours,"expected_requests":expected,"confidence_interval":{"p10":round(expected*.86),"p90":round(expected*1.12)},"scaling_recommendation":{"target_replicas":8,"requests_per_pod_capacity":40},"data_source":"synthetic-local"}
@app.get("/api/v1/predictions/maintenance/{service_id}", tags=["predictive-maintenance"])
def maintenance_prediction(service_id: str, authorization: str | None = Header(default=None)):
    require_auth(authorization); return {"service_id":service_id,"failure_probability":0.78 if service_id=="svc-billing" else 0.42,"root_cause":"memory saturation" if service_id=="svc-billing" else "database connection pressure","recommendation":"Investigate rising resource use and review capacity before the next peak.","model":"xgboost-local-fallback"}
@app.get("/api/logs", tags=["logs"])
def logs(authorization: str | None = Header(default=None)):
    require_auth(authorization); return {"entries":[{"time":"09:43:12.194","level":"ERROR","service":"checkout-api","message":"timeout acquiring database connection from pool"},{"time":"09:42:51.009","level":"WARN","service":"checkout-api","message":"p95 request duration above configured objective"},{"time":"09:41:23.881","level":"INFO","service":"billing-worker","message":"invoice batch started"},{"time":"09:40:04.335","level":"ERROR","service":"billing-worker","message":"container memory working set over 91 percent"}]}
@app.post("/api/logs/analyze", tags=["genai"])
def analyze(payload: AnalyzeRequest, authorization: str | None = Header(default=None)):
    require_auth(authorization); pool="connection pool exhaustion" if "pool" in payload.text.lower() else "elevated request latency"; audit("genai.analysis.requested","log-stream")
    summary=f"{pool.title()} is the strongest correlated signal."
    recommendation="Increase the worker pool temporarily, then inspect slow database queries and the most recent deployment."
    return {"root_cause_summary":summary,"summary":summary,"human_explanation":"The signal correlates with the active checkout latency alert and elevated resource use.","suggested_fix":recommendation,"recommendation":recommendation,"confidence":0.87,"mode":"rule-based fallback","pii_scrubbed":True}
@app.get("/api/v1/genai/summary/{alert_id}", tags=["genai"])
def genai_summary(alert_id: str, authorization: str | None = Header(default=None)):
    require_auth(authorization); return {"alert_id":alert_id,"root_cause_summary":"Elevated checkout latency is correlated with database connection-pool contention.","suggested_fix":"Inspect slow queries and expand the pool only within database capacity.","confidence":0.87,"mode":"rule-based fallback"}
@app.post("/api/v1/notifications/send", tags=["notifications"])
def send_notification(payload: NotificationRequest, authorization: str | None = Header(default=None)):
    require_auth(authorization); notice_id=str(uuid4())
    with db() as con: con.execute("INSERT INTO notifications VALUES(?,?,?,?,?)",(notice_id,payload.alert_id,payload.channel,"sent",utcnow()))
    audit("notification.sent",notice_id); return {"notification_id":notice_id,"status":"sent","channel":payload.channel}
@app.get("/api/v1/notifications", tags=["notifications"])
def notification_history(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    with db() as con: return {"notifications":[dict(r) for r in con.execute("SELECT * FROM notifications ORDER BY sent_at DESC LIMIT 50")]}
@app.get("/api/v1/dashboards/{dashboard_name}", tags=["dashboards"])
def dashboard(dashboard_name: Literal["executive","api","traffic","infrastructure","kubernetes","containers","ai","security","cloud-cost","logs","settings"], authorization: str | None = Header(default=None)):
    require_auth(authorization); return {"dashboard":dashboard_name,"generated_at":utcnow(),"partial_errors":[],"data":{"overview":overview(authorization),"alerts":alerts(),"services":SERVICES}}
@app.get("/api/v1/k8s/nodes", tags=["kubernetes"])
def k8s_nodes(authorization: str | None = Header(default=None)):
    require_auth(authorization); return {"nodes":[{"name":"ip-10-0-1-14","region":"us-east-1a","status":"ready","cpu":62,"memory":70},{"name":"ip-10-0-2-39","region":"us-east-1b","status":"ready","cpu":66,"memory":71}]}
@app.get("/api/v1/k8s/pods", tags=["kubernetes"])
def k8s_pods(namespace: str = "production", authorization: str | None = Header(default=None)):
    require_auth(authorization); return {"namespace":namespace,"pods":[{"name":"checkout-api-7b86c9c5b8-kzj8p","service":"checkout-api","status":"running","restarts":1},{"name":"billing-worker-6cb8f8fbb-cdf5q","service":"billing-worker","status":"running","restarts":4}]}
@app.put("/api/v1/configurations", tags=["cloud-sql"])
def set_configuration(payload: ConfigurationRequest, authorization: str | None = Header(default=None)):
    require_auth(authorization); config_id=str(uuid4())
    with db() as con: con.execute("INSERT INTO configurations VALUES(?,?,?,?,?,?)",(config_id,payload.service_id,payload.key,payload.value,"operator@helio.dev",utcnow()))
    audit("configuration.updated",f"{payload.service_id}:{payload.key}"); return {"id":config_id,"service_id":payload.service_id,"key":payload.key,"updated_at":utcnow()}
@app.get("/api/v1/configurations/{service_id}", tags=["cloud-sql"])
def list_configurations(service_id: str, authorization: str | None = Header(default=None)):
    require_auth(authorization)
    with db() as con: return {"configurations":[dict(r) for r in con.execute("SELECT * FROM configurations WHERE service_id=? ORDER BY updated_at DESC",(service_id,))]}
@app.get("/api/v1/audit", tags=["cloud-sql"])
def audits(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    with db() as con: return {"events":[dict(r) for r in con.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 50")]}

@app.get("/api/cloud/costs", tags=["cloud-cost"])
def cloud_costs(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    phase = datetime.now(timezone.utc).minute
    compute = round(326.40 + sin(phase / 60 * pi) * 4.2, 2)
    storage = 48.65
    network = 71.22
    total = round(compute + storage + network, 2)
    return {"currency":"USD","month":"Current month","total":total,"budget":500.00,"forecast":round(total + 96.30, 2),"line_items":[{"service":"GKE compute nodes","cost":compute,"change":"+4.2%","owner":"platform"},{"service":"Cloud SQL","cost":112.18,"change":"+1.1%","owner":"data"},{"service":"Cloud Storage","cost":storage,"change":"-2.8%","owner":"platform"},{"service":"Load balancing and egress","cost":network,"change":"+6.4%","owner":"platform"}],"recommendations":["Move immutable audit exports to archive storage after 90 days.","Scale the checkout worker pool before peak instead of keeping idle replicas all day."],"generated_at":utcnow(),"mode":"simulated-local"}

@app.get("/api/cloud/storage", tags=["cloud-storage"])
def storage_catalog(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    with db() as con: objects = [dict(row) for row in con.execute("SELECT * FROM storage_objects ORDER BY created_at DESC")]
    defaults = [{"id":"obj-001","object_name":"audit/2026-09/alert-events.json","bucket":"platform-audit-archive","size_kb":384,"storage_class":"archive","encrypted":1,"retention_days":2555,"created_at":"2026-09-01 08:30 UTC"},{"id":"obj-002","object_name":"models/traffic-forecast-v3.json","bucket":"platform-ml-artifacts","size_kb":920,"storage_class":"standard","encrypted":1,"retention_days":365,"created_at":"2026-09-02 09:00 UTC"}]
    return {"buckets":[{"name":"platform-audit-archive","region":"asia-south1","versioning":True,"encryption":"AES-256"},{"name":"platform-ml-artifacts","region":"asia-south1","versioning":True,"encryption":"CMEK"}],"objects":objects + defaults,"mode":"simulated-local"}

@app.post("/api/cloud/storage", tags=["cloud-storage"], status_code=201)
def create_storage_object(payload: StorageObject, authorization: str | None = Header(default=None)):
    require_auth(authorization)
    object_id = f"obj-{uuid4().hex[:12]}"
    try:
        with db() as con: con.execute("INSERT INTO storage_objects VALUES(?,?,?,?,?,?,?,?)", (object_id,payload.object_name,payload.bucket,payload.size_kb,payload.storage_class,1,payload.retention_days,utcnow()))
    except sqlite3.IntegrityError: raise HTTPException(409,"An object with that name already exists")
    audit("storage.object_registered",object_id)
    return {"id":object_id,**payload.model_dump(),"encrypted":True,"created_at":utcnow()}

@app.get("/api/cloud/iam", tags=["security"])
def iam_overview(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    return {"shared_responsibility":{"provider":"Physical facilities, host hardware and managed-service platform security.","customer":"Identities, application code, data classification, network policy and least-privilege access."},"roles":[{"role":"Platform Operator","members":3,"permissions":["services:read","alerts:acknowledge","scaling:trigger","logs:analyze"]},{"role":"Security Auditor","members":2,"permissions":["audit:read","storage:read","iam:read"]},{"role":"Service Developer","members":12,"permissions":["services:read","logs:read","metrics:read"]}],"controls":[{"name":"MFA for privileged roles","status":"enforced"},{"name":"TLS in transit","status":"enforced"},{"name":"Encryption at rest","status":"enforced"},{"name":"Audit logging","status":"active"}],"mode":"local-policy-model"}

@app.get("/api/cloud/network", tags=["network"])
def network_topology(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    return {"vpc":{"name":"platform-vpc","cidr":"10.42.0.0/16","region":"asia-south1"},"subnets":[{"name":"public-ingress","cidr":"10.42.10.0/24","exposure":"public","workloads":"HTTPS load balancer"},{"name":"private-services","cidr":"10.42.20.0/24","exposure":"private","workloads":"GKE workloads"},{"name":"private-data","cidr":"10.42.30.0/24","exposure":"private","workloads":"Cloud SQL and Redis"}],"flows":["Internet -> HTTPS load balancer -> API gateway -> Kubernetes services","API gateway -> private database subnet -> Cloud SQL","Audit exporter -> private egress -> Cloud Storage"],"firewall_rules":[{"name":"allow-https-ingress","direction":"ingress","ports":"TCP 443","action":"allow"},{"name":"deny-public-database","direction":"ingress","ports":"TCP 5432","action":"deny"},{"name":"allow-service-mtls","direction":"east-west","ports":"TCP 8443","action":"allow"}],"mode":"reference-architecture"}

@app.get("/api/cloud/resilience", tags=["resilience"])
def resilience_overview(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    return {"targets":{"rto":"60 minutes","rpo":"15 minutes","availability":"99.9%"},"backups":[{"asset":"Cloud SQL operational store","strategy":"Point-in-time recovery + daily backup","last_backup":"18 minutes ago","status":"healthy"},{"asset":"Audit archives","strategy":"Versioned object storage","last_backup":"7 minutes ago","status":"healthy"},{"asset":"Kubernetes manifests","strategy":"Git repository + container registry","last_backup":"On every release","status":"healthy"}],"runbook":["Detect and declare the incident.","Restore the database to the approved recovery point.","Redeploy signed containers and apply Kubernetes manifests.","Validate health checks, data integrity and audit trail before reopening traffic."],"mode":"demonstration-runbook"}

@app.get("/api/live/telemetry", tags=["telemetry"])
def live_telemetry(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    second = datetime.now(timezone.utc).second
    return {"timestamp":utcnow(),"request_rate":round(182 + sin(second / 60 * 2 * pi) * 18),"cpu":round(64 + sin(second / 60 * 2 * pi) * 9),"memory":round(71 + sin((second + 13) / 60 * 2 * pi) * 6),"latency_ms":round(412 + sin((second + 8) / 60 * 2 * pi) * 74),"source":"synthetic-live-simulator"}
@app.websocket("/ws/live")
async def live(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json({"type":"dashboard.tick","timestamp":utcnow(),"health":99.94}); await asyncio.sleep(15)
    except Exception: return

WEB = ROOT / "web"
@app.get("/", include_in_schema=False)
def home():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for asset in ("styles.css", "app.js"):
        version = hashlib.sha256((WEB / asset).read_bytes()).hexdigest()[:16]
        html = html.replace(f'"/{asset}"', f'"/{asset}?v={version}"')
    return HTMLResponse(html, headers={"Cache-Control":"no-store"})
app.mount("/", StaticFiles(directory=WEB, html=True), name="frontend")
