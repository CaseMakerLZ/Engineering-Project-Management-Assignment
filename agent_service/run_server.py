import uvicorn
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_service.api import app


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
