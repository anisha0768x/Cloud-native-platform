from __future__ import annotations

from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

class Scale(BaseModel):
    replicas: int
class Analyze(BaseModel):
    text: str
class Notification(BaseModel):
    alert_id: str
    channel: str = "slack"
class Metric(BaseModel):
    service_id: str
    metric_name: str
    value: float

def create_app(service: str) -> FastAPI:
    app = FastAPI(title=f"Helio {service}", version="1.0.0")
    @app.get("/health")
    def health(): return {"status":"ok","service":service,"time":now()}
    @app.get("/ready")
    def ready(): return {"status":"ready","service":service}
    if service == "monitoring-service":
        @app.get("/api/v1/services")
        def services(): return {"services":[{"id":"svc-checkout","name":"checkout-api","status":"degraded","uptime":99.98},{"id":"svc-identity","name":"identity-service","status":"healthy","uptime":99.99}]}
        @app.get("/api/v1/alerts")
        def alerts(): return {"alerts":[{"id":"alert-001","severity":"critical","status":"open","service":"checkout-api"}]}
    elif service == "metrics-service":
        @app.post("/api/v1/metrics/ingest")
        def ingest(metric: Metric): return {"accepted":True,"topic":"metrics.raw","metric":metric.model_dump()}
        @app.get("/api/v1/metrics/query")
        def query(service_id: str, metric_name: str): return {"service_id":service_id,"metric_name":metric_name,"aggregation":"avg","points":[{"time":now(),"value":64.0}]}
    elif service == "traffic-prediction-service":
        @app.get("/api/v1/predictions/traffic/{service_id}")
        def traffic(service_id: str): return {"service_id":service_id,"expected_requests":268,"confidence_interval":{"p10":232,"p90":301},"scaling_recommendation":8}
    elif service == "predictive-maintenance-service":
        @app.get("/api/v1/predictions/maintenance/{service_id}")
        def maintenance(service_id: str): return {"service_id":service_id,"failure_probability":0.42,"root_cause":"memory saturation","recommendation":"Review memory limits and restart trend."}
    elif service == "genai-log-analysis-service":
        @app.post("/api/v1/genai/analyze")
        def analyze(body: Analyze): return {"root_cause_summary":"Rule-based fallback analysis completed.","suggested_fix":"Inspect correlated metrics and recent deployment changes.","confidence":0.72,"pii_scrubbed":True}
    elif service == "notification-service":
        @app.post("/api/v1/notifications/send")
        def notify(body: Notification): return {"status":"sent","alert_id":body.alert_id,"channel":body.channel,"sent_at":now()}
    elif service == "dashboard-service":
        @app.get("/api/v1/dashboards/{name}")
        def dashboard(name: str):
            if name not in {"executive","api","traffic","infrastructure","kubernetes","containers","ai","security","cloud-cost","logs","settings"}: raise HTTPException(404,"Unknown dashboard")
            return {"dashboard":name,"generated_at":now(),"partial_errors":[]}
    elif service == "k8s-management-service":
        @app.get("/api/v1/k8s/nodes")
        def nodes(): return {"nodes":[{"name":"node-1","status":"ready","cpu":64,"memory":71}]}
        @app.get("/api/v1/k8s/pods")
        def pods(): return {"pods":[{"name":"checkout-api-1","status":"running","restarts":1}]}
        @app.post("/api/v1/k8s/deployments/{namespace}/{name}/scale")
        def scale(namespace: str, name: str, body: Scale): return {"deployment":name,"namespace":namespace,"replicas":body.replicas,"executed_at":now()}
    elif service == "cloud-storage-service":
        @app.get("/api/v1/storage/objects")
        def objects(prefix: str = ""): return {"prefix":prefix,"objects":[]}
    elif service == "cloud-sql-service":
        @app.get("/api/v1/audit")
        def audit(): return {"events":[]}
        @app.get("/api/v1/configurations/{service_id}")
        def configs(service_id: str): return {"service_id":service_id,"configurations":[]}
    return app
