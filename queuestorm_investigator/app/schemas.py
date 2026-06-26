from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


Language = Literal["en", "bn", "mixed"]
Channel = Literal["in_app_chat", "call_center", "email", "merchant_portal", "field_agent"]
UserType = Literal["customer", "merchant", "agent", "unknown"]

TxnType = Literal["transfer", "payment", "cash_in", "cash_out", "settlement", "refund"]
TxnStatus = Literal["completed", "failed", "pending", "reversed"]

EvidenceVerdict = Literal["consistent", "inconsistent", "insufficient_data"]
CaseType = Literal[
    "wrong_transfer",
    "payment_failed",
    "refund_request",
    "duplicate_payment",
    "merchant_settlement_delay",
    "agent_cash_in_issue",
    "phishing_or_social_engineering",
    "other",
]
Severity = Literal["low", "medium", "high", "critical"]
Department = Literal[
    "customer_support",
    "dispute_resolution",
    "payments_ops",
    "merchant_operations",
    "agent_operations",
    "fraud_risk",
]


class Transaction(BaseModel):
    transaction_id: str
    timestamp: Optional[str] = None
    type: TxnType
    amount: float
    counterparty: Optional[str] = None
    status: TxnStatus


class AnalyzeTicketRequest(BaseModel):
    ticket_id: str
    complaint: str
    language: Optional[Language] = "en"
    channel: Optional[Channel] = "in_app_chat"
    user_type: Optional[UserType] = "unknown"
    campaign_context: Optional[str] = None
    transaction_history: Optional[List[Transaction]] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

    @field_validator("complaint")
    @classmethod
    def complaint_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("complaint must not be empty")
        return value.strip()

    @field_validator("ticket_id")
    @classmethod
    def ticket_id_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("ticket_id must not be empty")
        return value.strip()


class AnalyzeTicketResponse(BaseModel):
    ticket_id: str
    relevant_transaction_id: Optional[str]
    evidence_verdict: EvidenceVerdict
    case_type: CaseType
    severity: Severity
    department: Department
    agent_summary: str
    recommended_next_action: str
    customer_reply: str
    human_review_required: bool
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    reason_codes: Optional[List[str]] = Field(default_factory=list)
