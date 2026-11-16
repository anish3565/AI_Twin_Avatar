import json
import os
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import aclosing
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.background import BackgroundTask

from . import db, llm
from .guard import (
    BLOCKED_REPLY,
    MAX_MESSAGE_CHARS,
    MAX_REPLY_CHARS,
    SAFE_FALLBACK_REPLY,
    VOICE_REPLY_CHARS,
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


class VisitorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    name: str = Field(min_length=1, max_length=120)
    company: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=120)
    hiring_for: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    linkedin_url: str | None = Field(default=None, max_length=300, pattern=r"^https://(www\.)?linkedin\.com/\S*$")
    consent: Literal[True]

    @field_validator("name", "company", "role", "hiring_for")
    @classmethod
    def clean_required(cls, value: str) -> str:
        cleaned = clean_question(value)
        if not cleaned:
            raise ValueError("field is empty")
        return cleaned

    @field_validator("email", "linkedin_url")
    @classmethod
    def strip(cls, value: str | None) -> str | None:
        return value.strip() if value else None


class VisitorOut(BaseModel):
    saved: bool


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    voice: bool = False

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


@app.post("/visitor", response_model=VisitorOut)
def save_visitor(body: VisitorIn, request: Request) -> VisitorOut:
    if not session_limiter.allow(client_key(request)):
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    visitor = body.model_dump(include={"name", "email", "company", "role", "hiring_for", "linkedin_url"})
    try:
        db.link_visitor(body.session_id, visitor)
    except LookupError:
        raise HTTPException(status_code=404, detail="Session not found.")
    except Exception:
        raise HTTPException(status_code=503, detail="Could not save your details. Please try again.")
    return VisitorOut(saved=True)


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

    if body.voice:
        background.add_task(db.safe, db.mark_voice_used, body.session_id)

    if looks_like_injection(question):
        outcome, reply = "refused", BLOCKED_REPLY
    else:
        try:
            result = await llm.complete(build_messages(question, load_knowledge(), voice=body.voice))
            provider, model = result.provider, result.model
            prompt_tokens, completion_tokens = result.prompt_tokens, result.completion_tokens
            fallback_used = result.fallback_used
            text = result.text.strip()
            if text.upper().startswith(UNKNOWN_TOKEN):
                outcome = "unknown"
                reply = f"I don't have that information yet. {contact_line()}".strip()
            elif not reply_is_safe(text) or (body.voice and len(text) > VOICE_REPLY_CHARS):
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


SENTENCE_END = re.compile(r"[.!?]\s")


def _line(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"


def _complete_sentences(buffer: str) -> tuple[list[str], str]:
    sentences = []
    start = 0
    for match in SENTENCE_END.finditer(buffer):
        sentence = buffer[start:match.end()].strip()
        if sentence:
            sentences.append(sentence)
        start = match.end()
    return sentences, buffer[start:]


def _accept(sentences: list[str], spoken: list[str], limit: int) -> tuple[list[str], bool]:
    accepted = []
    for sentence in sentences:
        if not reply_is_safe(sentence) or len(" ".join([*spoken, sentence])) > limit:
            return accepted, False
        spoken.append(sentence)
        accepted.append(sentence)
    return accepted, True


def _is_unknown(text: str) -> bool:
    return text.strip().upper().startswith(UNKNOWN_TOKEN)


async def _stream_events(question: str, state: dict) -> AsyncIterator[str]:
    spoken: list[str] = []
    pending = ""
    full = ""
    decided = False
    limit = VOICE_REPLY_CHARS if state["voice"] else MAX_REPLY_CHARS
    try:
        if looks_like_injection(question):
            state.update(outcome="refused", reply=BLOCKED_REPLY)
        else:
            messages = build_messages(question, load_knowledge(), voice=state["voice"])
            async with aclosing(llm.stream(messages, state)) as deltas:
                async for delta in deltas:
                    full += delta
                    pending += delta
                    if not decided:
                        if len(full.strip()) < len(UNKNOWN_TOKEN):
                            continue
                        decided = True
                        if _is_unknown(full):
                            state.update(outcome="unknown", reply=f"I don't have that information yet. {contact_line()}".strip())
                            break
                    if len(full) > limit:
                        state.update(outcome="refused", reply=SAFE_FALLBACK_REPLY)
                        break
                    complete, pending = _complete_sentences(pending)
                    accepted, ok = _accept(complete, spoken, limit)
                    for sentence in accepted:
                        yield _line({"type": "sentence", "text": sentence})
                    if not ok:
                        state.update(outcome="refused", reply=SAFE_FALLBACK_REPLY)
                        break

            if state["outcome"] is None and not decided and _is_unknown(full):
                state.update(outcome="unknown", reply=f"I don't have that information yet. {contact_line()}".strip())

            if state["outcome"] is None:
                accepted, ok = _accept([pending.strip()] if pending.strip() else [], spoken, limit)
                for sentence in accepted:
                    yield _line({"type": "sentence", "text": sentence})
                if not ok:
                    state.update(outcome="refused", reply=SAFE_FALLBACK_REPLY)
                elif not spoken:
                    state.update(outcome="error", error_type="EmptyReply", reply=f"Sorry, I couldn't answer right now. {contact_line()}".strip())
                else:
                    state.update(outcome="answered", reply=" ".join(spoken))
    except Exception as exc:
        state.update(
            outcome="error",
            error_type=type(exc).__name__,
            reply=f"Sorry, I couldn't answer right now. {contact_line()}".strip(),
        )

    state["total_ms"] = int((time.perf_counter() - state["started"]) * 1000)
    yield _line({
        "type": "end",
        "message_id": state["message_id"],
        "outcome": state["outcome"],
        "reply": state["reply"],
    })


def _save_streamed(state: dict) -> None:
    db.safe(
        db.save_message,
        message_id=state["message_id"],
        session_id=state["session_id"],
        question=state["question"],
        reply=state.get("reply"),
        outcome=state.get("outcome") or "error",
        provider=state.get("provider"),
        model=state.get("model"),
        prompt_tokens=state.get("prompt_tokens"),
        completion_tokens=state.get("completion_tokens"),
        total_ms=state.get("total_ms"),
        fallback_used=state.get("fallback_used", False),
        error_type=state.get("error_type"),
    )
    if state["voice"]:
        db.safe(db.mark_voice_used, state["session_id"])


@app.post("/chat/stream")
async def chat_stream(body: ChatIn, request: Request) -> StreamingResponse:
    if not chat_limiter.allow(client_key(request)):
        raise HTTPException(status_code=429, detail="Too many messages. Please try again in a few minutes.")
    state = {
        "message_id": str(uuid.uuid4()),
        "session_id": body.session_id,
        "question": body.message,
        "voice": body.voice,
        "started": time.perf_counter(),
        "outcome": None,
        "reply": None,
    }
    return StreamingResponse(
        _stream_events(body.message, state),
        media_type="application/x-ndjson",
        background=BackgroundTask(_save_streamed, state),
    )
