"""Project paths and BitBrowser runtime configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
RESULTS_DIR = BASE_DIR / "Results"

# Shell variables override the project-local .env file.
load_dotenv(BASE_DIR / ".env", override=False)

BIT_BROWSER_API_URL = os.getenv("BIT_BROWSER_API_URL", "http://127.0.0.1:54346")
BIT_BROWSER_ID = os.getenv("BIT_BROWSER_ID", "")
BIT_BROWSER_NAME = os.getenv("BIT_BROWSER_NAME", "outlook-register")
BIT_BROWSER_CLOSE_WAIT = max(5.0, float(os.getenv("BIT_BROWSER_CLOSE_WAIT", "5")))
BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "30000"))
HEADLESS = os.getenv("HEADLESS", "false").lower() in ("1", "true", "yes")
