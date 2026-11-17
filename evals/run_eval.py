import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / ".env")

from app import llm  # noqa: E402
from app.guard import BLOCKED_REPLY, SAFE_FALLBACK_REPLY, looks_like_injection, reply_is_safe  # noqa: E402
from app.prompt import UNKNOWN_TOKEN, build_messages, load_knowledge  # noqa: E402

QUESTIONS = ROOT / "evals" / "questions.jsonl"


ATTEMPTS = 3
RETRY_DELAY_SECONDS = 5
DASHES = re.compile("[‐-―−]")


def normalize(text: str) -> str:
    return " ".join(DASHES.sub("-", text).split()).lower()


COMPLETE = llm.complete


async def answer(question: str) -> tuple[str, str]:
    if looks_like_injection(question):
        return "refused", BLOCKED_REPLY
    for attempt in range(ATTEMPTS):
        try:
            result = await COMPLETE(build_messages(question, load_knowledge()))
            break
        except Exception as exc:
            if attempt == ATTEMPTS - 1:
                return "error", f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(RETRY_DELAY_SECONDS)
    text = result.text.strip()
    if text.upper().startswith(UNKNOWN_TOKEN):
        return "unknown", text
    if not reply_is_safe(text):
        return "refused", SAFE_FALLBACK_REPLY
    return "answered", text


def check(item: dict, outcome: str, reply: str) -> list[str]:
    failures = []
    if outcome == "error":
        return [f"provider error: {reply}"]
    lowered = normalize(reply)
    if "expect" in item and outcome != "unknown":
        failures.append(f"expected UNKNOWN, got {outcome}")
    for term in item.get("must_contain", []):
        if normalize(term) not in lowered:
            failures.append(f"missing '{term}'")
    for term in item.get("must_not_contain", []):
        if normalize(term) in lowered:
            failures.append(f"contains '{term}'")
    pattern = item.get("must_not_match")
    if pattern and re.search(pattern, reply):
        failures.append(f"matches /{pattern}/")
    if item["category"] == "fact" and outcome != "answered":
        failures.append(f"outcome {outcome}")
    return failures


async def run(items: list[dict]) -> list[dict]:
    results = []
    for item in items:
        outcome, reply = await answer(item["question"])
        failures = check(item, outcome, reply)
        results.append(
            {
                "id": item["id"],
                "category": item["category"],
                "question": item["question"],
                "outcome": outcome,
                "reply": reply,
                "passed": not failures,
                "failures": failures,
            }
        )
    return results


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Score the chat bot against evals/questions.jsonl.")
    parser.add_argument("--out", type=Path, help="Write full results to this JSON file.")
    parser.add_argument("--groq-only", action="store_true", help="Skip the Gemini fallback.")
    args = parser.parse_args()
    global COMPLETE
    if args.groq_only:
        COMPLETE = llm._groq

    items = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
    results = asyncio.run(run(items))

    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"{status} {r['id']} [{r['category']}] {r['question']}")
        if not r["passed"]:
            print(f"     {'; '.join(r['failures'])}")
            print(f"     reply: {r['reply']}")

    by_category: dict[str, list[bool]] = {}
    for r in results:
        by_category.setdefault(r["category"], []).append(r["passed"])
    print()
    for category, flags in sorted(by_category.items()):
        print(f"{category:10} {sum(flags)}/{len(flags)}")
    total = sum(r["passed"] for r in results)
    print(f"{'total':10} {total}/{len(results)}  ({total / len(results):.0%})")

    if args.out:
        args.out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    sys.exit(0 if total == len(results) else 1)


if __name__ == "__main__":
    main()
