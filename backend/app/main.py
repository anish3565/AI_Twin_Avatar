import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import llm
from .guard import (
    BLOCKED_REPLY,
    MAX_MESSAGE_CHARS,
    SAFE_FALLBACK_REPLY,
    clean_question,
    looks_like_injection,
    reply_is_safe,
)
from .prompt import UNKNOWN_TOKEN, build_messages, load_knowledge
from .ratelimit import RateLimiter

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

MAX_BODY_BYTES = 4096
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}
chat_limiter = RateLimiter(limit=20, window_seconds=300)

app = FastAPI(title="ThatMe API", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",") if origin],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def harden(request: Request, call_next):
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > MAX_BODY_BYTES:
        return JSONResponse({"detail": "Request too large."}, status_code=413)
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    return response


def contact_line() -> str:
    options = [v for v in (os.environ.get("CONTACT_EMAIL"), os.environ.get("CONTACT_LINKEDIN")) if v]
    if not options:
        return ""
    return "You can reach Anish at " + " or ".join(options) + "."


def client_key(request: Request) -> str:
    real_ip = request.headers.get("x-real-ip", "").strip()
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)

    @field_validator("message")
    @classmethod
    def sanitize(cls, value: str) -> str:
        cleaned = clean_question(value)
        if not cleaned:
            raise ValueError("message is empty")
        return cleaned


class ChatOut(BaseModel):
    message_id: str
    reply: str
    outcome: str


@app.post("/chat", response_model=ChatOut)
async def chat(body: ChatIn, request: Request) -> ChatOut:
    if not chat_limiter.allow(client_key(request)):
        raise HTTPException(status_code=429, detail="Too many messages. Please try again in a few minutes.")

    message_id = str(uuid.uuid4())
    question = body.message

    if looks_like_injection(question):
        return ChatOut(message_id=message_id, reply=BLOCKED_REPLY, outcome="blocked")

    try:
        result = await llm.complete(build_messages(question, load_knowledge()))
    except Exception:
        return ChatOut(
            message_id=message_id,
            reply=f"Sorry, I couldn't answer right now. {contact_line()}".strip(),
            outcome="error",
        )

    text = result.text.strip()
    if text.upper().startswith(UNKNOWN_TOKEN):
        return ChatOut(
            message_id=message_id,
            reply=f"I don't have that information yet. {contact_line()}".strip(),
            outcome="unknown",
        )
    if not reply_is_safe(text):
        return ChatOut(message_id=message_id, reply=SAFE_FALLBACK_REPLY, outcome="blocked")
    return ChatOut(message_id=message_id, reply=text, outcome="answered")
