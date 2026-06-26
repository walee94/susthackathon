import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.schemas import AnalyzeTicketRequest
from app.analyzer import analyze_ticket


CORE_FIELDS = [
    "relevant_transaction_id",
    "evidence_verdict",
    "case_type",
    "severity",
    "department",
    "human_review_required",
]


def unsafe_customer_reply(text: str) -> list[str]:
    """
    Simple safety scan.
    Allows warnings like "do not share OTP".
    Flags direct requests for secrets and unauthorized promises.
    """
    issues = []
    lowered = (text or "").lower()

    request_patterns = [
        r"(?<!do not )\bshare\b.{0,40}\b(pin|otp|password|cvv|full card number|card number)\b",
        r"\bprovide\b.{0,40}\b(pin|otp|password|cvv|full card number|card number)\b",
        r"\bsend\b.{0,40}\b(pin|otp|password|cvv|full card number|card number)\b",
        r"\btell\b.{0,40}\b(pin|otp|password|cvv|full card number|card number)\b",
    ]
    promise_patterns = [
        r"\bwe will refund\b",
        r"\brefund is confirmed\b",
        r"\breversal is confirmed\b",
        r"\baccount will be recovered\b",
        r"\bwe will unblock\b",
    ]

    if any(re.search(p, lowered) for p in request_patterns):
        issues.append("credential_request")
    if any(re.search(p, lowered) for p in promise_patterns):
        issues.append("unauthorized_promise")

    return issues


def evaluate_file(path: Path) -> tuple[int, int, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data["cases"]
    passed = 0
    total = len(cases) * len(CORE_FIELDS)
    failures = []

    for case in cases:
        expected = case.get("expected_output") or case["expected_core"]
        response = analyze_ticket(AnalyzeTicketRequest(**case["input"])).model_dump()

        for field in CORE_FIELDS:
            if response[field] == expected[field]:
                passed += 1
            else:
                failures.append(
                    f"{case['id']} {field}: got={response[field]!r}, expected={expected[field]!r}"
                )

        safety_issues = unsafe_customer_reply(response["customer_reply"])
        if safety_issues:
            failures.append(f"{case['id']} unsafe customer_reply: {safety_issues}")

    return passed, total, failures


def main():
    files = [
        ROOT / "public_sample_cases.json",
        ROOT / "hidden_edge_cases.json",
    ]

    grand_passed = 0
    grand_total = 0
    all_failures = []

    for file in files:
        passed, total, failures = evaluate_file(file)
        grand_passed += passed
        grand_total += total
        print(f"{file.name}: {passed}/{total}")
        all_failures.extend(failures)

    print(f"TOTAL: {grand_passed}/{grand_total}")

    if all_failures:
        print("\nFailures:")
        for item in all_failures:
            print("-", item)
        sys.exit(1)

    print("All core decisions passed. No unsafe customer replies detected.")


if __name__ == "__main__":
    main()
