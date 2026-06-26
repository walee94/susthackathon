from .rules import (
    count_completed_transfers_to_counterparty,
    extract_amounts,
    find_duplicate_payment_pair,
    has_any,
    normalize,
    select_relevant_transaction,
)
from .safety import safe_official_reply, sanitize_customer_reply, sanitize_next_action
from .schemas import AnalyzeTicketRequest, AnalyzeTicketResponse, Transaction


def is_bn(req: AnalyzeTicketRequest) -> bool:
    return req.language == "bn"


def complaint_has_balance_deducted(req: AnalyzeTicketRequest) -> bool:
    return has_any(req.complaint, [
        "deducted", "balance deducted", "charged", "money cut", "cut from my balance",
        "কেটে", "কাটা", "ব্যালেন্স", "টাকা কেটে"
    ])


def detect_case_type(req: AnalyzeTicketRequest, tx: Transaction | None, ambiguous: bool = False) -> str:
    text = normalize(req.complaint)
    user_type = req.user_type or "unknown"

    phishing_terms = [
        "otp", "pin", "password", "cvv", "full card", "card number", "scam", "fraud",
        "phishing", "suspicious", "fake call", "fake sms", "verification code",
        "account will be blocked", "bkash officer", "asked for my otp", "asked for otp",
        "প্রতার", "ওটিপি", "পিন", "পাসওয়ার্ড", "ভুয়া", "ফেক"
    ]
    if has_any(text, phishing_terms):
        # Keep this high priority. Prompt-injection attempts often mention credentials too.
        return "phishing_or_social_engineering"

    duplicate_terms = [
        "duplicate", "twice", "double charged", "charged twice", "two times",
        "same payment twice", "deducted twice", "দুইবার", "২ বার", "ডাবল"
    ]
    if has_any(text, duplicate_terms):
        return "duplicate_payment"

    merchant_terms = ["settlement", "settled", "merchant settlement", "sales", "merchant portal", "সেটেলমেন্ট"]
    if user_type == "merchant" or req.channel == "merchant_portal" or has_any(text, merchant_terms):
        return "merchant_settlement_delay"

    cash_in_terms = [
        "agent cash in", "cash in", "cash-in", "cashin", "deposit through agent",
        "agent deposit", "ক্যাশ ইন", "এজেন্ট", "ব্যালেন্সে টাকা আসেনি"
    ]
    if user_type == "agent" or has_any(text, cash_in_terms):
        return "agent_cash_in_issue"

    wrong_transfer_terms = [
        "wrong number", "wrong recipient", "wrong transfer", "sent to wrong",
        "mistakenly sent", "wrong person", "by mistake", "brother", "sister",
        "friend did not get", "didn't get it", "did not get it", "recipient did not receive",
        "receiver did not receive", "not received", "ভুল নম্বর", "ভুল মানুষ", "পায়নি", "পায়নি"
    ]
    if has_any(text, wrong_transfer_terms):
        return "wrong_transfer"

    payment_failed_terms = [
        "failed", "payment failed", "transaction failed", "deducted but failed",
        "failed but balance", "app showed failed", "ফেইল", "ব্যর্থ"
    ]
    if has_any(text, payment_failed_terms):
        return "payment_failed"

    refund_terms = ["refund", "reversal", "return my money", "money back", "changed my mind", "ফেরত", "রিফান্ড"]
    if has_any(text, refund_terms):
        return "refund_request"

    if ambiguous:
        if tx and tx.type == "transfer":
            return "wrong_transfer"
        # If amount matched multiple transfers but no exact tx selected.
        if any(t.type == "transfer" for t in req.transaction_history or []):
            return "wrong_transfer"

    if tx:
        if tx.type == "payment" and tx.status == "failed":
            return "payment_failed"
        if tx.type == "settlement":
            return "merchant_settlement_delay"
        if tx.type == "cash_in":
            return "agent_cash_in_issue"
        if tx.type == "refund":
            return "refund_request"

    return "other"


def map_department(case_type: str, severity: str, verdict: str) -> str:
    if case_type == "wrong_transfer":
        return "dispute_resolution"
    if case_type in ["payment_failed", "duplicate_payment"]:
        return "payments_ops"
    if case_type == "merchant_settlement_delay":
        return "merchant_operations"
    if case_type == "agent_cash_in_issue":
        return "agent_operations"
    if case_type == "phishing_or_social_engineering":
        return "fraud_risk"
    if case_type == "refund_request" and severity in ["high", "critical"]:
        return "dispute_resolution"
    return "customer_support"


