"""
Shared Data Contract & Pydantic Schemas for TimeSlice.
Adheres strictly to the Team Shared Contract across Frontend, AI Agent, Google Workspace, and WhatsApp/Database.
"""

from enum import Enum
from typing import Optional, List
from datetime import datetime
import uuid
from pydantic import BaseModel, Field


class ActivityCategory(str, Enum):
    """The 5 core TimeSlice categories."""
    academics = "academics"
    career = "career"
    social = "social"
    health = "health"
    admin = "admin"


class ActivityType(str, Enum):
    """Distinction between scheduled calendar events and un-timed tasks."""
    event = "event"
    task = "task"


class ActivityStatus(str, Enum):
    """Status lifecycle for an activity."""
    proposed = "proposed"
    needs_clarification = "needs_clarification"
    executing = "executing"
    completed = "completed"
    failed = "failed"


class Activity(BaseModel):
    """
    Normalized activity object matching the team's shared data contract.
    Both Google Calendar/Tasks and Supabase store/consume this model.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: ActivityType
    title: str
    category: ActivityCategory
    # Calendar events require start_time and end_time (ISO 8601 with timezone offset)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    # Google Tasks may have due_date without a time duration (YYYY-MM-DD)
    due_date: Optional[str] = None
    duration_minutes: Optional[int] = None
    status: ActivityStatus = ActivityStatus.proposed
    clarification_needed: Optional[str] = None
    external_id: Optional[str] = None  # Google Calendar Event ID or Google Task ID
    source: str = "whatsapp"


class ParseRequest(BaseModel):
    """Incoming request to parse a natural language brain dump."""
    message: str
    user_id: str = "default_user"
    timezone: str = "America/New_York"
    # Optional override for testing or message receipt timestamp
    current_time: Optional[datetime] = None


class ParseResponse(BaseModel):
    """Output from the AI parsing layer."""
    original_message: str
    summary: str
    whatsapp_reply: str
    activities: List[Activity]
    needs_clarification: bool = False
    clarification_prompt: Optional[str] = None


class ExecuteRequest(BaseModel):
    """Incoming request to execute an approved action plan."""
    activities: List[Activity]
    user_id: str = "default_user"


class ExecuteResponse(BaseModel):
    """Output after Google Workspace execution."""
    results: List[Activity]
    success: bool
    whatsapp_reply: str
