from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf" / "cloud_native_platform_project_report.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="Cover", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=27, leading=33, textColor=colors.HexColor("#173724"), spaceAfter=14))
styles.add(ParagraphStyle(name="Subtitle", parent=styles["Normal"], fontSize=13, leading=20, textColor=colors.HexColor("#4D6354")))
styles.add(ParagraphStyle(name="H1x", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=19, leading=24, textColor=colors.HexColor("#173724"), spaceBefore=8, spaceAfter=10))
styles.add(ParagraphStyle(name="H2x", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=colors.HexColor("#244E32"), spaceBefore=10, spaceAfter=6))
styles.add(ParagraphStyle(name="Bodyx", parent=styles["BodyText"], fontSize=9.4, leading=14, spaceAfter=7, textColor=colors.HexColor("#202820")))
styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8, leading=11, textColor=colors.HexColor("#48554A")))
styles.add(ParagraphStyle(name="Callout", parent=styles["BodyText"], fontSize=9.5, leading=14, leftIndent=10, rightIndent=10, borderPadding=10, borderColor=colors.HexColor("#B9D9A4"), borderWidth=1, backColor=colors.HexColor("#F2F8EB"), spaceBefore=6, spaceAfter=10))

def p(text, style="Bodyx"):
    return Paragraph(text, styles[style])

def table(headers, rows, widths):
    data = [[p(h, "Small") for h in headers]] + [[p(str(cell), "Small") for cell in row] for row in rows]
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1B3B28")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#C8D2C7")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F5F8F3")]),
        ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    return t

def heading(text, level=1): return p(text, "H1x" if level == 1 else "H2x")

def footer(canvas, doc):
    canvas.saveState(); canvas.setStrokeColor(colors.HexColor("#C9D5C8")); canvas.line(1.7*cm, 1.4*cm, A4[0]-1.7*cm, 1.4*cm)
    canvas.setFont("Helvetica", 8); canvas.setFillColor(colors.HexColor("#4B5D50")); canvas.drawString(1.7*cm, 0.9*cm, "Cloud-Native Intelligent Microservices Management Platform")
    canvas.drawRightString(A4[0]-1.7*cm, 0.9*cm, f"Page {doc.page}"); canvas.restoreState()

story=[]
story += [Spacer(1, 3.1*cm), p("CLOUD COMPUTING PROJECT REPORT", "Small"), Spacer(1, .35*cm), p("Cloud-Native Intelligent Microservices Management Platform", "Cover"), p("Using GenAI, Kubernetes and Predictive Auto Scaling", "Subtitle"), Spacer(1, 1.0*cm), p("Prepared for Anisha Verma", "H2x"), p("This report explains the project topic, architectural decisions, the website experience, service modules, code behavior, local data model, Docker workflow, and the path from this local demonstration to a cloud deployment.", "Subtitle"), Spacer(1, 2.0*cm), p("Document scope", "H2x"), p("The repository is a working local implementation and teaching platform. It exposes a browser dashboard and FastAPI APIs, plus service packages and deployment definitions. Some infrastructure data is deliberately simulated locally until Docker, Kubernetes and cloud services are connected. This distinction is made explicit throughout the report.", "Callout"), PageBreak()]

story += [heading("1. Project purpose"), p("The platform is an AIOps-style cloud operations control plane. Its purpose is to help an operator understand the health of microservices, observe Kubernetes workloads, interpret logs, react to alerts, and make data-informed scaling decisions. Comparable product categories include cloud monitoring, application performance monitoring, infrastructure observability and incident response platforms."), heading("Why this is a cloud computing project",2), p("Cloud computing is not only hosting a website on a server. It is the use of elastic compute, managed storage, networking, identity, automation and observability to operate software at scale. This project uses those ideas directly: independent services, container images, Kubernetes orchestration, scalable ingestion, managed data stores, role-based access, audit history, and predictive capacity planning."), table(["Cloud concept","How the project demonstrates it"],[
    ["Microservices","Twelve bounded contexts separate authentication, monitoring, metrics, predictions, logs, notifications, dashboards, Kubernetes control, storage and audit/configuration."],
    ["Containers","Each service has a Docker definition and can be started as an isolated process."],
    ["Kubernetes","The architecture uses deployments, services, health probes, namespaces, resource limits, HPA and Ingress."],
    ["Managed data","PostgreSQL, TimescaleDB, Redis, Kafka, OpenSearch and object storage each serve a different operational need."],
    ["Cloud automation","CI/CD, infrastructure-as-code, audit records and automated scaling connect software changes to operations."],
], [3.0*cm, 12.5*cm]), heading("Topic statement",2), p("Cloud-Native Intelligent Microservices Management Platform using GenAI, Kubernetes and Predictive Auto Scaling means: build an operations platform from cloud-native components; use intelligent analysis to explain failures; run and observe container workloads through Kubernetes; and forecast demand or failure risk before an outage occurs."), PageBreak()]

