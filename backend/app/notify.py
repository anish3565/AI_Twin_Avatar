import logging
import os

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"
FIELDS = (
    ("Name", "name"),
    ("Company", "company"),
    ("Role", "role"),
    ("Hiring for", "hiring_for"),
    ("Email", "email"),
    ("LinkedIn", "linkedin_url"),
)


def format_lead(visitor: dict) -> str:
    lines = ["New visitor on your AI twin:"]
    for label, key in FIELDS:
        value = visitor.get(key)
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


def send_lead_alert(visitor: dict) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        r = httpx.post(
            TELEGRAM_URL.format(token=token),
            json={"chat_id": chat_id, "text": format_lead(visitor)},
            timeout=10,
        )
        r.raise_for_status()
    except Exception:
        logger.exception("Telegram lead alert failed")
