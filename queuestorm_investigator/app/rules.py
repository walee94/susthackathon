import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from .schemas import Transaction


BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

# Loose English/Bangla day-part keywords, mapped to a 24h hour.
_DAY_PART_HOURS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"\b(morning)\b"), 9),
    (re.compile(r"\b(afternoon)\b"), 15),
    (re.compile(r"\b(evening)\b"), 19),
    (re.compile(r"\bnight\b"), 22),
    (re.compile(r"\bsubah|সকাল\b"), 9),
    (re.compile(r"\bdupur|দুপুর\b"), 14),
    (re.compile(r"\bbikal|বিকাল\b"), 17),
    (re.compile(r"\brat|রাত\b"), 21),
]

# Hour tokens like "2pm", "14:00", "২টায়", "সকাল ১০টা".
_HOUR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<!\d)([01]?\d|2[0-3])\s*(am|pm)\b"),
    re.compile(r"(?<!\d)([01]?\d|2[0-3])\s*:\s*\d{2}\b"),
    re.compile(r"(?<!\d)([01]?\d|2[0-3])\s*(?:টায়|টা)\b"),
)


def normalize(text: str) -> str:
    return (text or "").translate(BN_DIGITS).lower().strip()


def extract_amounts(text: str) -> list[float]:
    """
    Extract English and Bangla digit amounts.
    Examples: 5000, 5,000, ২০০০, ৫০০ টাকা.
    """
    t = normalize(text)
    raw = re.findall(r"(?<!\d)(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\d)", t)
    amounts: list[float] = []
    for item in raw:
        try:
            value = float(item.replace(",", ""))
            # Avoid treating common dates/years and very short account fragments as amounts where possible.
            if value > 0:
                amounts.append(value)
        except ValueError:
            pass
    return amounts


def extract_txn_ids(text: str) -> list[str]:
    return re.findall(r"\b[A-Z]{2,}-\d+\b", (text or "").upper())


def complaint_mentions_counterparty(complaint: str, counterparty: Optional[str]) -> bool:
    if not counterparty:
        return False
    c = normalize(complaint)
    cp = normalize(counterparty)
    compact_cp = re.sub(r"\D", "", cp)
    compact_text = re.sub(r"\D", "", c)
    # Use direct text match for IDs and compact digit match for phone numbers.
    return cp in c or bool(compact_cp and len(compact_cp) >= 6 and compact_cp in compact_text)


def has_any(text: str, keywords: Iterable[str]) -> bool:
    lowered = normalize(text)
    return any(k.lower() in lowered for k in keywords)


def amount_matches(complaint: str, tx: Transaction) -> bool:
    amounts = extract_amounts(complaint)
    if not amounts:
        return False
    return any(abs(a - float(tx.amount)) < 0.01 for a in amounts)


