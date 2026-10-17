"""
FastAPI Server for TimeSlice AI Agent.
Exposes endpoints for natural language message parsing and plan execution.
"""

import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.schemas import (
    ParseRequest,
    ParseResponse,
    ExecuteRequest,
    ExecuteResponse,
)
from backend.ai.parser import parse_brain_dump
from backend.ai.planner import validate_and_plan

app = FastAPI(
    title="TimeSlice AI Agent API",
    description="Parses natural language WhatsApp brain dumps into structured calendar events and tasks.",
    version="1.0.0",
)

# Enable CORS for Next.js frontend and ngrok tunneling
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    """Health check endpoint to verify backend service status."""
    has_key = bool(os.getenv("GEMINI_API_KEY"))
    return {
        "status": "healthy",
        "service": "TimeSlice AI Agent",
        "gemini_configured": has_key,
    }


@app.post("/api/parse", response_model=ParseResponse)
def parse_message(request: ParseRequest):
    """
    Core AI Parsing Endpoint:
    Receives raw natural-language brain dump and returns structured, categorized activities.
    """
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        response = parse_brain_dump(request)
        # Run through planner for conflict checks & validation
        validated_activities, warnings = validate_and_plan(response.activities)
        response.activities = validated_activities
        if warnings and not response.clarification_prompt:
            response.clarification_prompt = " | ".join(warnings)
            response.needs_clarification = True
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Parsing failed: {str(e)}")


@app.post("/api/execute", response_model=ExecuteResponse)
def execute_plan(request: ExecuteRequest):
    """
    Execution endpoint:
    Handoff to Google Calendar / Google Tasks integration.
    """
    # Placeholder for Ojal's Google Workspace integration
    return ExecuteResponse(
        results=request.activities,
        success=True,
        whatsapp_reply="Synced activities to Google Workspace.",
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
