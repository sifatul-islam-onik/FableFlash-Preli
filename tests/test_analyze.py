"""Test POST /analyze-ticket endpoint — schema and error handling."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

VALID_INPUT = {
    "ticket_id": "TKT-TEST-001",
    "complaint": "I sent 5000 taka to a wrong number around 2pm today.",
    "language": "en",
    "channel": "in_app_chat",
    "user_type": "customer",
    "transaction_history": [
        {
            "transaction_id": "TXN-TEST-001",
            "timestamp": "2026-04-14T14:08:22Z",
            "type": "transfer",
            "amount": 5000,
            "counterparty": "+8801719876543",
            "status": "completed",
        }
    ],
}


def test_valid_request_returns_200():
    """Valid input returns 200 with all required fields."""
    response = client.post("/analyze-ticket", json=VALID_INPUT)
    assert response.status_code == 200
    data = response.json()

    # Check all required fields are present
    required_fields = [
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
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"

    # ticket_id must be echoed back
    assert data["ticket_id"] == "TKT-TEST-001"

    # Enums must be valid
    assert data["evidence_verdict"] in [
        "consistent", "inconsistent", "insufficient_data"
    ]
    assert data["case_type"] in [
        "wrong_transfer", "payment_failed", "refund_request",
        "duplicate_payment", "merchant_settlement_delay",
        "agent_cash_in_issue", "phishing_or_social_engineering", "other",
    ]
    assert data["severity"] in ["low", "medium", "high", "critical"]
    assert data["department"] in [
        "customer_support", "dispute_resolution", "payments_ops",
        "merchant_operations", "agent_operations", "fraud_risk",
    ]
    assert isinstance(data["human_review_required"], bool)


def test_malformed_json_returns_400():
    """Malformed JSON should return 400."""
    response = client.post(
        "/analyze-ticket",
        content="not valid json{{{",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code in (400, 422)


def test_missing_ticket_id_returns_422():
    """Missing required field ticket_id should return 422."""
    bad_input = {
        "complaint": "Something went wrong.",
    }
    response = client.post("/analyze-ticket", json=bad_input)
    assert response.status_code in (400, 422)


def test_empty_complaint_returns_422():
    """Empty complaint string should return 422."""
    bad_input = {
        "ticket_id": "TKT-BAD",
        "complaint": "",
    }
    response = client.post("/analyze-ticket", json=bad_input)
    assert response.status_code == 422


def test_whitespace_only_complaint_returns_422():
    """Whitespace-only complaint should return 422."""
    bad_input = {
        "ticket_id": "TKT-BAD",
        "complaint": "   ",
    }
    response = client.post("/analyze-ticket", json=bad_input)
    assert response.status_code == 422


def test_empty_transaction_history():
    """Request with empty transaction_history should work."""
    input_data = {
        "ticket_id": "TKT-EMPTY",
        "complaint": "Someone called me asking for my OTP.",
        "language": "en",
        "transaction_history": [],
    }
    response = client.post("/analyze-ticket", json=input_data)
    assert response.status_code == 200
    data = response.json()
    assert data["ticket_id"] == "TKT-EMPTY"
    assert data["relevant_transaction_id"] is None


def test_minimal_valid_request():
    """Request with only required fields (ticket_id + complaint)."""
    input_data = {
        "ticket_id": "TKT-MINIMAL",
        "complaint": "I have a problem with my account.",
    }
    response = client.post("/analyze-ticket", json=input_data)
    assert response.status_code == 200
    data = response.json()
    assert data["ticket_id"] == "TKT-MINIMAL"


def test_confidence_in_range():
    """Confidence should be between 0 and 1."""
    response = client.post("/analyze-ticket", json=VALID_INPUT)
    data = response.json()
    if data.get("confidence") is not None:
        assert 0.0 <= data["confidence"] <= 1.0
