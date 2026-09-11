# Event contracts

Kafka topic contracts are versioned here. Producers must include stable event IDs; consumers perform idempotent processing. Initial topics: `metrics.raw`, `alerts.triggered`, `prediction.ready`, `maintenance.risk_detected`, `genai.summary_ready`, `scaling.executed`, and `audit.entry_created`.
