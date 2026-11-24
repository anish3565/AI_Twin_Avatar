# AI Twin Avatar

An AI version of Anish Tripathi for recruiters and interviewers. Visitors can ask questions by typing, by talking, or with a cartoon avatar that speaks the answers. Replies are grounded in Anish's own notes and never invent facts. Each conversation and its mode are saved for review.

Live site: https://aitwinavatar-frontend.vercel.app

## What it does

- **Three modes:** Avatar (a cartoon that speaks the replies and moves its mouth with the voice), Talk (voice in, spoken replies) and Type (text only). A **Switch mode** button lets visitors change mode at any time and keeps the same conversation.
- **Stage view:** in Avatar and Talk modes, only the current question and answer show in full. Scrolling up, or the History button, opens the whole conversation.
- **Grounded answers:** the bot answers only from the Markdown files in `knowledge/`. If the answer is not there, it says so and points to the contact email.
- **Queued questions:** a question sent while a reply is still arriving waits and is sent when the reply finishes.
- **Safety:** prompt-injection checks, a reply guard that blocks unknown links and leaked instructions, and rate limits per visitor.
- **Consent first:** the bot asks before collecting a name, company, role and the role being hired for. Details are saved only after explicit consent.
- **Lead alerts:** when a visitor shares their details, an alert goes to Telegram (optional).
- **Free to run:** Groq is the main model, Gemini is the backup, and the avatar runs in the browser with no GPU.

## How it is built

```
frontend/   Static page (HTML, CSS, JavaScript). Calls the backend API.
backend/    FastAPI app: /session, /visitor, /chat, /chat/stream.
  app/guard.py    Injection check and reply guard.
  app/prompt.py   System prompt and knowledge loading.
  app/llm.py      Groq first, Gemini fallback.
  app/db.py       Postgres (Supabase) writes.
  app/notify.py   Telegram lead alerts.
knowledge/  The only facts the bot may use.
db/         schema.sql (new database) and migrations/ (changes to existing ones).
evals/      50 test questions and the scoring script.
```

The frontend and backend are deployed as two Vercel projects. The backend is configured by `pyproject.toml` (`[tool.vercel]`).

## Run it locally

Requirements: Python 3.11 or newer, and a Postgres database (for example a free Supabase project).

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file in the project root (it is git-ignored) with the variables below, then start the API:

```powershell
uvicorn backend.app.main:app --reload
```

Serve the frontend with any static server and open it in a browser:

```powershell
cd frontend
python -m http.server 5173
```

Note: `frontend/js/chat.js` calls the live API at `API_BASE`. To use your local API, change that constant and add your frontend origin to `ALLOWED_ORIGINS`.

## Environment variables

Set these in `.env` locally, or in the Vercel project settings when deployed. Never commit values.

| Name | Required | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Yes | Postgres connection string |
| `GROQ_API_KEY` | Yes | Main language model |
| `GEMINI_API_KEY` | Yes | Backup language model |
| `GROQ_MODEL` | No | Override the Groq model name |
| `GEMINI_MODEL` | No | Override the Gemini model name |
| `CONTACT_EMAIL` | Yes | Shown to visitors and used in the reply guard |
| `CONTACT_LINKEDIN` | No | LinkedIn URL the bot may share |
| `ALLOWED_ORIGINS` | Yes (deployed) | Comma-separated frontend origins allowed by CORS |
| `TELEGRAM_BOT_TOKEN` | No | Enables lead alerts |
| `TELEGRAM_CHAT_ID` | No | Chat that receives lead alerts |

## Database setup

- **New database:** run `db/schema.sql`, then `db/views.sql`.
- **Existing database:** run each file in `db/migrations/` in order. `001_message_mode.sql` adds the `messages.mode` column that records whether a question was asked in avatar, voice or text mode.

## Tests

```powershell
pytest
```

The test suite runs without calling any model or database. It covers the guard, the prompt, the chat and stream endpoints, mode handling, rate limits and the stray UNKNOWN fix. It currently runs 65 tests.

## Evaluation

`evals/questions.jsonl` holds 50 questions in five categories: fact, unknown, privacy, offtopic and injection. The script calls the live model, so it needs the API keys.

```powershell
python evals/run_eval.py --out evals/results.json
```

It prints a pass or fail line for each question, a score per category, and the total. The exit code is non-zero if any question fails.

Latest run (2026-11-24, live Groq model with Gemini fallback, before the stray UNKNOWN fix):

| Category | Passed |
| --- | --- |
| fact | 32 / 32 |
| unknown | 8 / 8 |
| privacy | 4 / 4 |
| offtopic | 3 / 3 |
| injection | 3 / 3 |
| **Total** | **50 / 50 (100%)** |

Model answers can vary between runs, so treat this as a snapshot.

## Privacy and facts

- The bot never states a salary, phone number or home address. Those are not in `knowledge/`.
- Anish's contact email is the only address the bot may print.
- Visitors see a notice that the chat is an AI version of Anish, and that the conversation may be stored.

## Status

Built: knowledge-grounded chat, three modes with switching, the stage view with scroll-up history, the animated avatar, consent and lead alerts, the reply guard, rate limits, queued questions, the evaluation set, and per-message mode tracking.

Not yet built: usage tracking with an 80% alert, thumbs up or down feedback, timing and error telemetry, the admin dashboard, job-fit mode, and session tags. The database already has columns for some of these.

## Known limitations

- **Avatar lip-sync is approximate.** The mouth opens and closes with each sentence's start and end, not with individual sounds.
- **Voice input needs Chrome or Edge.** Where speech recognition is missing, the Talk option is disabled. Avatar mode still speaks the replies.
- **Spoken voice depends on the browser.** The chosen voice is whatever the browser provides.
- **Model memory is short.** The model sees only the last four turns. The full conversation is kept on screen and in the database.

## License

See [LICENSE](LICENSE).
