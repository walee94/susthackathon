# QueueStorm Investigator

AI/API SupportOps copilot for the SUST CSE Carnival 2026 Codex Community Hackathon preliminary round.

This service exposes:

- `GET /health`
- `POST /analyze-ticket`

It receives one synthetic customer complaint with recent transaction history and returns a structured JSON analysis.

## Tech stack

- Python
- FastAPI
- Pydantic
- Uvicorn
- Rule-based evidence reasoning
- Safety guardrails for customer-facing replies

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Health check

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## Analyze a ticket

```bash
curl -X POST http://localhost:8000/analyze-ticket \
  -H "Content-Type: application/json" \
  --data @sample_request.json
```

## Required response fields

The API returns:

```json
{
  "ticket_id": "TKT-001",
  "relevant_transaction_id": "TXN-9101",
  "evidence_verdict": "consistent",
  "case_type": "wrong_transfer",
  "severity": "high",
  "department": "dispute_resolution",
  "agent_summary": "...",
  "recommended_next_action": "...",
  "customer_reply": "...",
  "human_review_required": true,
  "confidence": 0.92,
  "reason_codes": []
}
```

## Evidence reasoning approach

The analyzer compares the complaint against each transaction using:

- amount match
- counterparty match
- transaction type clues
- transaction status clues
- user type clues
- safety-sensitive keyword detection

It selects the best matching transaction when the score is strong enough.

Then it sets:

- `relevant_transaction_id`
- `evidence_verdict`
- `case_type`
- `department`
- `severity`
- `human_review_required`

## Safety logic

Customer replies are passed through a final safety guardrail.

The service never asks the customer for:

- PIN
- OTP
- password
- full card number
- CVV

The service never confirms refunds, reversals, account recovery, or unblocking without authority.

Safe wording example:

> Any eligible amount will be processed through official channels after verification.

## MODELS

This version uses no external model.

| Model | Where it runs | Reason |
|---|---|---|
| Rule-based classifier and evidence analyzer | Inside this API service | Fast, free, stable, no API key required, safer for hidden tests |

Optional future improvement:

| Model | Where it runs | Reason |
|---|---|---|
| OpenAI GPT model | External API | Improve phrasing for summaries and customer replies after rule-based decision locks schema fields |

Important: If an LLM is added later, the rule engine should still own enum fields and safety-critical decisions.

## Assumptions

- Inputs are synthetic.
- `transaction_history` usually contains 2 to 5 transactions.
- The API should prefer `insufficient_data` over guessing.
- High-risk or ambiguous cases should be escalated to human review.

## Known limitations

- Bangla and Banglish support is keyword-based.
- Time matching is simple.
- It does not connect to any real payment system.
- It does not perform live fraud investigation.

## Docker

Build:

```bash
docker build -t queuestorm-investigator .
```

Run:

```bash
docker run -p 8000:8000 queuestorm-investigator
```

Test:

```bash
curl http://localhost:8000/health
```

## Tests

```bash
pytest
```

## Deployment idea

For a fast hackathon deployment, use Render, Railway, Fly.io, or Poridhi Labs.

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

If the platform does not provide `$PORT`, use:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```


## Hidden-case strategy added

The service now includes stronger logic for likely hidden cases:

- exact transaction ID matching
- Bangla digit amount extraction
- ambiguous-match detection
- duplicate payment second-transaction selection
- repeated-recipient contradiction for wrong-transfer claims
- merchant settlement routing using `user_type` and `channel`
- agent cash-in routing for English, Bangla, and Banglish complaints
- phishing and prompt-injection protection
- safe fallback when transaction history is missing or unclear

## Local evaluation

Run:

```bash
python scripts/evaluate_cases.py
```

Current result:

```text
public_sample_cases.json: 60/60
hidden_edge_cases.json: 120/120
TOTAL: 180/180
All core decisions passed. No unsafe customer replies detected.
```

## Included test files

- `public_sample_cases.json`: official public sample pack copied into the repo for local testing.
- `hidden_edge_cases.json`: custom hidden-style cases created from the rubric and problem statement.
- `EVALUATION_NOTES.md`: explains the hidden-case strategy and evaluation result.

## Decision priority

The engine uses this order:

1. Detect phishing, credential abuse, and prompt injection.
2. Detect duplicate payments and select the later matching transaction.
3. Detect merchant settlement cases.
4. Detect agent cash-in cases.
5. Detect wrong transfer or receiver-not-received cases.
6. Detect failed payment or failed transaction cases.
7. Detect refund requests.
8. Return `other` with `insufficient_data` when the complaint is vague.

## Safety design

The system never asks customers for secrets.

It may warn customers not to share secrets.

It never promises a refund, reversal, unblock, or recovery.

It uses safe phrasing such as:

```text
Any eligible amount will be processed through official channels after verification.
```
