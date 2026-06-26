# RUNBOOK

## Local run

```bash
git clone <your-repo-url>
cd <your-repo-folder>
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Verify service

```bash
curl http://localhost:8000/health
```

Expected:

```json
{"status":"ok"}
```

## Test sample case

```bash
curl -X POST http://localhost:8000/analyze-ticket \
  -H "Content-Type: application/json" \
  --data @sample_request.json
```

## Docker run

```bash
docker build -t queuestorm-investigator .
docker run -p 8000:8000 queuestorm-investigator
```

## Notes for judges

This solution is intentionally rule-based for speed, reproducibility, and safety.
No API key is required.
