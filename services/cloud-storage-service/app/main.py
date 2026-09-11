import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from services._runtime.factory import create_app
app = create_app("cloud-storage-service")
