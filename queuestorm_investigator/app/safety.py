import re

FORBIDDEN_CREDENTIAL_TERMS = [
    "pin",
    "otp",
    "password",
    "full card number",
    "card number",
    "cvv",
]

UNAUTHORIZED_PROMISE_PATTERNS = [
    r"\bwe will refund\b",
    r"\bwill refund you\b",
    r"\brefund is confirmed\b",
    r"\breversal is confirmed\b",
    r"\baccount will be recovered\b",
    r"\bwe will recover\b",
    r"\bguaranteed refund\b",
]


def contains_forbidden_customer_request(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in FORBIDDEN_CREDENTIAL_TERMS)


def contains_unauthorized_promise(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in UNAUTHORIZED_PROMISE_PATTERNS)


def sanitize_customer_reply(text: str) -> str:
    """
    Final guardrail before returning the customer-facing reply.
    It avoids credential requests and refund promises.
    """
    if contains_forbidden_customer_request(text) or contains_unauthorized_promise(text):
        return (
            "We have noted your concern. Please use only official support channels for updates. "
            "Do not share your PIN, OTP, password, or full card number with anyone. "
            "Any eligible amount will be processed through official channels after verification."
        )
    return text


def safe_official_reply(case_type: str, txn_id: str | None, verdict: str) -> str:
    txn_phrase = f" about transaction {txn_id}" if txn_id else ""
    if case_type == "phishing_or_social_engineering":
        return (
            "We have noted your report of a suspicious contact. Do not share your PIN, OTP, password, "
            "or full card number with anyone. Please continue only through official support channels."
        )
    if verdict == "inconsistent":
        return (
            f"We have reviewed the information provided{txn_phrase}. The available transaction history "
            "does not fully match the complaint, so our support team will verify the details further."
        )
    if verdict == "insufficient_data":
        return (
            f"We have noted your concern{txn_phrase}. The available information is not enough to confirm "
            "the issue yet, so our support team will review it through official channels."
        )
    return (
        f"We have noted your concern{txn_phrase}. Our support team will verify the details. "
        "Any eligible amount will be processed through official channels after verification."
    )
