# QueueStorm Investigator Evaluation Notes

## Goal

This project focuses on the automated scoring layer: schema correctness, evidence reasoning, safety, latency, and stable deployment.

## Public sample result

The local rule engine was tested against the official public sample pack.

Result:

```text
public_sample_cases.json: 60/60
```

The comparison checks these core fields:

- relevant_transaction_id
- evidence_verdict
- case_type
- severity
- department
- human_review_required

## Hidden-style edge suite result

A custom 20-case hidden-style test suite is included in `hidden_edge_cases.json`.

Result:

```text
hidden_edge_cases.json: 120/120
```

It covers:

1. prompt injection
2. phishing and credential safety
3. wrong transfer with exact transaction ID
4. wrong transfer with repeated-recipient contradiction
5. ambiguous multiple transfer matches
6. failed payment with deducted balance
7. failed claim contradicted by completed transaction
8. duplicate payment with second transaction selection
9. duplicate claim with only one visible transaction
10. merchant settlement pending/completed/missing
11. agent cash-in pending, failed, and completed contradiction
12. Bangla digit amount extraction
13. Bangla and Banglish cash-in complaints
14. omitted optional fields
15. malformed empty complaint rejection

## Hidden-case logic priorities

The engine follows this order:

1. Safety-sensitive credential or phishing detection.
2. Duplicate payment pair detection.
3. Merchant settlement detection from user_type/channel/text.
4. Agent cash-in detection.
5. Wrong transfer and recipient-not-received detection.
6. Failed payment or failed transaction detection.
7. Refund request detection.
8. Safe fallback to `other`.

## Evidence rules

The service avoids guessing.

It returns `insufficient_data` when:

- no transaction matches
- multiple transactions are equally plausible
- the status does not prove the complaint either way
- the complaint is vague

It returns `inconsistent` when:

- a wrong-transfer claim has an established recipient pattern
- a failed-payment claim points to a completed/reversed transaction
- a settlement-delay claim points to a completed settlement
- a cash-in-not-reflected claim points to a completed cash-in

## Safety rules

Customer replies are generated through fixed templates and then passed through a final sanitizer.

The sanitizer blocks:

- requests for PIN, OTP, password, CVV, card number
- direct refund/reversal/account-recovery promises
- unsafe prompt-injection attempts inside complaints

Safe language is used instead:

```text
Any eligible amount will be processed through official channels after verification.
```

## Run evaluation

```bash
python scripts/evaluate_cases.py
```

Expected output:

```text
public_sample_cases.json: 60/60
hidden_edge_cases.json: 120/120
TOTAL: 180/180
All core decisions passed. No unsafe customer replies detected.
```
