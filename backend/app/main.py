import os
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import db, llm
from app.prompt import UNKNOWN_TOKEN, build_messages, load_knowledge

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

MAX_QUESTION_CHARS = 1000

app = FastAPI(title="ThatMe API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",") if origin],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


def contact_line() -> str:
    options = [v for v in (os.environ.get("CONTACT_EMAIL"), os.environ.get("CONTACT_LINKEDIN")) if v]
    if not options:
        return ""
    return "You can reach Anish at " + " or ".join(options) + "."


class SessionIn(BaseModel):
    invite_code: str | None = None


class SessionOut(BaseModel):
    session_id: str


class ChatIn(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


class ChatOut(BaseModel):
    message_id: str
    reply: str
    outcome: str


@app.post("/session", response_model=SessionOut)
def start_session(body: SessionIn, background: BackgroundTasks) -> SessionOut:
    session_id = str(uuid.uuid4())
    background.add_task(db.safe, db.create_session, session_id, body.invite_code)
    return SessionOut(session_id=session_id)


@app.post("/chat", response_model=ChatOut)
async def chat(body: ChatIn, background: BackgroundTasks) -> ChatOut:
    message_id = str(uuid.uuid4())
    started = time.perf_counter()
    question = body.message.strip()
    provider = model = None
    prompt_tokens = completion_tokens = None
    fallback_used = False
    error_type = None

    try:
        result = await llm.complete(build_messages(question, load_knowledge()))
        provider, model = result.provider, result.model
        prompt_tokens, completion_tokens = result.prompt_tokens, result.completion_tokens
        fallback_used = result.fallback_used
        if result.text.strip().upper().startswith(UNKNOWN_TOKEN):
            outcome = "unknown"
            reply = f"I don't have that information yet. {contact_line()}"
        else:
            outcome = "answered"
            reply = result.text
    except Exception as exc:
        outcome = "error"
        error_type = type(exc).__name__
        reply = f"Sorry, I couldn't answer right now. {contact_line()}"

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