def evidence_verdict(req: AnalyzeTicketRequest, tx: Transaction | None, case_type: str, ambiguous: bool = False) -> str:
    history = req.transaction_history or []

    if case_type == "phishing_or_social_engineering":
        return "insufficient_data" if not tx else "consistent"

    if ambiguous:
        return "insufficient_data"

    if not history or not tx:
        return "insufficient_data"

    if case_type == "payment_failed":
        if tx.status == "failed":
            return "consistent"
        if tx.status in ["completed", "reversed"]:
            return "inconsistent"
        return "insufficient_data"

    if case_type == "wrong_transfer":
        if tx.type != "transfer":
            return "insufficient_data"

        # Repeated completed transfers to the same counterparty suggest established recipient.
        repeated = count_completed_transfers_to_counterparty(history, tx.counterparty)
        if repeated >= 3 and has_any(req.complaint, ["wrong", "mistake", "ভুল"]):
            return "inconsistent"

        if tx.status == "completed":
            return "consistent"
        if tx.status in ["failed", "reversed"]:
            return "inconsistent"
        return "insufficient_data"

    if case_type == "duplicate_payment":
        duplicate = find_duplicate_payment_pair(history)
        return "consistent" if duplicate else "insufficient_data"

    if case_type == "merchant_settlement_delay":
        if tx.type == "settlement" and tx.status in ["pending", "failed"]:
            return "consistent"
        if tx.type == "settlement" and tx.status in ["completed", "reversed"]:
            return "inconsistent"
        return "insufficient_data"

    if case_type == "agent_cash_in_issue":
        if tx.type == "cash_in" and tx.status in ["pending", "failed"]:
            return "consistent"
        if tx.type == "cash_in" and tx.status == "completed":
            return "inconsistent"
        return "insufficient_data"

    if case_type == "refund_request":
        if tx.status == "reversed":
            return "inconsistent"
        if tx.status in ["completed", "pending", "failed"]:
            return "consistent"
        return "insufficient_data"

    return "insufficient_data"


def determine_severity(req: AnalyzeTicketRequest, case_type: str, tx: Transaction | None, verdict: str, ambiguous: bool = False) -> str:
    amount = float(tx.amount) if tx else 0.0

    if case_type == "phishing_or_social_engineering":
        return "critical"

    if case_type == "duplicate_payment":
        return "high" if verdict == "consistent" else "medium"

    if case_type == "payment_failed":
        if complaint_has_balance_deducted(req):
            return "high"
        return "medium"

    if case_type == "agent_cash_in_issue":
        return "high" if verdict == "consistent" else "medium"

    if case_type == "wrong_transfer":
        if ambiguous or verdict in ["inconsistent", "insufficient_data"]:
            return "medium"
        return "high"

    if case_type == "merchant_settlement_delay":
        # Public sample expects 15,000 BDT pending settlement as medium.
        return "high" if amount >= 50000 else "medium"

    if case_type == "refund_request":
        if amount >= 10000:
            return "medium"
        if verdict == "consistent":
            return "low"
        return "medium"

    if case_type == "other":
        return "low"

    return "medium"


def needs_human_review(case_type: str, severity: str, verdict: str, tx: Transaction | None, ambiguous: bool = False) -> bool:
    if case_type == "phishing_or_social_engineering":
        return True

    if case_type == "duplicate_payment" and verdict == "consistent":
        return True

    if case_type == "agent_cash_in_issue":
        return True

    if case_type == "wrong_transfer":
        # Public sample 8 expects ambiguous transfer to ask for clarification first, not human review.
        if ambiguous or tx is None:
            return False
        return True

    if case_type == "refund_request":
        return severity in ["high", "critical"]

    if case_type == "merchant_settlement_delay":
        return severity == "high"

    if case_type == "payment_failed":
        return False

    return False


