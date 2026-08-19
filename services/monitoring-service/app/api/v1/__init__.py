from app.api.v1.alert_routes import router as alert_router
from app.api.v1.service_routes import router as service_router

__all__ = ["service_router", "alert_router"]
