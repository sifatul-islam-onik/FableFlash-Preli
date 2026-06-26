"""Severity Scorer — determines the severity level of a case."""

from __future__ import annotations

import re
from app.core.transaction_matcher import MatchResult
from app.models.request import AnalyzeTicketRequest
from app.models.response import CaseType, EvidenceVerdict, Severity


class SeverityScorer:
    """Score the severity of a case based on type, evidence, and amount."""

    # Amount threshold for "high value" (BDT)
    HIGH_VALUE_THRESHOLD = 5000.0

    def score(
        self,
        request: AnalyzeTicketRequest,
        case_type: CaseType,
        evidence_verdict: EvidenceVerdict,
        match_result: MatchResult,
    ) -> Severity:
        """Determine severity level."""
        # 1. Critical: reserved exclusively for phishing/social engineering
        if case_type == CaseType.PHISHING_OR_SOCIAL_ENGINEERING:
            return Severity.CRITICAL

        # 2. High: default for any financially material dispute where the evidence is consistent:
        # - wrong transfers (consistent)
        # - duplicate payments
        # - failed payments with deducted balance
        # - pending cash-ins (agent_cash_in_issue and pending status)
        # - also any high value transactions
        if evidence_verdict == EvidenceVerdict.CONSISTENT:
            if case_type == CaseType.WRONG_TRANSFER:
                return Severity.HIGH
            if case_type == CaseType.PAYMENT_FAILED:
                return Severity.HIGH
            if case_type == CaseType.AGENT_CASH_IN_ISSUE:
                if match_result.matched_transaction and match_result.matched_transaction.status.value == "pending":
                    return Severity.HIGH

        if case_type == CaseType.DUPLICATE_PAYMENT:
            return Severity.HIGH

        # Fallback check for balance deduction mentions in payment failed cases
        if case_type == CaseType.PAYMENT_FAILED and self._mentions_balance_deduction(request.complaint):
            return Severity.HIGH

        # Also trigger high severity on high value transaction dispute
        if (
            match_result.matched_transaction
            and match_result.matched_transaction.amount >= self.HIGH_VALUE_THRESHOLD
            and case_type in (CaseType.WRONG_TRANSFER, CaseType.PAYMENT_FAILED)
        ):
            return Severity.HIGH

        # 3. Medium: claim is weakened by inconsistent evidence or the issue is process-related
        # - inconsistent evidence (evidence_verdict == inconsistent)
        # - process-related issues (merchant_settlement_delay)
        # - ambiguous matches
        # - agent cash-in issues that are not pending
        if (
            evidence_verdict == EvidenceVerdict.INCONSISTENT
            or case_type == CaseType.MERCHANT_SETTLEMENT_DELAY
            or match_result.ambiguous
            or case_type == CaseType.AGENT_CASH_IN_ISSUE
        ):
            return Severity.MEDIUM

        # 4. Low: voluntary refund requests and vague/unclassifiable complaints
        return Severity.LOW

    def _mentions_balance_deduction(self, complaint: str) -> bool:
        """Check if the complaint mentions unexpected balance deduction."""
        complaint_lower = complaint.lower()
        patterns = [
            r"balance.*deduct",
            r"deduct.*balance",
            r"money.*deduct",
            r"deduct.*money",
            r"balance.*cut",
            r"cut.*balance",
            r"charge.*but",
            r"কেটে গেছে",
            r"ব্যালেন্স কমে গেছে",
            r"টাকা কেটেছে",
        ]
        return any(re.search(p, complaint_lower) for p in patterns)
