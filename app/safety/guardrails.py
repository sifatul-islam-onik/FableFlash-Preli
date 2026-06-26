"""Safety guardrails — the last line of defense.

Applied to ALL responses (LLM and fallback) to catch and fix
unsafe content before it reaches the customer.

These checks prevent the three penalty types:
- Asking for PIN/OTP/password (-15 pts)
- Confirming refund/reversal without authority (-10 pts)
- Directing to suspicious third parties (-10 pts)
"""

from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)


class SafetyGuardrails:
    """Post-processing safety checks and sanitization."""

    # --- Credential request patterns (-15 pts) ---
    # These must NOT match safe warnings like "do not share your PIN or OTP"
    # We use negative lookbehind to exclude "not " / "never " / "don't " / "না "
    _SAFE_PREFIX = r"(?<!not\s)(?<!never\s)(?<!don't\s)(?<!না\s)(?<!do\s)"

    CREDENTIAL_PATTERNS = [
        # English patterns — requesting credentials
        _SAFE_PREFIX + r"(?:share|provide|send|give|enter|type|input|confirm|verify)\s+(?:your\s+)?(?:pin|otp|password|passcode|secret\s+code|card\s+number|full\s+card)",
        r"what\s+is\s+your\s+(?:pin|otp|password|passcode)",
        r"(?:need|require)\s+your\s+(?:pin|otp|password|passcode)",
        _SAFE_PREFIX + r"please\s+(?:share|provide|send|give)\s+(?:the\s+)?(?:pin|otp|password)",
        r"(?:enter|type)\s+(?:the\s+)?(?:otp|pin|password)\s+(?:here|below|now)",
        # Patterns that specifically ASK for info (not warn against)
        r"(?:can\s+you|could\s+you|kindly)\s+(?:share|provide|send|give)\s+(?:your\s+)?(?:pin|otp|password)",
        r"(?:we\s+need|i\s+need)\s+your\s+(?:pin|otp|password)",
        r"(?:for\s+verification|to\s+verify).*(?:share|provide|send|give)\s+(?:your\s+)?(?:pin|otp|password)",
        # Bangla patterns — requesting credentials
        r"(?:আপনার|তোমার)\s+(?:পিন|ওটিপি|পাসওয়ার্ড)\s+(?:দিন|জানান|শেয়ার করুন|পাঠান)",
    ]

    # --- Unauthorized action patterns (-10 pts) ---
    UNAUTHORIZED_ACTION_PATTERNS = [
        # Confirming refund
        r"(?:we\s+will|we\s+have|we\'ve|we\s+shall)\s+(?:refund|reverse|return|credit|restore|send\s+back)\s+(?:your|the)?",
        r"we\s+(?:are\s+)?(?:refunding|reversing|returning|crediting|sending\s+back)",
        r"we\s+(?:will|have|are|shall)\s+(?:initiate|process|send|issue|approve|give)\s+(?:a\s+)?(?:refund|reversal|credit)",
        r"(?:your\s+)?(?:money|amount|fund|balance)\s+(?:will\s+be|has\s+been|is\s+being|was)\s+(?:refund|return|reverse|credit|restore|sent\s+back)",
        r"(?:refund|reversal|recovery|unblock)\s+(?:has\s+been|will\s+be|is|was|being)\s+(?:process|initiat|complet|approv|done|execut|credited)",
        # Confirming account unblock
        r"(?:account|your\s+account)\s+(?:has\s+been|will\s+be|is|was)\s+(?:unblock|unlock|restor|reactivat)",
        # Direct promise language
        r"(?:you\s+will|you\'ll)\s+(?:get|receive)\s+(?:your\s+)?(?:money|refund|amount|fund)\s+(?:back|soon|shortly)",
    ]

    # --- Third party referral patterns (-10 pts) ---
    THIRD_PARTY_PATTERNS = [
        r"(?:contact|call|reach|visit|go\s+to)\s+(?:this|the\s+following|these)\s+(?:number|phone|website|link|url|person|agent)",
        r"(?:http|https|www\.)\S+(?:\.com|\.net|\.org|\.xyz|\.io)",
        # Suspicious phone number patterns (non-official)
        r"call\s+\+?\d{10,}",
    ]

    # Safe replacement for credential requests
    SAFE_CREDENTIAL_REPLY_EN = (
        "Please do not share your PIN or OTP with anyone."
    )
    SAFE_CREDENTIAL_REPLY_BN = (
        "অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"
    )

    # Safe replacement for unauthorized actions
    SAFE_REFUND_LANGUAGE_EN = (
        "any eligible amount will be returned through official channels"
    )
    SAFE_REFUND_LANGUAGE_BN = (
        "যোগ্য পরিমাণ অফিসিয়াল চ্যানেলে ফেরত দেওয়া হবে"
    )

    def check_and_sanitize(
        self,
        customer_reply: str,
        recommended_next_action: str,
        agent_summary: str,
        language: str | None = None,
    ) -> dict:
        """Check all text fields for safety violations and sanitize.

        Returns dict with sanitized versions and a list of violations found.
        """
        violations: list[str] = []

        # Check and sanitize customer_reply
        sanitized_reply = customer_reply
        sanitized_reply, reply_violations = self._check_credential_requests(
            sanitized_reply, language
        )
        violations.extend(reply_violations)

        sanitized_reply, action_violations = self._check_unauthorized_actions(
            sanitized_reply, language
        )
        violations.extend(action_violations)

        sanitized_reply, tp_violations = self._check_third_party_referrals(
            sanitized_reply
        )
        violations.extend(tp_violations)

        # Check recommended_next_action for unauthorized actions
        sanitized_action = recommended_next_action
        sanitized_action, na_violations = self._check_unauthorized_actions(
            sanitized_action, language
        )
        violations.extend(
            [f"next_action:{v}" for v in na_violations]
        )

        # Ensure the safety reminder is present in customer_reply
        sanitized_reply = self._ensure_safety_reminder(
            sanitized_reply, language
        )

        # Clean newlines and collapse spaces from all fields
        sanitized_reply = self._clean_newlines(sanitized_reply)
        sanitized_action = self._clean_newlines(sanitized_action)
        sanitized_summary = self._clean_newlines(agent_summary)

        if violations:
            logger.warning(f"Safety violations detected and fixed: {violations}")

        return {
            "customer_reply": sanitized_reply,
            "recommended_next_action": sanitized_action,
            "agent_summary": sanitized_summary,
            "violations": violations,
        }

    def _clean_newlines(self, text: str) -> str:
        """Replace actual and literal newlines with space, and collapse spaces."""
        if not text:
            return ""
        # Replace literal '\n' string representations
        text = text.replace("\\n", " ").replace("\\r", " ")
        # Replace actual newline/carriage return characters
        text = text.replace("\n", " ").replace("\r", " ")
        # Collapse multiple spaces
        text = re.sub(r"\s+", " ", text).strip()
        # Collapse safety substitution duplicate phrases/words
        text = re.sub(r"\b(any\s+eligible)\s+\1\b", r"\1", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(any)\s+\1\b", r"\1", text, flags=re.IGNORECASE)
        return text

    def _check_credential_requests(
        self, text: str, language: str | None
    ) -> tuple[str, list[str]]:
        """Check for and remove credential request patterns."""
        violations = []
        for pattern in self.CREDENTIAL_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                violations.append("credential_request")
                # Replace the offending sentence
                text = re.sub(
                    pattern + r"[^.!?\n]*[.!?\n]?",
                    self.SAFE_CREDENTIAL_REPLY_BN
                    if language == "bn"
                    else self.SAFE_CREDENTIAL_REPLY_EN,
                    text,
                    flags=re.IGNORECASE,
                )
        return text, violations

    def _check_unauthorized_actions(
        self, text: str, language: str | None
    ) -> tuple[str, list[str]]:
        """Check for and replace unauthorized refund/reversal promises."""
        violations = []
        for pattern in self.UNAUTHORIZED_ACTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                violations.append("unauthorized_action")
                # Replace the offending phrase with safe language
                text = re.sub(
                    pattern + r"[^.!?\n]*",
                    self.SAFE_REFUND_LANGUAGE_BN
                    if language == "bn"
                    else self.SAFE_REFUND_LANGUAGE_EN,
                    text,
                    flags=re.IGNORECASE,
                )
        return text, violations

    def _check_third_party_referrals(
        self, text: str
    ) -> tuple[str, list[str]]:
        """Check for and remove third-party referral patterns."""
        violations = []
        for pattern in self.THIRD_PARTY_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                violations.append("third_party_referral")
                text = re.sub(
                    pattern + r"[^.!?\n]*[.!?\n]?",
                    "Please contact us through official support channels.",
                    text,
                    flags=re.IGNORECASE,
                )
        return text, violations

    def _ensure_safety_reminder(
        self, text: str, language: str | None
    ) -> str:
        """Ensure the customer reply contains the PIN/OTP safety reminder."""
        if language == "bn":
            reminder = self.SAFE_CREDENTIAL_REPLY_BN
            check_words = ["পিন", "ওটিপি"]
        else:
            reminder = self.SAFE_CREDENTIAL_REPLY_EN
            check_words = ["pin", "otp"]

        text_lower = text.lower()
        # Check if the reminder (or equivalent) is already present
        has_reminder = all(
            word.lower() in text_lower for word in check_words
        )

        if not has_reminder:
            text = text.rstrip()
            if not text.endswith("."):
                text += "."
            text += " " + reminder

        return text