story += [heading("2. Architecture and data flow"), p("The production architecture follows an event-driven core with a REST control-plane edge. REST is used for user actions requiring an immediate answer, such as logging in, registering a service, acknowledging an alert or requesting a scaling change. Kafka is used for high-volume telemetry and fan-out, such as raw metrics, log events and triggered alerts."), p("Browser -> API Gateway -> service APIs is the user-facing path. Metrics agents, Kubernetes collectors and log shippers publish events -> Kafka -> Metrics, prediction, notification and GenAI consumers. Dashboard Service aggregates safe read models for the frontend."), heading("Why REST and Kafka are both used",2), table(["Pattern","Use in this platform","Reason"],[
    ["REST/JSON","Login, service registration, dashboard queries, manual scale, alert acknowledgement","Simple, immediate response and easy browser integration."],
    ["Kafka events","metrics.raw, alerts.triggered, prediction.ready, scaling.executed","Handles bursty producers, supports replay and lets several consumers process one signal independently."],
    ["WebSocket","dashboard.tick","Pushes lightweight live-state messages to an already open dashboard."],
], [3.0*cm,5.1*cm,7.4*cm]), heading("Polyglot persistence",2), p("No single database is best at every workload. PostgreSQL stores integrity-sensitive control-plane records. TimescaleDB stores high-write time-series metrics. OpenSearch indexes searchable log text. Redis provides low-latency cache, pub/sub and rate-limit state. Object storage keeps durable log archives, generated reports and ML artifacts."), p("In the current local website, SQLite provides a deliberate fallback so it runs without external credentials. The API response labels the moving dashboard values as simulated-local. This is not presented as a substitute for production telemetry."), PageBreak()]

story += [heading("3. The twelve modules"), table(["Module","What it does","Main API or event"],[
 ["Authentication","Issues access/refresh tokens and checks RBAC permissions.","/auth/login, /auth/refresh, /auth/me"],
 ["API Gateway","Browser entry point; validates access, routes APIs and provides the local BFF.","/api/*, /ws/live"],
 ["Monitoring","Service registry, heartbeats, uptime and alert lifecycle.","/services, /alerts"],
 ["Metrics","Ingests and queries CPU, memory, latency and request telemetry.","metrics.raw, /metrics/query"],
 ["Traffic Prediction","Forecasts demand and recommends pod count.","/predictions/traffic/{id}"],
 ["Predictive Maintenance","Scores failure risk and suggests root cause.","/predictions/maintenance/{id}"],
 ["GenAI Log Analysis","Correlates logs, alerts and metrics into an RCA summary.","/genai/analyze"],
 ["Notifications","Routes alert messages to Slack, email or webhook policies.","/notifications/send"],
 ["Dashboard BFF","Aggregates data for Executive, API, Traffic and other dashboards.","/dashboards/{name}"],
 ["Kubernetes Management","Reads nodes/pods/deployments and executes controlled scaling.","/k8s/nodes, /scale"],
 ["Cloud Storage","Stores report exports and archived log/model objects.","/storage/objects"],
 ["Cloud SQL / Audit","Configuration and immutable action history.","/configurations, /audit"],
], [3.1*cm,8.4*cm,4.0*cm]), Spacer(1,8), p("Each service owns its own domain schema in the target architecture. A service should not reach into another service's database. It uses a REST contract or event instead. This prevents hidden coupling and lets teams deploy, scale and recover services independently.", "Callout"), PageBreak()]

