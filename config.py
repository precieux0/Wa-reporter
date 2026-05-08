import os
import json
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SMTP_ACCOUNTS = json.loads(os.getenv("SMTP_ACCOUNTS", "[]"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "0")) if os.getenv("ADMIN_ID") else None

MIN_REPORTS = int(os.getenv("MIN_REPORTS", "10"))
MAX_REPORTS = int(os.getenv("MAX_REPORTS", "50"))
EMAIL_DELAY = float(os.getenv("EMAIL_DELAY", "2.0"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
WHATSAPP_RECIPIENTS = json.loads(os.getenv("WHATSAPP_RECIPIENTS", '["support@support.whatsapp.com"]'))

REPORT_CATEGORIES = [
    "Spam", "Harassment", "Fake Account", "Impersonation",
    "Illegal Activities", "Privacy Violation", "Threats",
    "Scam", "Abusive Content", "Other"
]
