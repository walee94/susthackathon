import re

FORBIDDEN_REQUEST_PATTERNS = [
    r"\bshare\b.{0,30}\b(pin|otp|password|cvv|full card number|card number)\b",
    r"\bsend\b.{0,30}\b(pin|otp|password|cvv|full card number|card number)\b",
    r"\bprovide\b.{0,30}\b(pin|otp|password|cvv|full card number|card number)\b",
    r"\btell\b.{0,30}\b(pin|otp|password|cvv|full card number|card number)\b",
    r"\bverify\b.{0,30}\b(pin|otp|password|cvv|full card number|card number)\b",
    r"(পিন|ওটিপি|otp|pin).{0,30}(দিন|শেয়ার|শেয়ার|বলুন|পাঠান)",
]

UNAUTHORIZED_PROMISE_PATTERNS = [
    r"\bwe will refund\b",
    r"\bwill refund you\b",
    r"\brefund is confirmed\b",
    r"\breversal is confirmed\b",
    r"\baccount will be recovered\b",
    r"\bwe will recover\b",
    r"\bguaranteed refund\b",
    r"\bwe will unblock\b",
    r"\baccount unblock is confirmed\b",
]


def asks_for_secret(text: str) -> bool:
    lowered = (text or "").lower()
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in FORBIDDEN_REQUEST_PATTERNS)


def contains_unauthorized_promise(text: str) -> bool:
    lowered = (text or "").lower()
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in UNAUTHORIZED_PROMISE_PATTERNS)


def sanitize_customer_reply(text: str, language: str | None = "en") -> str:
    """
    Final guardrail before returning the customer-facing reply.
    Warnings like "do not share OTP" are allowed.
    Requests like "share OTP" are not allowed.
    """
    if asks_for_secret(text) or contains_unauthorized_promise(text):
        if language == "bn":
            return (
                "আপনার বিষয়টি আমরা নোট করেছি। আপডেটের জন্য শুধু অফিসিয়াল সাপোর্ট চ্যানেল ব্যবহার করুন। "
                "কারো সাথে আপনার পিন, ওটিপি, পাসওয়ার্ড বা সম্পূর্ণ কার্ড নম্বর শেয়ার করবেন না। "
                "যাচাইয়ের পর কোনো যোগ্য অর্থ অফিসিয়াল চ্যানেলের মাধ্যমে প্রক্রিয়া করা হবে।"
            )
        return (
            "We have noted your concern. Please use only official support channels for updates. "
            "Do not share your PIN, OTP, password, CVV, or full card number with anyone. "
            "Any eligible amount will be processed through official channels after verification."
        )
    return text


def sanitize_next_action(text: str, language: str | None = "en") -> str:
    """
    Final guardrail for the internal recommended_next_action string.
    The next-action is an instruction to a human agent, so the secret-asking
    guardrail is not strictly required, but the unauthorized-promise guardrail
    is: an internal recommendation must never tell an agent to confirm a
    refund, reversal, account unblock, or recovery. If such language is found,
    we fall back to a neutral, non-committal instruction.
    """
    if contains_unauthorized_promise(text):
        if language == "bn":
            return (
                "অভ্যন্তরীণ রেকর্ড যাচাই করুন এবং যেকোনো যোগ্য পরিমাণ শুধু অফিসিয়াল চ্যানেলের মাধ্যমে "
                "প্রক্রিয়া করুন। কোনো রিফান্ড, রিভার্সাল, আনব্লক বা অ্যাকাউন্ট রিকভারি নিশ্চিত করবেন না।"
            )
        return (
            "Verify internal records and process any eligible amount only through official channels. "
            "Do not confirm any refund, reversal, unblock, or account recovery."
        )
    return text


def safe_official_reply(case_type: str, txn_id: str | None, verdict: str, language: str | None = "en", department: str | None = None) -> str:
    lang = language or "en"

    if lang == "bn":
        txn_phrase = f" {txn_id}" if txn_id else ""
        if case_type == "phishing_or_social_engineering":
            return (
                "রিপোর্ট করার জন্য ধন্যবাদ। আমরা কখনো আপনার পিন, ওটিপি বা পাসওয়ার্ড চাই না। "
                "কারো সাথে এগুলো শেয়ার করবেন না। বিষয়টি আমাদের ফ্রড রিস্ক দল পর্যালোচনা করবে।"
            )
        if verdict == "insufficient_data":
            return (
                f"আপনার বিষয়টি আমরা নোট করেছি{txn_phrase}। সঠিক লেনদেন শনাক্ত করতে অনুগ্রহ করে "
                "লেনদেন আইডি, পরিমাণ এবং কী সমস্যা হয়েছে তা জানান। কারো সাথে পিন বা ওটিপি শেয়ার করবেন না।"
            )
        if case_type == "agent_cash_in_issue":
            return (
                f"আপনার লেনদেন {txn_id} এর বিষয়ে আমরা অবগত হয়েছি। আমাদের এজেন্ট অপারেশন্স দল এটি যাচাই করবে "
                "এবং অফিসিয়াল চ্যানেলে আপনাকে জানাবে। কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"
            )
        return (
            f"আপনার লেনদেন {txn_id} এর বিষয়ে আমরা অবগত হয়েছি। আমাদের সাপোর্ট দল এটি যাচাই করবে। "
            "যাচাইয়ের পর কোনো যোগ্য অর্থ অফিসিয়াল চ্যানেলের মাধ্যমে প্রক্রিয়া করা হবে। "
            "কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"
        )

    txn_phrase = f" about transaction {txn_id}" if txn_id else ""

    if case_type == "phishing_or_social_engineering":
        return (
            "Thank you for reporting this. We never ask for your PIN, OTP, password, CVV, "
            "or full card number under any circumstances. Do not share these with anyone, "
            "even if they claim to be from official support. Please continue only through official support channels."
        )

    if case_type == "merchant_settlement_delay" and txn_id:
        return (
            f"We have noted your concern about settlement {txn_id}. Our merchant operations team will check "
            "the batch status and update you through official channels."
        )

    if case_type == "refund_request" and verdict == "consistent":
        return (
            f"Thank you for reaching out. Refund eligibility for completed merchant payments may depend on "
            "the merchant policy and verification result. Please continue through official support channels. "
            "Do not share your PIN or OTP with anyone."
        )

    if verdict == "inconsistent":
        return (
            f"We have received your request{txn_phrase}. The available transaction history does not fully match "
            "the complaint, so the support team will verify the details through official workflow. "
            "Do not share your PIN or OTP with anyone."
        )

    if verdict == "insufficient_data":
        return (
            f"Thank you for reaching out. We need a little more detail to identify the correct transaction. "
            "Please share the transaction ID, amount, approximate time, or recipient or merchant identifier. "
            "Do not share your PIN or OTP with anyone."
        )

    return (
        f"We have noted your concern{txn_phrase}. Our support team will verify the details. "
        "Any eligible amount will be processed through official channels after verification. "
        "Do not share your PIN or OTP with anyone."
    )
