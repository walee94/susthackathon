from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_wrong_transfer():
    payload = {
        "ticket_id": "TKT-001",
        "complaint": "I sent 5000 taka to a wrong number around 2pm today.",
        "language": "en",
        "channel": "in_app_chat",
        "user_type": "customer",
        "transaction_history": [
            {
                "transaction_id": "TXN-9101",
                "timestamp": "2026-04-14T14:08:22Z",
                "type": "transfer",
                "amount": 5000,
                "counterparty": "+8801719876543",
                "status": "completed"
            }
        ]
    }
    res = client.post("/analyze-ticket", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["ticket_id"] == "TKT-001"
    assert data["relevant_transaction_id"] == "TXN-9101"
    assert data["case_type"] == "wrong_transfer"
    assert data["evidence_verdict"] == "consistent"
    assert data["department"] == "dispute_resolution"
    assert "OTP" in data["customer_reply"] or "eligible amount" in data["customer_reply"]


def test_phishing_safety():
    payload = {
        "ticket_id": "TKT-002",
        "complaint": "Someone called me and asked for my OTP and PIN for cashback.",
        "language": "en",
        "channel": "call_center",
        "user_type": "customer",
        "transaction_history": []
    }
    res = client.post("/analyze-ticket", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["case_type"] == "phishing_or_social_engineering"
    assert data["department"] == "fraud_risk"
    assert data["severity"] == "critical"
    assert data["human_review_required"] is True
    assert "Do not share" in data["customer_reply"]


def test_empty_complaint_rejected():
    payload = {
        "ticket_id": "TKT-003",
        "complaint": "",
        "transaction_history": []
    }
    res = client.post("/analyze-ticket", json=payload)
    assert res.status_code in (400, 422)
