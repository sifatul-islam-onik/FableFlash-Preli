"""Request models matching Section 5 of the problem statement."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# --- Enums for request fields ---

class TransactionType(str, Enum):
    TRANSFER = "transfer"
    PAYMENT = "payment"
    CASH_IN = "cash_in"
    CASH_OUT = "cash_out"
    SETTLEMENT = "settlement"
    REFUND = "refund"


class TransactionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    PENDING = "pending"
    REVERSED = "reversed"


class Language(str, Enum):
    EN = "en"
    BN = "bn"
    MIXED = "mixed"


class Channel(str, Enum):
    IN_APP_CHAT = "in_app_chat"
    CALL_CENTER = "call_center"
    EMAIL = "email"
    MERCHANT_PORTAL = "merchant_portal"
    FIELD_AGENT = "field_agent"


class UserType(str, Enum):
    CUSTOMER = "customer"
    MERCHANT = "merchant"
    AGENT = "agent"
    UNKNOWN = "unknown"


# --- Models ---

class TransactionEntry(BaseModel):
    """A single transaction from the customer's recent history."""

    transaction_id: str
    timestamp: str  # ISO 8601
    type: TransactionType
    amount: float
    counterparty: str
    status: TransactionStatus


class AnalyzeTicketRequest(BaseModel):
    """Request body for POST /analyze-ticket."""

    ticket_id: str
    complaint: str
    language: Optional[Language] = None
    channel: Optional[Channel] = None
    user_type: Optional[UserType] = None
    campaign_context: Optional[str] = None
    transaction_history: Optional[list[TransactionEntry]] = Field(default_factory=list)
    metadata: Optional[dict[str, Any]] = None

    @field_validator("complaint")
    @classmethod
    def complaint_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("complaint must not be empty")
        return v
