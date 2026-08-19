-- Runs automatically on first container startup (mounted into
-- /docker-entrypoint-initdb.d/, which Postgres's official image executes
-- once, only when the data directory is empty).
--
-- WHY one Postgres DATABASE per service rather than one shared database
-- with per-service schemas or table prefixes: this is the same bounded-
-- context principle stated in the master architecture doc (§3) — even
-- though these all happen to run on the same physical Postgres instance
-- in local dev, each service must be unable to accidentally query another
-- service's tables. Separate databases enforce that at the connection
-- level, not just by convention.

CREATE DATABASE auth_service OWNER platform;
CREATE DATABASE monitoring_service OWNER platform;
CREATE DATABASE metrics_service OWNER platform;
CREATE DATABASE k8s_management_service OWNER platform;
CREATE DATABASE traffic_prediction_service OWNER platform;
CREATE DATABASE predictive_maintenance_service OWNER platform;
CREATE DATABASE genai_log_analysis_service OWNER platform;
CREATE DATABASE notification_service OWNER platform;
-- Module 12+: CREATE DATABASE cloud_storage_service OWNER platform;
