import logging
import os

import psycopg

log = logging.getLogger("thatme.db")


def _connect():
    return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10)


def create_session(session_id: str, invite_code: str | None, visitor: dict) -> None:
    with _connect() as conn:
        visitor_id = conn.execute(
            """
            insert into visitors (name, email, company, role, linkedin_url, consent_at)
            values (%s, %s, %s, %s, %s, now())
            returning id
            """,
            (
                visitor["name"], visitor["email"], visitor["company"],
                visitor.get("role"), visitor.get("linkedin_url"),
            ),
        ).fetchone()[0]
        conn.execute(
            """
            insert into sessions (id, visitor_id, invite_code)
            values (%s, %s, (select code from invite_links where code = %s))
            """,
            (session_id, visitor_id, invite_code),
        )


def save_message(
    *,
    message_id: str,
    session_id: str,
    question: str,
    reply: str,
    outcome: str,
    provider: str | None,
    model: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_ms: int,
    fallback_used: bool,
    error_type: str | None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            insert into messages (
                id, session_id, question, reply, outcome, provider, model,
                prompt_tokens, completion_tokens, total_ms, fallback_used, error_type
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                message_id, session_id, question, reply, outcome, provider, model,
                prompt_tokens, completion_tokens, total_ms, fallback_used, error_type,
            ),
        )
        if outcome == "unknown":
            conn.execute(
                "insert into unknown_questions (message_id, question) values (%s, %s)",
                (message_id, question),
            )
        conn.execute(
            "update sessions set message_count = message_count + 1 where id = %s",
            (session_id,),
        )


def safe(fn, *args, **kwargs) -> None:
    try:
        fn(*args, **kwargs)
    except Exception:
        log.exception("background write failed: %s", fn.__name__)
