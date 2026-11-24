import os
import re
from functools import lru_cache
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"

MAX_MESSAGE_CHARS = 1000
MAX_REPLY_CHARS = 700
VOICE_REPLY_CHARS = 400

BLOCKED_REPLY = "I can only talk about my experience, projects and education. Ask me about those."
SAFE_FALLBACK_REPLY = "Sorry, I can't share that. Ask me about my experience, projects or education."

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩﻿]")
_TAG_CHARS = re.compile(r"[<>]")
_INJECTION = re.compile(
    r"ignore\s+(all|any|the|your|previous|prior|above|earlier)"
    r"|disregard|forget\s+(your|the|all)"
    r"|system\s*prompt|developer\s*mode|jailbreak|\bDAN\b"
    r"|reveal|show\s+me\s+(your|the)\s+(prompt|rules|instructions)"
    r"|your\s+(instructions|rules|prompt)"
    r"|you\s+are\s+now|pretend\s+(to\s+be|you)|act\s+as|roleplay"
    r"|\bapi[\s_-]*key|\btoken\b|\bpassword|\bsecret|environment\s+variable|\.env\b"
    r"|```|<\s*/?\s*(question|knowledge|system|user|assistant)",
    re.IGNORECASE,
)
_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_LEAK_MARKERS = ("KNOWLEDGE:", "You are an AI version of", "Answer only from the KNOWLEDGE", "UNKNOWN_TOKEN")


def clean_question(text: str) -> str:
    text = _CONTROL.sub("", text)
    text = _TAG_CHARS.sub("", text)
    return " ".join(text.split())


def looks_like_injection(question: str) -> bool:
    return _INJECTION.search(question) is not None


# The model sometimes adds the UNKNOWN marker after a correct answer, e.g. "...7.60.UNKNOWN".
_TRAILING_UNKNOWN = re.compile(r"(?<=\S)\s*UNKNOWN[\s.!?]*$")


def strip_trailing_unknown(text: str) -> str:
    return _TRAILING_UNKNOWN.sub("", text).rstrip()


def _normalise_url(url: str) -> str:
    return url.strip().lower().rstrip(".,;:!?)\"'").rstrip("/")


@lru_cache(maxsize=1)
def _knowledge_urls() -> frozenset[str]:
    urls = set()
    for path in KNOWLEDGE_DIR.glob("*.md"):
        for url in _URL.findall(path.read_text(encoding="utf-8")):
            urls.add(_normalise_url(url))
    return frozenset(urls)


def _allowed_urls() -> frozenset[str]:
    urls = set(_knowledge_urls())
    linkedin = os.environ.get("CONTACT_LINKEDIN", "").strip()
    if linkedin:
        urls.add(_normalise_url(linkedin))
    return frozenset(urls)


def _allowed_emails() -> set[str]:
    value = os.environ.get("CONTACT_EMAIL", "").strip().lower()
    return {value} if value else set()


def reply_is_safe(reply: str) -> bool:
    if len(reply) > MAX_REPLY_CHARS:
        return False
    lowered = reply.lower()
    if any(marker.lower() in lowered for marker in _LEAK_MARKERS):
        return False
    allowed_urls = _allowed_urls()
    for url in _URL.findall(reply):
        if _normalise_url(url) not in allowed_urls:
            return False
    allowed_emails = _allowed_emails()
    for email in _EMAIL.findall(reply):
        if email.lower() not in allowed_emails:
            return False
    return True
