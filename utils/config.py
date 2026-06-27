from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv(Path(__file__).parent.parent / ".env")

DATABASE_URL      = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5433/sales_intel")
REDIS_URL         = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
SERPAPI_KEY       = os.getenv("SERPAPI_KEY", "")
CLEARBIT_API_KEY  = os.getenv("CLEARBIT_API_KEY", "")
HUNTER_API_KEY    = os.getenv("HUNTER_API_KEY", "")
APIFY_API_KEY     = os.getenv("APIFY_API_KEY", "")
INSTANTLY_API_KEY        = os.getenv("INSTANTLY_API_KEY", "")
OUTREACH_SCORE_THRESHOLD = int(os.getenv("OUTREACH_SCORE_THRESHOLD", "60"))

# SMTP — free email sending (no Instantly needed for testing)
# Gmail: enable 2FA → Security → App Passwords → generate one for "Mail"
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")  # Gmail app password, not your account password
