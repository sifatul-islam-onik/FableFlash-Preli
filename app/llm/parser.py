"""Response parser for LLM output."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def parse_llm_response(llm_output: dict | None) -> dict | None:
    """Parse and validate the LLM's JSON response.

    Returns a dict with agent_summary, recommended_next_action, customer_reply
    or None if parsing fails.
    """
    if llm_output is None:
        return None

    required_fields = ["agent_summary", "recommended_next_action", "customer_reply"]

    # Check all required fields are present and non-empty
    for field in required_fields:
        if field not in llm_output:
            logger.warning(f"LLM response missing field: {field}")
            return None
        if not isinstance(llm_output[field], str) or not llm_output[field].strip():
            logger.warning(f"LLM response has empty/invalid field: {field}")
            return None

    return {
        "agent_summary": llm_output["agent_summary"].strip(),
        "recommended_next_action": llm_output["recommended_next_action"].strip(),
        "customer_reply": llm_output["customer_reply"].strip(),
    }
