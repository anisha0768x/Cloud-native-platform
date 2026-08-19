from app.api.v1.genai_routes import router as genai_router
from app.api.v1.log_routes import router as log_router

__all__ = ["log_router", "genai_router"]
