"""
platform_common
================
Shared library used by every microservice in the Cloud-Native Intelligent
Microservices Management Platform.

Provides: settings loading, structured JSON logging, SQLAlchemy async DB
base classes, JWT verification, standard exception types + FastAPI
exception handlers, and Kafka producer/consumer helpers.

Every service depends on this package instead of re-implementing these
concerns, so that logs, errors, and config behave identically across the
whole platform (this consistency is what makes the Logs/Security dashboards
and centralized alerting actually work).
"""

__version__ = "0.1.0"
