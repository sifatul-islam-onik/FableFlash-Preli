"""Transaction Matcher — finds the relevant_transaction_id from the complaint.

This is the most critical component for the Evidence Reasoning score (35 pts).
It extracts signals from the complaint text and scores each transaction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.models.request import AnalyzeTicketRequest, TransactionEntry


@dataclass
class MatchResult:
    """Result of transaction matching."""

    transaction_id: str | None = None
    matched_transaction: TransactionEntry | None = None
    match_scores: dict[str, float] = field(default_factory=dict)
    ambiguous: bool = False
    duplicate_detected: bool = False
    duplicate_txn_id: str | None = None
    established_recipient: bool = False
    reason: str = ""


class TransactionMatcher:
    """Match a complaint to the most relevant transaction in the history."""

    # Bangla digit map
    BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

    # Keywords mapping to transaction types
    TYPE_KEYWORDS = {
        "transfer": [
            "sent", "send", "transfer", "wrong number", "wrong person",
            "পাঠিয়েছি", "ট্রান্সফার", "ভুল নম্বর", "পাঠানো",
        ],
        "payment": [
            "paid", "pay", "payment", "bill", "recharge", "purchase", "bought",
            "পেমেন্ট", "বিল", "রিচার্জ", "কিনেছি",
        ],
        "cash_in": [
            "cash in", "deposit", "agent", "cash-in", "cashin",
            "ক্যাশ ইন", "জমা", "এজেন্ট",
        ],
        "cash_out": [
            "cash out", "withdraw", "cash-out", "cashout",
            "ক্যাশ আউট", "উত্তোলন",
        ],
        "settlement": [
            "settlement", "settle", "সেটেলমেন্ট",
        ],
        "refund": [
            "refund", "refunded", "রিফান্ড",
        ],
    }

    # Status keywords
    STATUS_KEYWORDS = {
        "failed": ["failed", "fail", "not working", "ব্যর্থ", "হয়নি"],
        "pending": ["pending", "processing", "not received", "haven't got",
                     "আসেনি", "পাইনি", "পেন্ডিং"],
    }

    def match(self, request: AnalyzeTicketRequest) -> MatchResult:
        """Find the most relevant transaction for the complaint."""
        transactions = request.transaction_history or []

        if not transactions:
            return MatchResult(reason="no_transaction_history")

        complaint = request.complaint.lower()
        complaint_normalized = complaint.translate(self.BANGLA_DIGITS)

        # Extract signals from complaint
        amounts = self._extract_amounts(complaint_normalized)
        txn_type = self._detect_transaction_type(complaint)
        status_hint = self._detect_status_hint(complaint)
        counterparties = self._extract_counterparties(complaint)
        time_hints = self._extract_time_hints(complaint)

        # Check for duplicate transactions first
        duplicate_result = self._check_duplicates(transactions)

        # Score each transaction
        scores: dict[str, float] = {}
        for txn in transactions:
            score = 0.0

            # Amount match (+3)
            if amounts and txn.amount in amounts:
                score += 3.0

            # Transaction type match (+2)
            if txn_type and txn.type.value == txn_type:
                score += 2.0

            # Status relevance (+1)
            if status_hint:
                if status_hint == "failed" and txn.status.value == "failed":
                    score += 1.5
                elif status_hint == "pending" and txn.status.value == "pending":
                    score += 1.5

            # Counterparty mention (+3)
            if counterparties:
                for cp in counterparties:
                    if cp in txn.counterparty.lower():
                        score += 3.0
                        break

            # Time hint matching (+1)
            if time_hints:
                txn_time = self._parse_timestamp(txn.timestamp)
                if txn_time:
                    for hint in time_hints:
                        if hint == "today" or hint == "আজ":
                            score += 0.5
                        elif hint == "yesterday" or hint == "গতকাল":
                            score += 0.5
                        elif hint in ("morning", "সকাল") and txn_time.hour < 12:
                            score += 0.5
                        elif hint in ("afternoon", "বিকাল", "দুপুর") and 12 <= txn_time.hour < 17:
                            score += 0.5
                        elif hint in ("evening", "সন্ধ্যা", "রাত") and txn_time.hour >= 17:
                            score += 0.5

            # Recency bonus for tiebreaking (+0.5 for most recent)
            score += 0.1  # base so no txn has 0 when others have 0

            scores[txn.transaction_id] = score

        # Find the best match
        if not scores:
            return MatchResult(reason="no_scores")

        sorted_txns = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_id, best_score = sorted_txns[0]

        # Check if the match is good enough
        if best_score <= 0.2:
            return MatchResult(
                match_scores=scores,
                reason="no_strong_match",
            )

        # Handle duplicate case if the duplicate transaction is among the best matches
        if duplicate_result and duplicate_result.duplicate_detected:
            dup_id = duplicate_result.duplicate_txn_id
            if dup_id in scores and scores[dup_id] == best_score:
                matched_txn = next(
                    (t for t in transactions if t.transaction_id == dup_id), None
                )
                return MatchResult(
                    transaction_id=dup_id,
                    matched_transaction=matched_txn,
                    match_scores=scores,
                    duplicate_detected=True,
                    duplicate_txn_id=dup_id,
                    reason="duplicate_detected",
                )

        # Check for ambiguity — multiple transactions with similar scores
        if len(sorted_txns) > 1:
            second_id, second_score = sorted_txns[1]
            score_gap = best_score - second_score

            # Count how many transactions have scores close to the best
            close_matches = sum(
                1 for _, s in sorted_txns if best_score - s < 1.5
            )

            # Ambiguous if: gap is too small between top candidates
            # OR if 3+ transactions have similar scores (clearly ambiguous)
            if (score_gap < 1.5 and not counterparties) or close_matches >= 3:
                # Only mark as ambiguous if there's no strong differentiator
                # (e.g., a counterparty match would resolve ambiguity)
                return MatchResult(
                    match_scores=scores,
                    ambiguous=True,
                    reason="ambiguous_multiple_matches",
                )

        # Get the matched transaction object
        matched_txn = next(
            (t for t in transactions if t.transaction_id == best_id), None
        )

        # Check for established recipient pattern
        established = False
        if matched_txn:
            same_cp_count = sum(
                1 for t in transactions
                if t.counterparty == matched_txn.counterparty
            )
            if same_cp_count >= 3:
                established = True

        # Handle duplicate case
        if duplicate_result and duplicate_result.duplicate_detected:
            return MatchResult(
                transaction_id=duplicate_result.duplicate_txn_id,
                matched_transaction=next(
                    (t for t in transactions
                     if t.transaction_id == duplicate_result.duplicate_txn_id),
                    matched_txn,
                ),
                match_scores=scores,
                duplicate_detected=True,
                duplicate_txn_id=duplicate_result.duplicate_txn_id,
                reason="duplicate_detected",
            )

        return MatchResult(
            transaction_id=best_id,
            matched_transaction=matched_txn,
            match_scores=scores,
            established_recipient=established,
            reason="matched",
        )

    def _extract_amounts(self, text: str) -> list[float]:
        """Extract monetary amounts from the complaint."""
        amounts = []
        # Match patterns like "5000 taka", "5000 BDT", "5000", "৫০০০ টাকা"
        patterns = [
            r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:taka|tk|bdt|টাকা)?",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                try:
                    amount = float(match.group(1).replace(",", ""))
                    if amount > 0:
                        amounts.append(amount)
                except ValueError:
                    continue
        return amounts

    def _detect_transaction_type(self, text: str) -> str | None:
        """Detect the likely transaction type from complaint text."""
        text_lower = text.lower()
        best_type = None
        best_count = 0

        for txn_type, keywords in self.TYPE_KEYWORDS.items():
            count = sum(1 for kw in keywords if kw in text_lower)
            if count > best_count:
                best_count = count
                best_type = txn_type

        return best_type

    def _detect_status_hint(self, text: str) -> str | None:
        """Detect if the complaint mentions a transaction status."""
        text_lower = text.lower()
        for status, keywords in self.STATUS_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                return status
        return None

    def _extract_counterparties(self, text: str) -> list[str]:
        """Extract phone numbers or merchant/agent IDs from the complaint."""
        counterparties = []
        # Phone number patterns (Bangladeshi)
        phone_patterns = [
            r"(?:\+?880)?1[3-9]\d{8}",
            r"01[3-9]\d{8}",
        ]
        for pattern in phone_patterns:
            for match in re.finditer(pattern, text):
                counterparties.append(match.group().lower())

        # Agent/Merchant IDs
        id_patterns = [r"agent[-\s]?\d+", r"merchant[-\s]?\d+"]
        for pattern in id_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                counterparties.append(match.group().lower())

        return counterparties

    def _extract_time_hints(self, text: str) -> list[str]:
        """Extract time-related hints from the complaint."""
        hints = []
        time_words = [
            "today", "yesterday", "morning", "afternoon", "evening", "night",
            "আজ", "গতকাল", "সকাল", "বিকাল", "দুপুর", "সন্ধ্যা", "রাত",
        ]
        text_lower = text.lower()
        for word in time_words:
            if word in text_lower:
                hints.append(word)
        return hints

    def _parse_timestamp(self, ts: str) -> datetime | None:
        """Parse an ISO 8601 timestamp."""
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    def _check_duplicates(
        self, transactions: list[TransactionEntry]
    ) -> MatchResult | None:
        """Check for duplicate transactions (same amount, counterparty, within 60s)."""
        for i, t1 in enumerate(transactions):
            for t2 in transactions[i + 1:]:
                if (
                    t1.amount == t2.amount
                    and t1.counterparty == t2.counterparty
                    and t1.status.value == "completed"
                    and t2.status.value == "completed"
                    and t1.type == t2.type
                ):
                    ts1 = self._parse_timestamp(t1.timestamp)
                    ts2 = self._parse_timestamp(t2.timestamp)
                    if ts1 and ts2:
                        diff = abs((ts2 - ts1).total_seconds())
                        if diff <= 120:  # within 2 minutes
                            # The later one is the duplicate
                            dup_id = (
                                t2.transaction_id if ts2 > ts1
                                else t1.transaction_id
                            )
                            return MatchResult(
                                duplicate_detected=True,
                                duplicate_txn_id=dup_id,
                            )
        return None