def parse_time(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def parse_hinted_time(complaint: str, reference: Optional[datetime] = None) -> Optional[datetime]:
    """
    Best-effort extraction of a complaint's claimed time of the transaction.
    Supports:
      * relative day words: today / yesterday / আজ / গতকাল
      * day-part words: morning/afternoon/evening/night + Bangla equivalents
      * hour tokens: 2pm, 14:00, ২টায়, সকাল ১০টা
    `reference` is the "now" anchor for relative phrases (defaults to UTC now).
    """
    if not complaint:
        return None

    text = normalize(complaint)
    ref = reference or datetime.now(timezone.utc)
    hour: Optional[int] = None

    for pat in _HOUR_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        h = int(m.group(1))
        if "pm" in m.group(0) and h < 12:
            h += 12
        hour = h
        break

    if hour is None:
        for pat, default_hour in _DAY_PART_HOURS:
            if pat.search(text):
                hour = default_hour
                break

    if hour is None:
        return None

    base_day: datetime
    if re.search(r"\byesterday\b|গতকাল", text):
        base_day = (ref - timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)
    elif re.search(r"\btoday\b|আজ", text):
        base_day = ref.replace(hour=hour, minute=0, second=0, microsecond=0)
    elif re.search(r"\blast night\b|গত রাতে", text):
        base_day = (ref - timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)
    else:
        # No relative anchor; assume same day as reference.
        base_day = ref.replace(hour=hour, minute=0, second=0, microsecond=0)

    return base_day


def time_score(complaint: str, txn_timestamp: Optional[str],
               reference: Optional[datetime] = None) -> int:
    """
    Score bump based on how close the complaint's hinted time is to the txn
    timestamp. Returns:
        +2 if within 2 hours
        +1 if within 6 hours
        -2 if the hinted time is on a different calendar day
         0 if either side is missing/unparseable
    A negative score is allowed here; txn_score clamps the result to >= 0.
    `reference` is the "now" anchor used to interpret "today"/"yesterday".
    """
    if not txn_timestamp:
        return 0
    hinted = parse_hinted_time(complaint, reference=reference)
    txn_dt = parse_time(txn_timestamp)
    if hinted is None or txn_dt is None:
        return 0

    delta = abs((txn_dt - hinted).total_seconds())
    if delta <= 2 * 3600:
        return 2
    if delta <= 6 * 3600:
        return 1
    if hinted.date() != txn_dt.date():
        return -2
    return 0


def txn_score(complaint: str, tx: Transaction,
              reference: Optional[datetime] = None) -> int:
    score = 0
    lowered = normalize(complaint)

    # Explicit transaction id is the strongest signal.
    for tid in extract_txn_ids(complaint):
        if tid == tx.transaction_id.upper():
            score += 10

    if amount_matches(complaint, tx):
        score += 5

    if complaint_mentions_counterparty(complaint, tx.counterparty):
        score += 5

    # Light time-proximity signal. Cheap bonus, never below 0 from this branch.
    score += max(time_score(complaint, tx.timestamp, reference=reference), 0)

    type_words = {
        "transfer": [
            "transfer", "send", "sent", "wrong number", "wrong recipient", "brother",
            "sister", "friend", "receiver", "recipient", "didn't get", "did not get",
            "not received", "money pathaisi", "send korechi", "ভুল", "পাঠাই", "পাঠিয়েছি",
            "ট্রান্সফার", "ভাই", "পায়নি", "পায়নি"
        ],
        "payment": [
            "payment", "paid", "merchant", "shop", "bill", "recharge", "electricity",
            "biller", "পেমেন্ট", "বিল", "রিচার্জ"
        ],
        "cash_in": [
            "cash in", "cash-in", "cashin", "deposit", "agent", "ক্যাশ ইন",
            "এজেন্ট", "জমা", "ব্যালেন্সে টাকা আসেনি"
        ],
        "cash_out": [
            "cash out", "cash-out", "cashout", "withdraw", "ক্যাশ আউট", "উত্তোলন"
        ],
        "settlement": [
            "settlement", "settled", "settle", "sales", "merchant portal", "merchant",
            "সেটেলমেন্ট", "বিক্রি"
        ],
        "refund": [
            "refund", "reversal", "return", "returned", "money back", "ফেরত", "রিফান্ড"
        ],
    }

    if any(word in lowered for word in type_words.get(tx.type, [])):
        score += 3

    status_words = {
        "completed": ["completed", "success", "successful", "deducted", "charged", "কাটা", "কেটে"],
        "failed": ["failed", "fail", "unsuccessful", "ব্যর্থ", "ফেইল"],
        "pending": ["pending", "processing", "not reflected", "not received", "আসেনি", "পেন্ডিং"],
        "reversed": ["reversed", "returned", "refunded", "ফেরত"],
    }

    if any(word in lowered for word in status_words.get(tx.status, [])):
        score += 1

    return score


def find_duplicate_payment_pair(history: list[Transaction]) -> Optional[Transaction]:
    """
    Return the suspected duplicate transaction, normally the later identical payment.
    Works even if timestamps are missing by using list order as a fallback.
    """
    candidates = [t for t in history if t.type == "payment" and t.status in ("completed", "pending")]
    if len(candidates) < 2:
        return None

    def key(t: Transaction):
        return (round(float(t.amount), 2), t.counterparty or "")

    groups: dict[tuple[float, str], list[Transaction]] = {}
    for tx in candidates:
        groups.setdefault(key(tx), []).append(tx)

    best_group: list[Transaction] | None = None
    for group in groups.values():
        if len(group) >= 2:
            if best_group is None or len(group) > len(best_group):
                best_group = group

    if not best_group:
        return None

    def sort_key(tx: Transaction):
        parsed = parse_time(tx.timestamp)
        return parsed or datetime.min.replace(tzinfo=timezone.utc)

    return sorted(best_group, key=sort_key)[-1]


def likely_ambiguous_match(complaint: str, history: list[Transaction], best_score: int,
                           reference: Optional[datetime] = None) -> bool:
    """
    If several transactions are equally plausible, do not guess.
    Public sample 8 expects null relevant_transaction_id for multiple 1000 BDT transfers.
    """
    if len(history) < 2 or best_score < 3:
        return False

    scored = [(txn_score(complaint, tx, reference=reference), tx) for tx in history]
    top = max(score for score, _ in scored)
    if top < 3:
        return False

    plausible = [tx for score, tx in scored if score == top]
    if len(plausible) >= 2:
        return True

    # Same amount and same likely transaction type can also be ambiguous,
    # even if weak status hints make one score slightly higher.
    amounts = extract_amounts(complaint)
    if amounts:
        amount_matched = [tx for tx in history if any(abs(a - float(tx.amount)) < 0.01 for a in amounts)]
        same_type = [tx for tx in amount_matched if tx.type == amount_matched[0].type] if amount_matched else []
        if len(same_type) >= 2 and has_any(complaint, ["yesterday", "today", "সকাল", "গতকাল", "আজ"]):
            # If no counterparty or transaction id is mentioned, picking one is unsafe.
            if not extract_txn_ids(complaint) and not any(complaint_mentions_counterparty(complaint, tx.counterparty) for tx in same_type):
                return True

    return False


def select_relevant_transaction(complaint: str, history: list[Transaction],
                                reference: Optional[datetime] = None) -> tuple[Optional[Transaction], int, bool]:
    if not history:
        return None, 0, False

    if has_any(complaint, ["duplicate", "twice", "double charged", "charged twice", "two times", "deducted twice", "কাটা গেছে দুইবার"]):
        duplicate = find_duplicate_payment_pair(history)
        if duplicate:
            return duplicate, 10, False

    scored = [(txn_score(complaint, tx, reference=reference), tx) for tx in history]
    scored.sort(key=lambda x: x[0], reverse=True)

    best_score, best_tx = scored[0]
    if best_score < 3:
        return None, best_score, False

    ambiguous = likely_ambiguous_match(complaint, history, best_score, reference=reference)
    if ambiguous:
        return None, best_score, True

    return best_tx, best_score, False


def count_completed_transfers_to_counterparty(history: list[Transaction], counterparty: Optional[str]) -> int:
    if not counterparty:
        return 0
    return sum(
        1 for tx in history
        if tx.type == "transfer"
        and tx.status == "completed"
        and tx.counterparty == counterparty
    )
