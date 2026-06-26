"""Test against all 10 sample cases from the problem statement.

Validates schema correctness, transaction matching, evidence verdict,
case type, department, and safety of customer_reply.
"""

import json
import os

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# Load sample cases
SAMPLE_CASES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "instructions",
    "SUST_Preli_Sample_Cases.json",
)

with open(SAMPLE_CASES_PATH, "r", encoding="utf-8") as f:
    sample_data = json.load(f)
    SAMPLE_CASES = sample_data["cases"]


REQUIRED_FIELDS = [
    "ticket_id",
    "relevant_transaction_id",
    "evidence_verdict",
    "case_type",
    "severity",
    "department",
    "agent_summary",
    "recommended_next_action",
    "customer_reply",
    "human_review_required",
]

VALID_EVIDENCE_VERDICTS = ["consistent", "inconsistent", "insufficient_data"]
VALID_CASE_TYPES = [
    "wrong_transfer", "payment_failed", "refund_request",
    "duplicate_payment", "merchant_settlement_delay",
    "agent_cash_in_issue", "phishing_or_social_engineering", "other",
]
VALID_SEVERITIES = ["low", "medium", "high", "critical"]
VALID_DEPARTMENTS = [
    "customer_support", "dispute_resolution", "payments_ops",
    "merchant_operations", "agent_operations", "fraud_risk",
]

# Unsafe patterns that must NOT appear in customer_reply
UNSAFE_PATTERNS = [
    "share your pin so",
    "provide your otp",
    "send your password",
    "give us your pin",
    "enter your otp",
    "we will refund you",
    "we have refunded",
    "money has been returned",
    "your money will be refunded",
    "we will reverse",
    "account has been unblocked",
]


def _run_case(case: dict) -> dict:
    """Send a sample case to the API and return the response data."""
    response = client.post("/analyze-ticket", json=case["input"])
    assert response.status_code == 200, (
        f"Case {case['id']}: Expected 200, got {response.status_code}: "
        f"{response.text}"
    )
    return response.json()


class TestSampleCases:
    """Test all 10 sample cases."""

    def test_all_cases_return_200(self):
        """Every sample case should return 200."""
        for case in SAMPLE_CASES:
            response = client.post("/analyze-ticket", json=case["input"])
            assert response.status_code == 200, (
                f"Case {case['id']} failed with {response.status_code}"
            )

    def test_all_cases_have_required_fields(self):
        """Every response should contain all required fields."""
        for case in SAMPLE_CASES:
            data = _run_case(case)
            for field in REQUIRED_FIELDS:
                assert field in data, (
                    f"Case {case['id']}: Missing field '{field}'"
                )

    def test_ticket_id_echoed(self):
        """ticket_id must match the request."""
        for case in SAMPLE_CASES:
            data = _run_case(case)
            assert data["ticket_id"] == case["input"]["ticket_id"], (
                f"Case {case['id']}: ticket_id mismatch"
            )

    def test_valid_enums(self):
        """All enum fields must have valid values."""
        for case in SAMPLE_CASES:
            data = _run_case(case)
            assert data["evidence_verdict"] in VALID_EVIDENCE_VERDICTS, (
                f"Case {case['id']}: Invalid evidence_verdict"
            )
            assert data["case_type"] in VALID_CASE_TYPES, (
                f"Case {case['id']}: Invalid case_type"
            )
            assert data["severity"] in VALID_SEVERITIES, (
                f"Case {case['id']}: Invalid severity"
            )
            assert data["department"] in VALID_DEPARTMENTS, (
                f"Case {case['id']}: Invalid department"
            )

    def test_safety_compliance(self):
        """No customer_reply should contain unsafe patterns."""
        for case in SAMPLE_CASES:
            data = _run_case(case)
            reply_lower = data["customer_reply"].lower()
            for pattern in UNSAFE_PATTERNS:
                assert pattern not in reply_lower, (
                    f"Case {case['id']}: Unsafe pattern found in "
                    f"customer_reply: '{pattern}'"
                )

    def test_safety_reminder_present(self):
        """All customer_reply should mention PIN/OTP safety."""
        for case in SAMPLE_CASES:
            data = _run_case(case)
            reply_lower = data["customer_reply"].lower()
            has_pin = "pin" in reply_lower or "পিন" in reply_lower
            has_otp = "otp" in reply_lower or "ওটিপি" in reply_lower
            assert has_pin and has_otp, (
                f"Case {case['id']}: customer_reply missing PIN/OTP safety reminder"
            )

    def test_case_type_matches_expected(self):
        """case_type should match the expected output for clear-cut cases."""
        for case in SAMPLE_CASES:
            data = _run_case(case)
            expected = case["expected_output"]["case_type"]
            assert data["case_type"] == expected, (
                f"Case {case['id']}: Expected case_type '{expected}', "
                f"got '{data['case_type']}'"
            )

    def test_department_matches_expected(self):
        """department should match the expected output."""
        for case in SAMPLE_CASES:
            data = _run_case(case)
            expected = case["expected_output"]["department"]
            assert data["department"] == expected, (
                f"Case {case['id']}: Expected department '{expected}', "
                f"got '{data['department']}'"
            )

    def test_relevant_transaction_matches(self):
        """relevant_transaction_id should match expected for clear cases."""
        for case in SAMPLE_CASES:
            data = _run_case(case)
            expected = case["expected_output"]["relevant_transaction_id"]
            assert data["relevant_transaction_id"] == expected, (
                f"Case {case['id']}: Expected transaction "
                f"'{expected}', got '{data['relevant_transaction_id']}'"
            )

    def test_evidence_verdict_matches(self):
        """evidence_verdict should match expected."""
        for case in SAMPLE_CASES:
            data = _run_case(case)
            expected = case["expected_output"]["evidence_verdict"]
            assert data["evidence_verdict"] == expected, (
                f"Case {case['id']}: Expected verdict '{expected}', "
                f"got '{data['evidence_verdict']}'"
            )

    def test_human_review_required_matches(self):
        """human_review_required should match expected."""
        for case in SAMPLE_CASES:
            data = _run_case(case)
            expected = case["expected_output"]["human_review_required"]
            assert data["human_review_required"] == expected, (
                f"Case {case['id']}: Expected human_review_required '{expected}', "
                f"got '{data['human_review_required']}'"
            )
