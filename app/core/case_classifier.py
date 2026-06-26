"""Case Classifier — determines case_type and department from the complaint."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.transaction_matcher import MatchResult
from app.models.request import AnalyzeTicketRequest
from app.models.response import CaseType, Department


@dataclass
class ClassificationResult:
    case_type: CaseType
    department: Department
    reason_codes: list[str]


class CaseClassifier:
    """Classify the complaint into a case type and route to department."""

    # Keyword groups for classification (English + Bangla)
    # ORDER MATTERS: more specific patterns must come before general ones
    CASE_TYPE_RULES: list[tuple[CaseType, list[str]]] = [
        (CaseType.PHISHING_OR_SOCIAL_ENGINEERING, [
            "otp", "pin", "scam", "phishing", "fraud", "suspicious call",
            "suspicious sms", "someone called", "asking for otp",
            "asking for pin", "asking for password", "pretending",
            "fake call", "hack", "hacked", "unauthorized",
            "ওটিপি", "পিন", "প্রতারণা", "ফোন করে", "হ্যাক",
            "সন্দেহজনক", "জালিয়াতি",
        ]),
        (CaseType.DUPLICATE_PAYMENT, [
            "duplicate", "twice", "double", "two times", "charged twice",
            "deducted twice", "paid twice", "double charge",
            "দুইবার", "ডাবল", "ডুপ্লিকেট",
        ]),
        (CaseType.AGENT_CASH_IN_ISSUE, [
            "agent cash in", "cash in", "agent deposit", "cashin",
            "agent didn't", "agent did not", "agent says",
            "ক্যাশ ইন", "এজেন্ট", "জমা",
        ]),
        (CaseType.MERCHANT_SETTLEMENT_DELAY, [
            "settlement", "settle", "merchant settlement",
            "sales not settled", "settlement delay",
            "সেটেলমেন্ট", "মার্চেন্ট",
        ]),
        (CaseType.WRONG_TRANSFER, [
            "wrong number", "wrong person", "wrong transfer",
            "wrong recipient", "sent to wrong", "mistake transfer",
            "accidentally sent", "accidental transfer",
            "ভুল নম্বর", "ভুল ট্রান্সফার", "ভুলে পাঠিয়েছি",
        ]),
        # PAYMENT_FAILED must come BEFORE REFUND_REQUEST because
        # "failed payment + please refund" should be payment_failed, not refund_request
        (CaseType.PAYMENT_FAILED, [
            "payment failed", "failed payment", "transaction failed",
            "showed failed", "app showed failed", "failed",
            "not completed", "balance deducted", "deducted but",
            "money deducted", "cut but", "charged but",
            "balance was deducted", "my balance was",
            "পেমেন্ট ব্যর্থ", "টাকা কেটেছে", "ব্যর্থ",
        ]),
        (CaseType.REFUND_REQUEST, [
            "refund", "money back", "return my money", "get my money",
            "want my money", "give back", "changed my mind",
            "রিফান্ড", "টাকা ফেরত", "ফেরত দিন",
        ]),
    ]

    # Department mapping for each case type
    DEPARTMENT_MAP: dict[CaseType, Department] = {
        CaseType.WRONG_TRANSFER: Department.DISPUTE_RESOLUTION,
        CaseType.PAYMENT_FAILED: Department.PAYMENTS_OPS,
        CaseType.REFUND_REQUEST: Department.CUSTOMER_SUPPORT,
        CaseType.DUPLICATE_PAYMENT: Department.PAYMENTS_OPS,
        CaseType.MERCHANT_SETTLEMENT_DELAY: Department.MERCHANT_OPERATIONS,
        CaseType.AGENT_CASH_IN_ISSUE: Department.AGENT_OPERATIONS,
        CaseType.PHISHING_OR_SOCIAL_ENGINEERING: Department.FRAUD_RISK,
        CaseType.OTHER: Department.CUSTOMER_SUPPORT,
    }

    def classify(
        self,
        request: AnalyzeTicketRequest,
        match_result: MatchResult,
    ) -> ClassificationResult:
        """Classify the complaint into case_type and department."""
        complaint = request.complaint.lower()
        reason_codes: list[str] = []

        # Try keyword matching in priority order
        case_type = CaseType.OTHER
        for ct, keywords in self.CASE_TYPE_RULES:
            if any(kw in complaint for kw in keywords):
                case_type = ct
                reason_codes.append(ct.value)
                break

        # Special refinement for personal transfer issues (wrong_transfer)
        if case_type == CaseType.OTHER:
            is_transfer_context = (
                "sent" in complaint
                or "transfer" in complaint
                or "brother" in complaint
                or "friend" in complaint
                or "sister" in complaint
                or "parent" in complaint
                or "father" in complaint
                or "mother" in complaint
                or "ভাই" in complaint
                or "বোন" in complaint
                or "বন্ধু" in complaint
                or "পাঠিয়েছি" in complaint
                or "পাঠানো" in complaint
                or (match_result.matched_transaction and match_result.matched_transaction.type.value == "transfer")
            )
            is_not_received_context = (
                "didn't get" in complaint
                or "not received" in complaint
                or "did not get" in complaint
                or "didn't receive" in complaint
                or "did not receive" in complaint
                or "says he" in complaint
                or "says she" in complaint
                or "পায়নি" in complaint
                or "পায় নাই" in complaint
                or "আসেনি" in complaint
                or "আসে নাই" in complaint
            )
            if is_transfer_context and is_not_received_context:
                case_type = CaseType.WRONG_TRANSFER
                reason_codes.append(CaseType.WRONG_TRANSFER.value)

        # Override based on transaction evidence
        if match_result.duplicate_detected:
            case_type = CaseType.DUPLICATE_PAYMENT
            reason_codes = ["duplicate_payment", "duplicate_detected"]

        # Refine department based on user_type
        department = self.DEPARTMENT_MAP.get(case_type, Department.CUSTOMER_SUPPORT)

        if request.user_type and request.user_type.value == "merchant":
            if case_type in (CaseType.REFUND_REQUEST, CaseType.OTHER):
                department = Department.MERCHANT_OPERATIONS

        # Refine: contested refund goes to dispute resolution
        if case_type == CaseType.REFUND_REQUEST:
            contested_keywords = ["wrong", "unauthorized", "didn't order", "fraud"]
            if any(kw in complaint for kw in contested_keywords):
                department = Department.DISPUTE_RESOLUTION
                reason_codes.append("contested_refund")

        # Add match-related reason codes
        if match_result.transaction_id:
            reason_codes.append("transaction_match")
        if match_result.established_recipient:
            reason_codes.append("established_recipient_pattern")
        if match_result.ambiguous:
            reason_codes.append("ambiguous_match")
            reason_codes.append("needs_clarification")

        return ClassificationResult(
            case_type=case_type,
            department=department,
            reason_codes=reason_codes,
        )