story += [heading("4. How the website works"), p("The website is an operator console. It is served by the FastAPI gateway at localhost:8080 in local development. After login, the browser stores only a short-lived local demonstration access token in session storage and calls protected API endpoints with a Bearer token."), heading("Dashboard workflow",2), table(["Screen or control","What happens in code","Result"],[
 ["Login","POST /api/auth/login validates the demo identity and returns a token plus Anisha Verma's role and permissions.","The app unlocks the dashboard."],
 ["Command Center","GET /api/overview, /api/alerts and /api/services are requested concurrently.","Health, traffic, alerts and service status are rendered."],
 ["Search","Ctrl/Cmd+K or the search icon loads services and alerts, then filters them in the browser.","Selecting a result navigates to its relevant page."],
 ["Notifications","The bell reads alert and notification-history APIs. Sending to Slack creates a durable local notification record.","Operator sees delivery history and active incidents."],
 ["Priority alerts","Acknowledge calls the alert API.","The alert is acknowledged, audited, notified and a follow-up investigation alert is created."],
 ["Register service","The Services page submits a validated service-registration form.","New workload is persisted, searchable and visible in the catalog."],
 ["Kubernetes scale","The operator selects a workload and target replicas.","The action is recorded in scaling history and audit records."],
 ["Log analysis","A log sample is posted to GenAI analysis.","The local rule fallback returns a root-cause summary and suggested fix."],
], [3.1*cm,7.6*cm,4.8*cm]), heading("Time-aware and live UI behavior",2), p("The greeting uses the browser's local hour: morning before 12:00, afternoon from 12:00 to 16:59, and evening after 17:00. A lightweight background timer updates that greeting and the notification count every 15 seconds without re-rendering the full page. The earlier full-page refresh was removed because it caused visible blinking."), PageBreak()]

story += [heading("5. Data, alerts and simulated telemetry"), p("The local gateway creates a SQLite database under data/platform.db. It persists alerts, scaling history, audit events, notifications, metric points, configuration records and registered services. This is useful for an offline demonstration because actions survive browser refreshes and the platform can be tested without Docker."), heading("What changes dynamically now",2), table(["Signal","How it changes"],[
 ["Open alert count","Changes after acknowledge actions and when the backend generates a follow-up investigation alert."],
 ["Notification history","Changes when a notification is sent or an alert acknowledgement generates a Slack delivery."],
 ["Service catalog","Changes immediately after a registered service is submitted."],
 ["Scaling history and audit","Changes after manual scaling and other mutation endpoints."],
 ["Overview traffic and health","Uses a time-varying simulated-local signal, clearly labeled for development mode."],
], [4.4*cm,11.1*cm]), heading("How to make the data truly live",2), p("Run Docker Desktop and the compose stack, then connect real producers. A Kubernetes collector can read pod/node/deployment state through a ServiceAccount. Application instrumentation or OpenTelemetry collectors can publish request count, latency, CPU and error rate into Kafka. The Metrics Service writes points into TimescaleDB; Fluent Bit can send structured logs into OpenSearch; Dashboard Service reads cached aggregations. At that point the simulated-local fallback is replaced by recorded telemetry."), heading("Alert lifecycle",2), p("An alert enters open status after a health or threshold condition. An operator acknowledges it. The platform writes an audit record, sends a notification and opens a follow-up task so remediation is not silently forgotten. In production, resolution would require a recovered metric/health signal or an authorized explicit resolve action."), PageBreak()]

story += [heading("6. GenAI and predictive auto scaling"), heading("Traffic prediction",2), p("Inputs include historical request counts, time-of-day, day-of-week, latency and CPU. A light gradient-boosted or statistical model is appropriate initially because traffic has strong seasonal structure and cloud operations need explainability. The output contains expected requests, a confidence interval and a recommended replica count based on requests-per-pod capacity."), p("Formula concept: target replicas = ceiling(expected request rate / safe requests-per-pod capacity). The recommendation is a decision aid. Production auto-scaling must include minimum/maximum replica limits, cooldowns, confidence thresholds, SLO protection and an audit trail."), heading("Predictive maintenance",2), p("Inputs include CPU, memory, disk/network activity and restart trend. A classifier such as XGBoost estimates failure probability. Feature importance identifies likely causes, for example memory saturation or increasing restarts. The model should never hide uncertainty; its confidence and input freshness belong in the UI."), heading("GenAI log analysis",2), p("A strong GenAI workflow is retrieval-augmented rather than asking an LLM to guess from one log line. The service retrieves related logs from OpenSearch, correlated metrics from Metrics Service, active alerts and recent deployment history. It passes scrubbed context to a managed model such as Claude and requests structured JSON: root-cause summary, human explanation, suggested fix and confidence."), p("The local implementation deliberately supplies a rule-based fallback. If a managed model or OpenSearch is unavailable, the operator still receives a deterministic, safe explanation rather than an empty panel. In production, secrets/PII must be redacted before any external model call and the API key remains in a Kubernetes Secret, never in browser code.", "Callout"), PageBreak()]

