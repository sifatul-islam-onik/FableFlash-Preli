"""Escalation Decider — determines if human review is required."""

from __future__ import annotations

from app.models.response import CaseType, EvidenceVerdict, Severity


class EscalationDecider:
    """Decide whether a case requires human review."""

    def should_escalate(
        self,
        case_type: CaseType,
        severity: Severity,
        evidence_verdict: EvidenceVerdict,
        confidence: float,
        duplicate_detected: bool = False,
        has_pending_txn: bool = False,
    ) -> bool:
        """Return True if the case needs human review."""
        # Always escalate phishing/social engineering
        if case_type == CaseType.PHISHING_OR_SOCIAL_ENGINEERING:
            return True

        # Escalate wrong transfers (if we have enough data to initiate dispute or investigate inconsistency)
        if case_type == CaseType.WRONG_TRANSFER and evidence_verdict != EvidenceVerdict.INSUFFICIENT_DATA:
            return True

        # Escalate inconsistent evidence
        if evidence_verdict == EvidenceVerdict.INCONSISTENT:
            return True

        # Escalate critical severity
        if severity == Severity.CRITICAL:
            return True

        # Escalate duplicate payments (need biller verification)
        if duplicate_detected or case_type == CaseType.DUPLICATE_PAYMENT:
            return True

        # Escalate pending agent cash-in issues
        if case_type == CaseType.AGENT_CASH_IN_ISSUE and has_pending_txn:
            return True

        # Escalate low confidence (only if evidence is not insufficient_data)
        if confidence < 0.7 and evidence_verdict != EvidenceVerdict.INSUFFICIENT_DATA:
            return True

        return False
