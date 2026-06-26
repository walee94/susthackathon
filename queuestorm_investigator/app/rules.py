import re
from typing import Iterable, Optional

from .schemas import Transaction


def normalize(text: str) -> str:
    return (text or "").lower().strip()


def extract_amounts(text: str) -> list[float]:
    """
    Extract simple numeric amounts from English/Banglish complaint text.
    Examples: 5000, 5,000, 5000 taka, 5000 tk.
    """
    raw = re.findall(r"(?<!\d)(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\d)", text or "")
    amounts = []
    for item in raw:
        try:
            amounts.append(float(item.replace(",", "")))
        except ValueError:
            pass
    return amounts


def complaint_mentions_counterparty(complaint: str, counterparty: Optional[str]) -> bool:
    if not counterparty:
        return False
    c = normalize(complaint)
    cp = counterparty.lower()
    compact_cp = re.sub(r"\D", "", cp)
    compact_text = re.sub(r"\D", "", c)
    return cp in c or bool(compact_cp and compact_cp in compact_text)


def has_any(text: str, keywords: Iterable[str]) -> bool:
    lowered = normalize(text)
    return any(k in lowered for k in keywords)


def amount_matches(complaint: str, tx: Transaction) -> bool:
    amounts = extract_amounts(complaint)
    if not amounts:
        return False
    return any(abs(a - float(tx.amount)) < 0.01 for a in amounts)


def txn_score(complaint: str, tx: Transaction) -> int:
    score = 0

    if amount_matches(complaint, tx):
        score += 4

    if complaint_mentions_counterparty(complaint, tx.counterparty):
        score += 4

    lowered = normalize(complaint)

    type_words = {
        "transfer": ["transfer", "send", "sent", "wrong number", "wrong recipient", "ভুল", "পাঠাই"],
        "payment": ["payment", "paid", "merchant", "shop", "bill", "পেমেন্ট"],
        "cash_in": ["cash in", "cash-in", "deposit", "agent", "cashin", "ক্যাশ ইন"],
        "cash_out": ["cash out", "cash-out", "withdraw", "cashout", "ক্যাশ আউট"],
        "settlement": ["settlement", "merchant settlement", "settled", "settle"],
        "refund": ["refund", "reversal", "returned", "ফেরত"],
    }

    if any(word in lowered for word in type_words.get(tx.type, [])):
        score += 2

    status_words = {
        "completed": ["completed", "success", "successful", "deducted", "charged"],
        "failed": ["failed", "fail", "unsuccessful"],
        "pending": ["pending", "processing"],
        "reversed": ["reversed", "returned", "refunded"],
    }

    if any(word in lowered for word in status_words.get(tx.status, [])):
        score += 1

    return score


def select_relevant_transaction(complaint: str, history: list[Transaction]) -> tuple[Optional[Transaction], int]:
    if not history:
        return None, 0

    scored = [(txn_score(complaint, tx), tx) for tx in history]
    scored.sort(key=lambda x: x[0], reverse=True)

    best_score, best_tx = scored[0]
    if best_score >= 3:
        return best_tx, best_score

    return None, best_score
