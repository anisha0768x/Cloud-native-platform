"""Reliable local launcher for the FastAPI gateway on Windows."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / ".deps"))
sys.path.insert(0, str(ROOT / "services" / "api-gateway"))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8080)