story += [heading("7. Docker, Kubernetes and cloud deployment"), heading("Docker locally",2), p("Docker packages each service with its runtime and dependencies in an image. Docker Compose creates a private network, starts PostgreSQL, Redis, Kafka, OpenSearch and MinIO, then starts the gateway and each service container. The gateway is mapped to port 8080 for the browser; individual service ports are mapped for tests and Swagger inspection."), p("Command: docker compose -f infra/docker-compose.yml -f infra/services.compose.yml up --build. Docker Desktop must be running. Without Docker, python run_local.py starts the gateway with its SQLite fallback, which is why the website remains usable on a laptop."), heading("Kubernetes in production",2), table(["Kubernetes resource","Purpose in this project"],[
 ["Namespace","Separates auth, monitoring, AI, data, frontend and platform blast radii."],
 ["Deployment and ReplicaSet","Runs stateless service replicas and supports rolling updates."],
 ["Service and Ingress","Provides internal discovery; Ingress exposes only the gateway at the edge."],
 ["ConfigMap and Secret","Separates non-sensitive runtime config from credentials, keys and provider tokens."],
 ["Liveness and readiness probes","Kubernetes restarts unhealthy processes and avoids routing traffic before dependencies are ready."],
 ["HPA/KEDA","Scales replicas from CPU, memory, request demand or Kafka consumer lag."],
], [4.3*cm,11.2*cm]), heading("Cloud providers",2), p("The same design maps to AWS or Google Cloud. Example AWS mapping: EKS for Kubernetes, RDS PostgreSQL, MSK for Kafka, ElastiCache Redis, OpenSearch Service, S3 object storage, IAM Roles for Service Accounts and CloudWatch as an additional infrastructure signal. On Google Cloud, map these to GKE, Cloud SQL, Managed Service for Apache Kafka or Confluent, Memorystore, OpenSearch-compatible service, Cloud Storage and Workload Identity."), PageBreak()]

story += [heading("8. Security, reliability and delivery"), table(["Control","Implementation goal"],[
 ["Authentication","Short-lived JWT access tokens plus rotating refresh tokens; optional MFA for high-risk access."],
 ["Authorization","RBAC at gateway and service layer. An operator can acknowledge alerts and scale only when granted the matching permission."],
 ["Audit","Mutating actions retain actor, action, resource, before/after state and timestamp."],
 ["Secrets","Kubernetes Secrets or cloud secret manager/KMS; never put provider keys in browser JavaScript or image layers."],
 ["Network","TLS externally and mTLS/service mesh internally when deployed across a cluster."],
 ["Failure handling","Timeouts, retries with jitter, circuit breakers, idempotent event IDs and graceful partial dashboards."],
 ["CI/CD","Lint, unit/contract tests, image build, scan/sign, staging deploy, integration checks, approval gate and controlled production rollout."],
], [4.2*cm,11.3*cm]), heading("Current status and honest boundaries",2), p("The website, FastAPI gateway, persistent local workflows and service packages are implemented for local use. The repository includes compose, service, event-schema, Kubernetes and CI foundations. A production deployment still requires Docker Desktop or a cloud account, real Kafka/TimescaleDB/OpenSearch/Redis/S3 endpoints, service-specific data access implementations, container registry configuration, and validated Terraform modules. These are environmental deployment tasks, not features that a browser page can provide by itself."), heading("Recommended demonstration sequence",2), p("1. Start python run_local.py. 2. Log in as Anisha Verma. 3. Register a service. 4. Search for it. 5. Acknowledge an open alert and show the follow-up alert plus notification history. 6. Scale checkout-api and inspect audit history. 7. Use Log Intelligence to analyze a timeout. 8. Explain that Docker/Compose replaces local fallback dependencies with real local infrastructure, and Kubernetes is the production scheduler."), Spacer(1,12), p("End of report", "Small")]

doc = SimpleDocTemplate(str(OUT), pagesize=A4, rightMargin=1.7*cm, leftMargin=1.7*cm, topMargin=1.6*cm, bottomMargin=1.9*cm, title="Cloud-Native Intelligent Microservices Management Platform")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print("Report written successfully.")