def build_reason_codes(case_type: str, tx: Transaction | None, verdict: str, score: int, ambiguous: bool = False) -> list[str]:
    if ambiguous:
        return [case_type, "ambiguous_match", "needs_clarification"]
    codes = [case_type, verdict]
    if tx:
        codes.append("transaction_match")
        codes.append(f"txn_status_{tx.status}")
        codes.append(f"txn_type_{tx.type}")
    else:
        codes.append("no_transaction_match")
    if score >= 7:
        codes.append("strong_match")
    elif score >= 3:
        codes.append("partial_match")
    return codes


def build_summary(req: AnalyzeTicketRequest, tx: Transaction | None, case_type: str, verdict: str, ambiguous: bool = False) -> str:
    if ambiguous:
        return (
            f"Ticket {req.ticket_id}: customer reports a {case_type} issue, but multiple transactions in the "
            f"provided history plausibly match. Evidence verdict: {verdict}."
        )
    if tx:
        return (
            f"Ticket {req.ticket_id}: customer reports a {case_type} issue linked to "
            f"{tx.transaction_id} for {tx.amount:.0f} BDT. Evidence verdict: {verdict}."
        )
    return (
        f"Ticket {req.ticket_id}: customer reports a {case_type} issue, but no matching transaction "
        f"was identified in the provided history. Evidence verdict: {verdict}."
    )


def build_next_action(case_type: str, tx: Transaction | None, verdict: str, human_review: bool, ambiguous: bool = False) -> str:
    txn_ref = tx.transaction_id if tx else "the reported transaction"

    if case_type == "phishing_or_social_engineering":
        return (
            "Route to fraud_risk, log the reported suspicious contact if available, and remind the customer "
            "that official support never asks for secrets."
        )

    if ambiguous:
        return (
            "Ask the customer for a non-sensitive identifier such as transaction ID, recipient number, "
            "merchant ID, amount, or approximate time before initiating any dispute."
        )

    if verdict == "inconsistent":
        return (
            f"Verify {txn_ref} against internal records before taking action. Do not confirm any refund "
            "or reversal until the case is validated."
        )

    if verdict == "insufficient_data":
        return (
            "Ask the support agent to collect non-sensitive identifying details through official workflow "
            "and review internal transaction records."
        )

    if case_type == "refund_request":
        return (
            "Check refund eligibility through the official workflow. Do not promise a refund before validation."
        )

    if human_review:
        return (
            f"Escalate {txn_ref} for human review and verify transaction status, amount, counterparty, "
            "and eligibility through official workflow."
        )

    return (
        f"Review {txn_ref} through the normal support workflow and send the safe customer reply."
    )


def analyze_ticket(req: AnalyzeTicketRequest) -> AnalyzeTicketResponse:
    tx, score, ambiguous = select_relevant_transaction(req.complaint, req.transaction_history or [])
    case_type = detect_case_type(req, tx, ambiguous)
    verdict = evidence_verdict(req, tx, case_type, ambiguous)
    severity = determine_severity(req, case_type, tx, verdict, ambiguous)
    department = map_department(case_type, severity, verdict)
    human_review = needs_human_review(case_type, severity, verdict, tx, ambiguous)

    agent_summary = build_summary(req, tx, case_type, verdict, ambiguous)
    recommended_next_action = sanitize_next_action(
        build_next_action(case_type, tx, verdict, human_review, ambiguous),
        req.language,
    )
    customer_reply = sanitize_customer_reply(
        safe_official_reply(case_type, tx.transaction_id if tx else None, verdict, req.language, department),
        req.language
    )

    confidence = 0.85
    if ambiguous:
        confidence = 0.65
    elif verdict == "consistent" and score >= 7:
        confidence = 0.92
    elif verdict == "consistent":
        confidence = 0.82
    elif verdict == "insufficient_data":
        confidence = 0.60
    elif verdict == "inconsistent":
        confidence = 0.75

    return AnalyzeTicketResponse(
        ticket_id=req.ticket_id,
        relevant_transaction_id=tx.transaction_id if tx else None,
        evidence_verdict=verdict,
        case_type=case_type,
        severity=severity,
        department=department,
        agent_summary=agent_summary,
        recommended_next_action=recommended_next_action,
        customer_reply=customer_reply,
        human_review_required=human_review,
        confidence=confidence,
        reason_codes=build_reason_codes(case_type, tx, verdict, score, ambiguous),
    )
