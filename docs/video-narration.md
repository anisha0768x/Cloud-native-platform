# Helio Operations — 10-minute video narration and demo truth sheet

This is the narration for [`video-presentation.html`](video-presentation.html). Open that file in a browser and let it auto-run. It uses animated UI mockups, architecture motion, a moving cursor, data packets, scene transitions, and optional browser speech synthesis. For a submission-quality MP4, screen-record the page with system audio enabled; the page is intentionally built as a moving product-demo canvas rather than a static slide deck.

## Timing and narration

| Time | Segment | What is shown | Narration focus |
|---|---|---|---|
| 0:00–0:45 | Introduction | Animated dashboard with health, alerts, requests and nodes | What the platform is and who uses it |
| 0:45–2:00 | Real-world problem | Normal traffic → spike → latency → alert → response | Why cloud operations need a unified control plane |
| 2:00–3:30 | Website walkthrough | Browser shell, navigation, services table, cursor/click animation | Login, dashboard, service catalog, alerts, Kubernetes and logs |
| 3:30–5:00 | Day-to-day scenario | Moving request/metric/decision/action packets | Checkout sale, forecast, scaling and audit trail |
| 5:00–6:30 | AI + monitoring | Logs + metrics → analyst → diagnosis → human review | Observability and the implemented rule-based AI fallback |
| 6:30–8:00 | Architecture | Browser → gateway → services/data → Kubernetes/cloud | Backend contracts and deployment boundaries |
| 8:00–9:15 | Cloud concepts | Animated concept cards | Containers, Kubernetes, elasticity, observability, storage and recovery |
| 9:15–10:00 | Complete flow | End-to-end moving loop | Monitor → Predict → Optimize → Respond → Recover |

The full voice-over is embedded in the HTML `data-voice` attributes so browser narration follows each scene. If you record your own voice, read the same text in this file or use it as a cue sheet.

## Brutally honest implementation notes

Implemented and runnable locally:

- FastAPI API gateway with bearer-token login and a browser frontend.
- SQLite persistence for registered services, alert acknowledgement/follow-up events, storage objects, configuration and audit entries.
- Service catalog and service registration.
- Priority alerts, acknowledgement, follow-up alert creation, notification history and Slack-send contract.
- Kubernetes posture page with deployments and a controlled scale action recorded in the audit trail.
- Log stream and an incident-analysis endpoint that returns a confidence-labelled diagnosis and recommendation.
- Traffic forecast and predictive-maintenance views.
- Cloud cost/SLA, storage, IAM/security, network and disaster-recovery views.
- Dockerfiles, Docker Compose definitions, Kubernetes manifest and Terraform expansion point.

Simulated or reference-only in the current local build:

- Live telemetry, forecasts and cost figures are synthetic-local demonstration data; they are not readings from a real cloud account.
- The “AI Incident Analyst” currently uses a deterministic rule-based fallback. No hosted LLM is called by the demo.
- Kubernetes data and scale behaviour are represented through the API/database contract; no live cluster is contacted by the local page.
- Cloud Storage, IAM, network and disaster-recovery screens are local policy/reference models; they do not mutate AWS/GCP/Azure resources.
- Docker Compose and Terraform describe the path to a production deployment; they do not make the localhost demo a deployed cloud service by themselves.

The accurate claim for an evaluator is: **“This is a functional local prototype of a cloud-native AIOps control plane, with production-oriented service boundaries and deployment artefacts. The local adapter keeps the demo self-contained; cloud provider, live Kubernetes, streaming infrastructure and GenAI integrations are documented next steps.”**

## Suggested recording setup

1. Start the platform with `Start-Cloud-Native-Platform.cmd` and verify `http://127.0.0.1:8080/` opens.
2. Open `docs/video-presentation.html` in the same browser.
3. Keep browser/system audio enabled if using the built-in narration, or mute `Voice on` and record your own voice.
4. Record at 1920×1080, 30 fps, with the browser page full-screen. Use the pause button if you need to retake a sentence.
5. Keep the real website open in a second tab and cut to it during the walkthrough if you want to show live clicks; the claims in this script still remain accurate.
