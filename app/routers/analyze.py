"""POST /analyze-ticket — main analysis endpoint.

Orchestrates the full pipeline:
1. Validate input
2. Match transaction
3. Analyze evidence
4. Classify case
5. Score severity
6. Decide escalation
7. Generate text (LLM or fallback)
8. Apply safety guardrails
9. Return response
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.core.case_classifier import CaseClassifier
from app.core.escalation import EscalationDecider
from app.core.evidence_analyzer import EvidenceAnalyzer
from app.core.severity_scorer import SeverityScorer
from app.core.transaction_matcher import TransactionMatcher
from app.llm.fallback import FallbackGenerator
from app.llm.groq_client import GroqClient
from app.llm.parser import parse_llm_response
from app.llm.prompts import (
    SYSTEM_PROMPT,
    build_history_summary,
    build_transaction_summary,
    build_user_prompt,
)
from app.models.request import AnalyzeTicketRequest
from app.models.response import AnalyzeTicketResponse
from app.safety.guardrails import SafetyGuardrails

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize components (stateless, safe to reuse)
transaction_matcher = TransactionMatcher()
evidence_analyzer = EvidenceAnalyzer()
case_classifier = CaseClassifier()
severity_scorer = SeverityScorer()
escalation_decider = EscalationDecider()
groq_client = GroqClient()
fallback_generator = FallbackGenerator()
safety_guardrails = SafetyGuardrails()


@router.post("/analyze-ticket", response_model=AnalyzeTicketResponse)
async def analyze_ticket(request: AnalyzeTicketRequest):
    """Analyze a customer complaint ticket.

    Returns a structured JSON response with classification, evidence analysis,
    routing, and safe customer reply.
    """
    try:
        # Step 1: Match transaction
        match_result = transaction_matcher.match(request)

        # Step 2: Analyze evidence
        evidence_verdict = evidence_analyzer.analyze(request, match_result)

        # Step 3: Classify case type and department
        classification = case_classifier.classify(request, match_result)

        # Step 4: Score severity
        severity = severity_scorer.score(
            request,
            classification.case_type,
            evidence_verdict,
            match_result,
        )

        # Step 5: Compute confidence
        confidence = _compute_confidence(match_result, evidence_verdict)

        # Step 6: Decide escalation
        has_pending = (
            match_result.matched_transaction is not None
            and match_result.matched_transaction.status.value == "pending"
        )
        human_review = escalation_decider.should_escalate(
            case_type=classification.case_type,
            severity=severity,
            evidence_verdict=evidence_verdict,
            confidence=confidence,
            duplicate_detected=match_result.duplicate_detected,
            has_pending_txn=has_pending,
        )

        # Step 7: Generate text fields (LLM with fallback)
        text_fields = await _generate_text_fields(
            request, match_result, classification, evidence_verdict, severity
        )

        # Step 8: Apply safety guardrails
        language = request.language.value if request.language else None
        sanitized = safety_guardrails.check_and_sanitize(
            customer_reply=text_fields["customer_reply"],
            recommended_next_action=text_fields["recommended_next_action"],
            agent_summary=text_fields["agent_summary"],
            language=language,
        )

        # Step 9: Build and return response
        response = AnalyzeTicketResponse(
            ticket_id=request.ticket_id,
            relevant_transaction_id=match_result.transaction_id,
            evidence_verdict=evidence_verdict,
            case_type=classification.case_type,
            severity=severity,
            department=classification.department,
            agent_summary=sanitized["agent_summary"],
            recommended_next_action=sanitized["recommended_next_action"],
            customer_reply=sanitized["customer_reply"],
            human_review_required=human_review,
            confidence=round(confidence, 2),
            reason_codes=classification.reason_codes,
        )

        return response

    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Error analyzing ticket: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while processing the ticket.",
        )


async def _generate_text_fields(
    request: AnalyzeTicketRequest,
    match_result,
    classification,
    evidence_verdict,
    severity,
) -> dict:
    """Generate text fields using LLM or fallback."""
    language = request.language.value if request.language else None
    transactions = request.transaction_history or []

    # Build transaction summaries for the prompt
    matched_txn_summary = None
    if match_result.matched_transaction:
        matched_txn_summary = build_transaction_summary(
            match_result.matched_transaction
        )

    history_summary = build_history_summary(transactions)

    # Try LLM first
    user_prompt = build_user_prompt(
        ticket_id=request.ticket_id,
        complaint=request.complaint,
        language=language,
        case_type=classification.case_type.value,
        department=classification.department.value,
        severity=severity.value,
        evidence_verdict=evidence_verdict.value,
        relevant_transaction_id=match_result.transaction_id,
        matched_transaction_summary=matched_txn_summary,
        transaction_history_summary=history_summary,
        user_type=request.user_type.value if request.user_type else None,
        duplicate_detected=match_result.duplicate_detected,
        established_recipient=match_result.established_recipient,
        ambiguous=match_result.ambiguous,
    )

    llm_response = await groq_client.chat_completion(SYSTEM_PROMPT, user_prompt)
    parsed = parse_llm_response(llm_response)

    if parsed:
        logger.info("Using LLM-generated text fields")
        return parsed

    # Fallback to templates
    logger.info("Using fallback text generation")
    matched_amount = (
        match_result.matched_transaction.amount
        if match_result.matched_transaction
        else None
    )
    matched_counterparty = (
        match_result.matched_transaction.counterparty
        if match_result.matched_transaction
        else None
    )

    return fallback_generator.generate(
        case_type=classification.case_type,
        department=classification.department,
        evidence_verdict=evidence_verdict,
        relevant_transaction_id=match_result.transaction_id,
        matched_amount=matched_amount,
        matched_counterparty=matched_counterparty,
        language=language,
    )


def _compute_confidence(match_result, evidence_verdict) -> float:
    """Compute a confidence score based on match quality and evidence."""
    base = 0.5

    # Strong match boosts confidence
    if match_result.transaction_id and not match_result.ambiguous:
        if match_result.match_scores:
            best_score = max(match_result.match_scores.values())
            if best_score >= 5.0:
                base = 0.9
            elif best_score >= 3.0:
                base = 0.8
            else:
                base = 0.7

    # Ambiguous match lowers confidence
    if match_result.ambiguous:
        base = 0.6

    # No match
    if match_result.transaction_id is None:
        base = 0.55

    # Duplicate detection boosts confidence
    if match_result.duplicate_detected:
        base = max(base, 0.9)

    # Evidence verdict adjustments
    from app.models.response import EvidenceVerdict

    if evidence_verdict == EvidenceVerdict.CONSISTENT:
        base = min(base + 0.05, 0.95)
    elif evidence_verdict == EvidenceVerdict.INCONSISTENT:
        base = max(base - 0.05, 0.5)
    elif evidence_verdict == EvidenceVerdict.INSUFFICIENT_DATA:
        base = max(base - 0.1, 0.4)

    return round(min(max(base, 0.0), 1.0), 2)
