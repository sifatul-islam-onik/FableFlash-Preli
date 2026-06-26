"""Evidence Analyzer — determines if the complaint is consistent with transaction data."""

from __future__ import annotations

from app.core.transaction_matcher import MatchResult
from app.models.request import AnalyzeTicketRequest
from app.models.response import EvidenceVerdict


class EvidenceAnalyzer:
    """Analyze whether transaction evidence supports or contradicts the complaint."""

    def analyze(
        self,
        request: AnalyzeTicketRequest,
        match_result: MatchResult,
    ) -> EvidenceVerdict:
        """Determine the evidence verdict."""
        transactions = request.transaction_history or []

        # No transactions at all → insufficient data
        if not transactions:
            return EvidenceVerdict.INSUFFICIENT_DATA

        # Ambiguous match → insufficient data
        if match_result.ambiguous:
            return EvidenceVerdict.INSUFFICIENT_DATA

        # No strong match found → insufficient data
        if match_result.transaction_id is None:
            return EvidenceVerdict.INSUFFICIENT_DATA

        matched_txn = match_result.matched_transaction
        if matched_txn is None:
            return EvidenceVerdict.INSUFFICIENT_DATA

        # Check for inconsistency patterns
        if self._check_inconsistency(request, match_result, transactions):
            return EvidenceVerdict.INCONSISTENT

        # If we have a match and no inconsistency → consistent
        return EvidenceVerdict.CONSISTENT

    def _check_inconsistency(
        self,
        request: AnalyzeTicketRequest,
        match_result: MatchResult,
        transactions: list,
    ) -> bool:
        """Check if evidence contradicts the complaint."""
        complaint = request.complaint.lower()
        matched_txn = match_result.matched_transaction

        if not matched_txn:
            return False

        # Pattern 1: Claims "wrong transfer" but has established recipient
        # (3+ transfers to same counterparty)
        if match_result.established_recipient:
            wrong_transfer_keywords = [
                "wrong", "mistake", "accident", "ভুল", "accidentally",
            ]
            if any(kw in complaint for kw in wrong_transfer_keywords):
                return True

        # Pattern 2: Claims amount X but no transaction of amount X exists
        # (handled by matcher returning None, so this is a secondary check)

        # Pattern 3: Claims transaction failed but it shows as completed
        failed_keywords = ["failed", "not working", "ব্যর্থ", "হয়নি"]
        if any(kw in complaint for kw in failed_keywords):
            if matched_txn.status.value == "completed":
                # Complaint says failed but txn is completed — could be
                # inconsistent, but only if they also mention balance deducted
                # If balance deducted + failed status = consistent
                balance_keywords = ["balance", "deducted", "cut", "কেটে", "ব্যালেন্স"]
                if not any(bk in complaint for bk in balance_keywords):
                    return True

        return False
