"""
Natural-language brain dump parser powered by Gemini.
Extracts multiple events and tasks, categorizes them, resolves relative dates, and structures actions.
"""

from datetime import datetime, timedelta
import pytz
from typing import Dict, Any, List
from backend.schemas import (
    ParseRequest,
    ParseResponse,
    Activity,
    ActivityType,
    ActivityCategory,
    ActivityStatus,
)
from backend.ai.gemini_client import call_gemini

SYSTEM_INSTRUCTION = """You are Offload AI, an intelligent agent that parses chaotic natural-language brain dumps from WhatsApp into structured calendar events and tasks.

YOUR MISSION:
1. Extract ALL discrete activities from the user's message (there may be 1, 2, 3, or more items in a single message).
2. For each activity:
   - Assign exact activity type: "event" or "task"
     * "event": Scheduled time block on Google Calendar (e.g., "study Java for 2 hours tonight", "chapter meeting Friday at 7 PM").
     * "task": Action item or reminder without a dedicated calendar block (e.g., "remind me to submit resume", "apply to IBM internship tomorrow").
   - Assign exact category from these 5 ONLY:
     * "academics": classes, exams, homework, study blocks, research.
     * "career": job/internship applications, resume edits, interviews, career fairs.
     * "social": friends, club meetings, fraternity/sorority chapter, parties, family events.
     * "health": workouts, gym, sports, doctors, therapy, rest.
     * "admin": chores, errands, groceries, laundry, administrative tasks, bills.
   - Resolve dates and times using the provided Reference Current Time and User Timezone:
     * Output start_time and end_time in ISO 8601 with timezone offset (e.g. 2026-10-18T19:00:00-04:00).
     * If duration is mentioned (e.g. "2 hours tonight") but exact time is missing, schedule a sensible default evening block (e.g. 19:00-21:00) with status "proposed".
     * If end time is not stated for an event (e.g. "meeting at 7 PM"), default duration to 60 minutes.
     * For tasks, output due_date as YYYY-MM-DD if mentioned, or null.
     * If critical info is ambiguous, note in "clarification_needed".
3. Write a natural, encouraging WhatsApp response (under 160 characters when possible):
   * State what was synced.
   * Mention the category impact (e.g., "Your Academics slice just increased by 2 hours!").

OUTPUT FORMAT:
Return pure JSON matching this exact schema:
{
  "summary": "Short 1-line summary of items found",
  "whatsapp_reply": "Friendly WhatsApp confirmation to text back to the user",
  "activities": [
    {
      "type": "event" | "task",
      "title": "Clean concise title",
      "category": "academics" | "career" | "social" | "health" | "admin",
      "start_time": "ISO 8601 string or null",
      "end_time": "ISO 8601 string or null",
      "due_date": "YYYY-MM-DD or null",
      "duration_minutes": integer or null,
      "status": "proposed" | "needs_clarification",
      "clarification_needed": "Explanation if time/details are ambiguous or null"
    }
  ]
}
"""


def parse_brain_dump(request: ParseRequest) -> ParseResponse:
    """
    Parses a user's natural language brain dump into validated Pydantic Activity models.
    """
    tz_str = request.timezone or "America/New_York"
    try:
        user_tz = pytz.timezone(tz_str)
    except Exception:
        user_tz = pytz.timezone("America/New_York")

    ref_time = request.current_time or datetime.now(user_tz)
    if ref_time.tzinfo is None:
        ref_time = user_tz.localize(ref_time)

    prompt = f"""Reference Current Time: {ref_time.strftime('%A, %B %d, %Y at %I:%M %p %Z')} (ISO: {ref_time.isoformat()})
User Timezone: {tz_str}

Incoming WhatsApp Brain Dump:
"{request.message}"

Extract and categorize all events and tasks according to the system instructions.
"""

    gemini_data = call_gemini(system_instruction=SYSTEM_INSTRUCTION, prompt=prompt)

    raw_activities = gemini_data.get("activities", [])
    activities: List[Activity] = []
    has_clarification = False
    clarification_prompts = []

    for item in raw_activities:
        # Normalize category
        cat_raw = item.get("category")
        cat_str = cat_raw.lower() if cat_raw else "admin"
        try:
            category = ActivityCategory(cat_str)
        except ValueError:
            category = ActivityCategory.admin

        # Normalize type
        type_raw = item.get("type")
        type_str = type_raw.lower() if type_raw else "task"
        try:
            act_type = ActivityType(type_str)
        except ValueError:
            act_type = ActivityType.task

        # Parse timestamps
        start_time = None
        end_time = None
        if item.get("start_time"):
            try:
                start_time = datetime.fromisoformat(item["start_time"])
            except Exception:
                start_time = None

        if item.get("end_time"):
            try:
                end_time = datetime.fromisoformat(item["end_time"])
            except Exception:
                end_time = None

        # Calculate duration if missing but start & end exist
        duration = item.get("duration_minutes")
        if duration is None and start_time and end_time:
            duration = int((end_time - start_time).total_seconds() / 60)

        # Check status
        status_raw = item.get("status")
        status_str = status_raw.lower() if status_raw else "proposed"
        try:
            status = ActivityStatus(status_str)
        except ValueError:
            status = ActivityStatus.proposed

        clarif = item.get("clarification_needed")
        if clarif:
            has_clarification = True
            clarification_prompts.append(clarif)

        act = Activity(
            type=act_type,
            title=item.get("title", "Untitled Activity"),
            category=category,
            start_time=start_time,
            end_time=end_time,
            due_date=item.get("due_date"),
            duration_minutes=duration,
            status=status,
            clarification_needed=clarif,
            source="whatsapp",
        )
        activities.append(act)

    summary = gemini_data.get("summary", f"Extracted {len(activities)} items.")
    whatsapp_reply = gemini_data.get(
        "whatsapp_reply",
        f"Done! Processed {len(activities)} item(s) from your brain dump.",
    )

    return ParseResponse(
        original_message=request.message,
        summary=summary,
        whatsapp_reply=whatsapp_reply,
        activities=activities,
        needs_clarification=has_clarification,
        clarification_prompt="; ".join(clarification_prompts) if clarification_prompts else None,
    )
