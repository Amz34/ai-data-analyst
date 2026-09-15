import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL = os.getenv("DS_DB_URL", "postgresql+psycopg2://dsapp:dsapp_pass@127.0.0.1:5433/dsapp")
JWT_SECRET = os.getenv("DS_JWT_SECRET", "dev-secret-change-me")
JWT_ALGO = "HS256"
JWT_EXPIRES_MIN = int(os.getenv("DS_JWT_EXPIRES_MIN", "1440"))

DATA_DIR = Path(os.getenv("DS_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# LLM (DeepSeek-compatible API)
LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))

MAX_UPLOAD_MB = int(os.getenv("DS_MAX_UPLOAD_MB", "25"))

# ---- commercial layer (plans + usage metering) ----
DEFAULT_PLAN = os.getenv("DS_DEFAULT_PLAN", "trial")
ADMIN_TOKEN = os.getenv("DS_ADMIN_TOKEN", "")
PLAN_LIMITS = {
    "trial": {"dataset": 2, "dashboard": 2, "ask": 25, "users": 2, "max_upload_mb": 5},
    "starter": {"dataset": 10, "dashboard": 25, "ask": 500, "users": 5, "max_upload_mb": 25},
    "growth": {"dataset": 50, "dashboard": 200, "ask": 3000, "users": 20, "max_upload_mb": 100},
    "pro": {"dataset": 250, "dashboard": 1000, "ask": 20000, "users": 100, "max_upload_mb": 250},
}

SANDBOX_TIMEOUT_S = int(os.getenv("DS_SANDBOX_TIMEOUT_S", "5"))

# ---- crashproof additions (provider failover + circuit breaker + tracing) ----
LLM_FALLBACK_KEY = os.getenv("GOOGLE_API_KEY", "")
LLM_FALLBACK_BASE_URL = os.getenv("LLM_FALLBACK_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
LLM_FALLBACK_MODEL = os.getenv("LLM_FALLBACK_MODEL", "gemini-3.6-flash")
LLM_CIRCUIT_THRESHOLD = int(os.getenv("LLM_CIRCUIT_THRESHOLD", "2"))
LLM_CIRCUIT_COOLDOWN_S = int(os.getenv("LLM_CIRCUIT_COOLDOWN_S", "120"))
LLM_PRIMARY_RETRIES = int(os.getenv("LLM_PRIMARY_RETRIES", "2"))
LOG_DIR = Path(os.getenv("LOG_DIR", str(BASE_DIR / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)
CREDS_FILE = os.getenv("CREDS_FILE", "/home/ubuntu/.hermes/.env")
