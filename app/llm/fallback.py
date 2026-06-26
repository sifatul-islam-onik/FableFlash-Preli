"""Rule-based fallback for text generation when LLM is unavailable.

Generates deterministic, safe text fields using templates.
"""

from __future__ import annotations

from app.models.response import CaseType, Department, EvidenceVerdict


class FallbackGenerator:
    """Generate agent_summary, recommended_next_action, customer_reply
    using templates when the LLM is unavailable."""

    # --- Agent summary templates ---
    SUMMARY_TEMPLATES = {
        CaseType.WRONG_TRANSFER: (
            "Customer reports sending {amount} BDT via {txn_id} to "
            "{counterparty}, claiming it was sent to the wrong recipient."
        ),
        CaseType.PAYMENT_FAILED: (
            "Customer reports a failed payment of {amount} BDT ({txn_id}) "
            "with potential balance deduction. Requires investigation."
        ),
        CaseType.REFUND_REQUEST: (
            "Customer requests refund of {amount} BDT for {txn_id}. "
            "Not a service failure — customer-initiated refund request."
        ),
        CaseType.DUPLICATE_PAYMENT: (
            "Customer reports duplicate payment. Two identical transactions of "
            "{amount} BDT detected within a short time window. "
            "The suspected duplicate is {txn_id}."
        ),
        CaseType.MERCHANT_SETTLEMENT_DELAY: (
            "Merchant reports settlement of {amount} BDT ({txn_id}) is delayed "
            "beyond the expected window. Settlement status is pending."
        ),
        CaseType.AGENT_CASH_IN_ISSUE: (
            "Customer reports {amount} BDT cash-in via agent ({txn_id}) "
            "not reflected in balance. Transaction status is pending."
        ),
        CaseType.PHISHING_OR_SOCIAL_ENGINEERING: (
            "Customer reports a suspicious contact asking for credentials. "
            "Likely social engineering or phishing attempt. "
            "No financial transaction is directly involved."
        ),
        CaseType.OTHER: (
            "Customer has submitted a complaint that does not clearly match "
            "a specific category. Insufficient detail to classify precisely."
        ),
    }

    # --- Recommended next action templates ---
    ACTION_TEMPLATES = {
        CaseType.WRONG_TRANSFER: (
            "Verify {txn_id} details with the customer and initiate the "
            "wrong-transfer dispute workflow per policy."
        ),
        CaseType.PAYMENT_FAILED: (
            "Investigate {txn_id} ledger status. If balance was deducted on "
            "a failed payment, initiate the automatic reversal flow within "
            "standard SLA."
        ),
        CaseType.REFUND_REQUEST: (
            "Inform the customer that refund eligibility depends on the "
            "merchant's own policy. Provide guidance on contacting the "
            "merchant directly for a refund."
        ),
        CaseType.DUPLICATE_PAYMENT: (
            "Verify the duplicate with payments operations. If the biller "
            "confirms only one payment was received, initiate reversal of "
            "{txn_id}."
        ),
        CaseType.MERCHANT_SETTLEMENT_DELAY: (
            "Route to merchant operations to verify settlement batch status. "
            "Communicate a revised ETA to the merchant."
        ),
        CaseType.AGENT_CASH_IN_ISSUE: (
            "Investigate {txn_id} pending status with agent operations. "
            "Confirm settlement state and resolve within the standard "
            "cash-in SLA."
        ),
        CaseType.PHISHING_OR_SOCIAL_ENGINEERING: (
            "Escalate to fraud risk team immediately. Confirm to customer "
            "that the company never asks for OTP. Log the reported contact "
            "for fraud pattern analysis."
        ),
        CaseType.OTHER: (
            "Reply to customer asking for specific details: which transaction, "
            "what amount, what went wrong, and approximate time."
        ),
    }

    # --- Customer reply templates (English) ---
    REPLY_TEMPLATES_EN = {
        CaseType.WRONG_TRANSFER: (
            "We have noted your concern about transaction {txn_id}. "
            "Please do not share your PIN or OTP with anyone. "
            "Our dispute team will review the case and contact you "
            "through official support channels."
        ),
        CaseType.PAYMENT_FAILED: (
            "We have noted that transaction {txn_id} may have caused an "
            "unexpected balance deduction. Our payments team will review "
            "the case and any eligible amount will be returned through "
            "official channels. Please do not share your PIN or OTP "
            "with anyone."
        ),
        CaseType.REFUND_REQUEST: (
            "Thank you for reaching out. Refunds for completed merchant "
            "payments depend on the merchant's own policy. We recommend "
            "contacting the merchant directly. If you need help reaching "
            "them, please reply and we will guide you. Please do not share "
            "your PIN or OTP with anyone."
        ),
        CaseType.DUPLICATE_PAYMENT: (
            "We have noted the possible duplicate payment for transaction "
            "{txn_id}. Our payments team will verify with the biller and "
            "any eligible amount will be returned through official channels. "
            "Please do not share your PIN or OTP with anyone."
        ),
        CaseType.MERCHANT_SETTLEMENT_DELAY: (
            "We have noted your concern about settlement {txn_id}. Our "
            "merchant operations team will check the batch status and update "
            "you on the expected settlement time through official channels."
        ),
        CaseType.AGENT_CASH_IN_ISSUE: (
            "We have noted your concern about transaction {txn_id}. Our "
            "agent operations team will investigate and update you through "
            "official support channels. Please do not share your PIN or OTP "
            "with anyone."
        ),
        CaseType.PHISHING_OR_SOCIAL_ENGINEERING: (
            "Thank you for reaching out before sharing any information. "
            "We never ask for your PIN, OTP, or password under any "
            "circumstances. Please do not share these with anyone, even if "
            "they claim to be from us. Our fraud team has been notified "
            "of this incident."
        ),
        CaseType.OTHER: (
            "Thank you for reaching out. To help you faster, please share "
            "the transaction ID, the amount involved, and a short "
            "description of what went wrong. Please do not share your PIN "
            "or OTP with anyone."
        ),
    }

    # --- Customer reply templates (Bangla) ---
    REPLY_TEMPLATES_BN = {
        CaseType.WRONG_TRANSFER: (
            "আপনার লেনদেন {txn_id} এর বিষয়ে আমরা অবগত হয়েছি। "
            "আমাদের বিরোধ নিষ্পত্তি দল এটি যাচাই করবে এবং অফিসিয়াল "
            "চ্যানেলে আপনাকে জানাবে। অনুগ্রহ করে কারো সাথে আপনার পিন "
            "বা ওটিপি শেয়ার করবেন না।"
        ),
        CaseType.PAYMENT_FAILED: (
            "আপনার লেনদেন {txn_id} এর বিষয়ে আমরা অবগত হয়েছি। "
            "আমাদের পেমেন্ট দল এটি যাচাই করবে এবং যোগ্য পরিমাণ "
            "অফিসিয়াল চ্যানেলে ফেরত দেওয়া হবে। অনুগ্রহ করে কারো "
            "সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"
        ),
        CaseType.REFUND_REQUEST: (
            "যোগাযোগের জন্য ধন্যবাদ। সম্পন্ন মার্চেন্ট পেমেন্টের রিফান্ড "
            "মার্চেন্টের নিজস্ব নীতির উপর নির্ভর করে। আমরা সরাসরি "
            "মার্চেন্টের সাথে যোগাযোগ করার পরামর্শ দিই। অনুগ্রহ করে "
            "কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"
        ),
        CaseType.DUPLICATE_PAYMENT: (
            "আপনার লেনদেন {txn_id} এর সম্ভাব্য ডুপ্লিকেট পেমেন্টের "
            "বিষয়ে আমরা অবগত হয়েছি। আমাদের পেমেন্ট দল বিলারের সাথে "
            "যাচাই করবে এবং যোগ্য পরিমাণ অফিসিয়াল চ্যানেলে ফেরত দেওয়া "
            "হবে। অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"
        ),
        CaseType.MERCHANT_SETTLEMENT_DELAY: (
            "আপনার সেটেলমেন্ট {txn_id} এর বিষয়ে আমরা অবগত হয়েছি। "
            "আমাদের মার্চেন্ট অপারেশন্স দল ব্যাচ স্ট্যাটাস যাচাই করবে "
            "এবং অফিসিয়াল চ্যানেলে আপনাকে জানাবে।"
        ),
        CaseType.AGENT_CASH_IN_ISSUE: (
            "আপনার লেনদেন {txn_id} এর বিষয়ে আমরা অবগত হয়েছি। "
            "আমাদের এজেন্ট অপারেশন্স দল এটি দ্রুত যাচাই করবে এবং "
            "অফিসিয়াল চ্যানেলে আপনাকে জানাবে। অনুগ্রহ করে কারো সাথে "
            "আপনার পিন বা ওটিপি শেয়ার করবেন না।"
        ),
        CaseType.PHISHING_OR_SOCIAL_ENGINEERING: (
            "কোনো তথ্য শেয়ার করার আগে যোগাযোগ করার জন্য ধন্যবাদ। "
            "আমরা কোনো পরিস্থিতিতেই আপনার পিন, ওটিপি বা পাসওয়ার্ড "
            "জানতে চাই না। অনুগ্রহ করে কাউকে এসব শেয়ার করবেন না, "
            "এমনকি তারা আমাদের পক্ষ থেকে দাবি করলেও। আমাদের জালিয়াতি "
            "দলকে এই ঘটনা সম্পর্কে জানানো হয়েছে।"
        ),
        CaseType.OTHER: (
            "যোগাযোগের জন্য ধন্যবাদ। আপনাকে দ্রুত সাহায্য করতে, "
            "অনুগ্রহ করে লেনদেন আইডি, পরিমাণ এবং কী সমস্যা হয়েছে "
            "তা জানান। অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি "
            "শেয়ার করবেন না।"
        ),
    }

    def generate(
        self,
        case_type: CaseType,
        department: Department,
        evidence_verdict: EvidenceVerdict,
        relevant_transaction_id: str | None,
        matched_amount: float | None = None,
        matched_counterparty: str | None = None,
        language: str | None = None,
    ) -> dict:
        """Generate fallback text fields from templates.

        Returns dict with agent_summary, recommended_next_action, customer_reply.
        """
        txn_id = relevant_transaction_id or "N/A"
        amount = str(int(matched_amount)) if matched_amount else "N/A"
        counterparty = matched_counterparty or "unknown"

        fmt = {
            "txn_id": txn_id,
            "amount": amount,
            "counterparty": counterparty,
        }

        # Agent summary
        summary_template = self.SUMMARY_TEMPLATES.get(
            case_type, self.SUMMARY_TEMPLATES[CaseType.OTHER]
        )
        agent_summary = summary_template.format(**fmt)

        # If no transaction matched, clean up the summary
        if relevant_transaction_id is None:
            agent_summary = agent_summary.replace("N/A", "no specific transaction identified")

        # Recommended next action
        action_template = self.ACTION_TEMPLATES.get(
            case_type, self.ACTION_TEMPLATES[CaseType.OTHER]
        )
        recommended_next_action = action_template.format(**fmt)

        # Customer reply — language-aware
        if language == "bn":
            reply_templates = self.REPLY_TEMPLATES_BN
        else:
            reply_templates = self.REPLY_TEMPLATES_EN

        reply_template = reply_templates.get(
            case_type, reply_templates[CaseType.OTHER]
        )
        customer_reply = reply_template.format(**fmt)

        return {
            "agent_summary": agent_summary,
            "recommended_next_action": recommended_next_action,
            "customer_reply": customer_reply,
        }
