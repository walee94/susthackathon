from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .analyzer import analyze_ticket
from .schemas import AnalyzeTicketRequest, AnalyzeTicketResponse

app = FastAPI(
    title="QueueStorm Investigator",
    version="1.0.0",
    description="AI/API SupportOps copilot for ticket investigation.",
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze-ticket", response_model=AnalyzeTicketResponse)
def analyze(req: AnalyzeTicketRequest):
    try:
        return analyze_ticket(req)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        # Never leak stack traces, API keys, or implementation details.
        raise HTTPException(status_code=500, detail="Internal analysis error")


@app.exception_handler(Exception)
async def safe_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )
