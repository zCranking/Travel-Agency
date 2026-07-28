"""Manual eval runner -- not a pytest suite (these are live LLM calls with
real cost, not something to run on every commit). Usage:
    cd api && .venv/Scripts/python.exe evals/run.py
Requires ANTHROPIC_API_KEY; prints SKIPPED and exits 0 without one.
"""
import sys

from agent.graph import build_agent_graph, classify_intent
from core.config import settings
from evals.scenarios import SCENARIOS


def run() -> int:
    if not settings.anthropic_api_key:
        print("SKIPPED: no ANTHROPIC_API_KEY configured.")
        return 0

    graph = build_agent_graph()
    passed = 0
    failed = 0

    for scenario in SCENARIOS:
        name = scenario["name"]
        message = scenario["message"]
        ok = True
        reasons = []

        if "expect_intent" in scenario:
            actual_intent = classify_intent(message)
            if actual_intent != scenario["expect_intent"]:
                ok = False
                reasons.append(f"intent: expected {scenario['expect_intent']!r}, got {actual_intent!r}")

        if scenario.get("expect_reply_contains"):
            result = graph.invoke({"messages": [{"role": "user", "content": message}]})
            reply = result["messages"][-1].content
            reply_text = reply if isinstance(reply, str) else str(reply)
            missing = [kw for kw in scenario["expect_reply_contains"] if kw.lower() not in reply_text.lower()]
            if missing:
                ok = False
                reasons.append(f"reply missing keywords: {missing} (got: {reply_text[:200]!r})")

        if ok:
            passed += 1
            print(f"PASS  {name}")
        else:
            failed += 1
            print(f"FAIL  {name} -- {'; '.join(reasons)}")

    print(f"\n{passed}/{len(SCENARIOS)} passed, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
