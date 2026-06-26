from .rules import has_any, normalize, select_relevant_transaction
from .safety import safe_official_reply, sanitize_customer_reply
from .schemas import AnalyzeTicketRequest, AnalyzeTicketResponse, Transaction


HIGH_VALUE_THRESHOLD = 10000


def detect_case_type(req: AnalyzeTicketRequest, tx: Transaction | None) -> str:
    text = normalize(req.complaint)
    user_type = req.user_type or "unknown"

    if has_any(text, [
        "otp", "pin", "password", "cvv", "full card", "scam", "fraud", "phishing",
        "suspicious", "fake call", "fake sms", "bkash officer", "verification code",
        "প্রতার", "ওটিপি", "পিন", "পাসওয়ার্ড",
    ]):
        return "phishing_or_social_engineering"

    if user_type == "merchant" or has_any(text, ["settlement", "settled", "merchant settlement", "merchant portal"]):
        return "merchant_settlement_delay"

    if user_type == "agent" or has_any(text, ["agent cash in", "cash in", "cash-in", "deposit through agent", "agent deposit"]):
        return "agent_cash_in_issue"

    if has_any(text, ["duplicate", "twice", "double charged", "charged twice", "two times", "same payment twice"]):
        return "duplicate_payment"

    if has_any(text, ["wrong number", "wrong recipient", "wrong transfer", "sent to wrong", "mistakenly sent", "ভুল নম্বর"]):
        return "wrong_transfer"

    if has_any(text, ["failed", "payment failed", "transaction failed", "deducted but failed", "failed but balance"]):
        return "payment_failed"

    if has_any(text, ["refund", "reversal", "return my money", "money back", "ফেরত"]):
        return "refund_request"

    if tx:
        if tx.type == "transfer":
            return "wrong_transfer" if has_any(text, ["wrong", "mistake", "ভুল"]) else "other"
        if tx.type == "payment" and tx.status == "failed":
            return "payment_failed"
        if tx.type == "payment":
            return "refund_request" if has_any(text, ["refund", "return"]) else "other"
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


def evidence_verdict(req: AnalyzeTicketRequest, tx: Transaction | None, case_type: str) -> str:
    text = normalize(req.complaint)
    history = req.transaction_history or []

    if case_type == "phishing_or_social_engineering":
        # These are safety reports. Transaction history may be irrelevant.
        return "insufficient_data" if not tx else "consistent"

    if not history or not tx:
        return "insufficient_data"

    if case_type == "payment_failed":
        if tx.status == "failed":
            return "consistent"
        if tx.status in ["completed", "reversed"]:
            return "inconsistent"
        return "insufficient_data"

    if case_type == "wrong_transfer":
        if tx.type == "transfer" and tx.status == "completed":
            return "consistent"
        if tx.type == "transfer" and tx.status in ["failed", "reversed"]:
            return "inconsistent"
        return "insufficient_data"

    if case_type == "duplicate_payment":
        payments = [
            t for t in history
            if t.type == "payment"
            and t.counterparty == tx.counterparty
            and abs(float(t.amount) - float(tx.amount)) < 0.01
            and t.status in ["completed", "pending"]
        ]
        return "consistent" if len(payments) >= 2 else "insufficient_data"

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
        if tx.status in ["completed", "pending", "failed"]:
            return "consistent"
        if tx.status == "reversed":
            return "inconsistent"
        return "insufficient_data"

    return "insufficient_data"


def determine_severity(req: AnalyzeTicketRequest, case_type: str, tx: Transaction | None, verdict: str) -> str:
    amount = float(tx.amount) if tx else 0.0

    if case_type == "phishing_or_social_engineering":
        return "critical"

    if amount >= HIGH_VALUE_THRESHOLD:
        return "high"

    if case_type in ["wrong_transfer", "duplicate_payment", "agent_cash_in_issue"]:
        return "high" if amount >= 5000 else "medium"

    if verdict in ["inconsistent", "insufficient_data"]:
        return "medium"

    if case_type in ["payment_failed", "refund_request", "merchant_settlement_delay"]:
        return "medium"

    return "low"


def needs_human_review(case_type: str, severity: str, verdict: str, tx: Transaction | None) -> bool:
    if case_type in [
        "wrong_transfer",
        "phishing_or_social_engineering",
        "duplicate_payment",
        "agent_cash_in_issue",
    ]:
        return True

    if severity in ["high", "critical"]:
        return True

    if verdict in ["inconsistent", "insufficient_data"]:
        return True

    if tx and float(tx.amount) >= HIGH_VALUE_THRESHOLD:
        return True

    return False


def build_reason_codes(case_type: str, tx: Transaction | None, verdict: str, score: int) -> list[str]:
    codes = [case_type, verdict]
    if tx:
        codes.append("transaction_match")
        codes.append(f"txn_status_{tx.status}")
        codes.append(f"txn_type_{tx.type}")
    else:
        codes.append("no_transaction_match")
    if score >= 6:
        codes.append("strong_match")
    elif score >= 3:
        codes.append("partial_match")
    return codes


def build_summary(req: AnalyzeTicketRequest, tx: Transaction | None, case_type: str, verdict: str) -> str:
    if tx:
        return (
            f"Ticket {req.ticket_id}: customer reports a {case_type} issue linked to "
            f"{tx.transaction_id} for {tx.amount:.0f} BDT. Evidence verdict: {verdict}."
        )
    return (
        f"Ticket {req.ticket_id}: customer reports a {case_type} issue, but no matching transaction "
        f"was identified in the provided history. Evidence verdict: {verdict}."
    )


def build_next_action(case_type: str, tx: Transaction | None, verdict: str, human_review: bool) -> str:
    txn_ref = tx.transaction_id if tx else "the reported transaction"

    if case_type == "phishing_or_social_engineering":
        return (
            "Route to fraud_risk, preserve the suspicious message or caller details if available, "
            "and remind the customer to use only official support channels."
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

    if human_review:
        return (
            f"Escalate {txn_ref} for human review and verify transaction status, amount, counterparty, "
            "and eligibility through official workflow."
        )

    return (
        f"Review {txn_ref} through the normal support workflow and send the safe customer reply."
    )


def analyze_ticket(req: AnalyzeTicketRequest) -> AnalyzeTicketResponse:
    tx, score = select_relevant_transaction(req.complaint, req.transaction_history or [])
    case_type = detect_case_type(req, tx)
    verdict = evidence_verdict(req, tx, case_type)
    severity = determine_severity(req, case_type, tx, verdict)
    department = map_department(case_type, severity, verdict)
    human_review = needs_human_review(case_type, severity, verdict, tx)

    agent_summary = build_summary(req, tx, case_type, verdict)
    recommended_next_action = build_next_action(case_type, tx, verdict, human_review)
    customer_reply = sanitize_customer_reply(
        safe_official_reply(case_type, tx.transaction_id if tx else None, verdict)
    )

    confidence = 0.85
    if verdict == "consistent" and score >= 6:
        confidence = 0.92
    elif verdict == "consistent":
        confidence = 0.78
    elif verdict == "insufficient_data":
        confidence = 0.55
    elif verdict == "inconsistent":
        confidence = 0.72

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
        reason_codes=build_reason_codes(case_type, tx, verdict, score),
    )
