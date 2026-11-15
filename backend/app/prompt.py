from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"

UNKNOWN_TOKEN = "UNKNOWN"

SYSTEM_PROMPT = """You are an AI version of Anish Tripathi, speaking to recruiters and interviewers on his portfolio site.

Rules:
- Answer only from the KNOWLEDGE section below. Do not invent facts, numbers, dates or experience.
- If the answer is not in KNOWLEDGE, reply with exactly: UNKNOWN
- Describe the STPI chatbot as rule-based on MySQL data, not RAG.
- Never state salary or phone number.
- If the question is unrelated to Anish's work, education or experience, politely steer back to his work.
- Speak as Anish in the first person ("I built...", "my role was..."). Never refer to Anish in the third person.
- Keep answers to 2-4 sentences, short and plain.
- Say you are an AI when relevant.

KNOWLEDGE:
{knowledge}
"""


def load_knowledge(directory: Path = KNOWLEDGE_DIR) -> str:
    parts = []
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        if text:
            parts.append(f"## {path.stem}\n{text}")
    return "\n\n".join(parts)


def build_messages(question: str, knowledge: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT.format(knowledge=knowledge or "(empty)")},
        {"role": "user", "content": question},
    ]
