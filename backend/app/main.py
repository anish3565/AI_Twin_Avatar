import os
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import db, llm
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
session_limiter = RateLimiter(limit=10, window_seconds=300)
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


class SessionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invite_code: str | None = Field(default=None, max_length=64)


class SessionOut(BaseModel):
    session_id: str


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
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


@app.post("/session", response_model=SessionOut)
def start_session(body: SessionIn, request: Request, background: BackgroundTasks) -> SessionOut:
    if not session_limiter.allow(client_key(request)):
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    session_id = str(uuid.uuid4())
    background.add_task(db.safe, db.create_session, session_id, body.invite_code)
    return SessionOut(session_id=session_id)


@app.post("/chat", response_model=ChatOut)
async def chat(body: ChatIn, request: Request, background: BackgroundTasks) -> ChatOut:
    if not chat_limiter.allow(client_key(request)):
        raise HTTPException(status_code=429, detail="Too many messages. Please try again in a few minutes.")

    started = time.perf_counter()
    message_id = str(uuid.uuid4())
    question = body.message
    provider = model = None
    prompt_tokens = completion_tokens = None
    fallback_used = False
    error_type = None

    if looks_like_injection(question):
        outcome, reply = "refused", BLOCKED_REPLY
    else:
        try:
            result = await llm.complete(build_messages(question, load_knowledge()))
            provider, model = result.provider, result.model
            prompt_tokens, completion_tokens = result.prompt_tokens, result.completion_tokens
            fallback_used = result.fallback_used
            text = result.text.strip()
            if text.upper().startswith(UNKNOWN_TOKEN):
                outcome = "unknown"
                reply = f"I don't have that information yet. {contact_line()}".strip()
            elif not reply_is_safe(text):
                outcome, reply = "refused", SAFE_FALLBACK_REPLY
            else:
                outcome, reply = "answered", text
        except Exception as exc:
            outcome = "error"
            error_type = type(exc).__name__
            reply = f"Sorry, I couldn't answer right now. {contact_line()}".strip()

    total_ms = int((time.perf_counter() - started) * 1000)
    background.add_task(
        db.safe,
        db.save_message,
        message_id=message_id,
        session_id=body.session_id,
        question=question,
        reply=reply,
        outcome=outcome,
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_ms=total_ms,
        fallback_used=fallback_used,
        error_type=error_type,
    )
    return ChatOut(message_id=message_id, reply=reply, outcome=outcome)
