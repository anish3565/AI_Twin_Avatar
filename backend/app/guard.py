import os
import re

MAX_MESSAGE_CHARS = 1000
MAX_REPLY_CHARS = 700

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


def _allowed_urls() -> tuple[str, ...]:
    value = os.environ.get("CONTACT_LINKEDIN", "").strip().lower()
    return (value,) if value else ()


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
        if not any(url.lower().startswith(a) for a in allowed_urls):
            return False
    allowed_emails = _allowed_emails()
    for email in _EMAIL.findall(reply):
        if email.lower() not in allowed_emails:
            return False
    return True
