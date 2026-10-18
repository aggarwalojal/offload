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

SYSTEM_INSTRUCTION = """You are Offload AI, an intelligent executive scheduling and commitment tracking assistant built for ADP teams, implementation specialists, and client relationship managers.

YOUR MISSION:
Convert unstructured human interactions, client calls, meeting notes, Slack/WhatsApp chats, and messy brain dumps into actionable, categorized Google Calendar events and Google Tasks. Help ADP implementation teams preserve client context, track commitments automatically, and spend less time searching and more time executing.

1. EXTRACT ALL DISCRETE COMMITMENTS & ACTIVITIES:
   - Identify every client meeting, implementation deliverable, review, follow-up, and action item mentioned in the user's message.

2. CLASSIFY EACH ACTIVITY:
   - "type":
     * "event": Scheduled time block on Google Calendar (client meetings, demos, kickoff calls, implementation working sessions).
     * "task": Action item, commitment, or deliverable (e.g., "send payroll export checklist", "verify tax filing with Delta", "review ADP Vantage configuration").
   - "category" (Must strictly be one of these 5):
     * "career": Client Implementation & Deliverables (client meetings, data migrations, onboarding milestones, project deliverables).
     * "admin": Operations & Compliance (payroll audits, tax compliance, timesheets, tickets, documentation, administrative chores).
     * "social": Stakeholder Alignment & Client Relations (1-on-1s, team syncs, stakeholder check-ins, client relationship building).
     * "academics": Training & Knowledge (ADP product training, policy research, certifications, learning & development).
     * "health": Focus Time & Wellness (uninterrupted focus blocks, mental breaks, personal time).

3. PRECISE DATE & TIME RESOLUTION (CRITICAL):
   - You MUST accurately resolve ANY specific day, date, or future timeframe mentioned:
     * Specific days of the week: "this Thursday", "next Wednesday", "on Friday", "Tuesday morning".
     * Specific calendar dates: "October 24th", "Nov 2nd", "10/28", "November 15".
     * Relative references: "today", "tomorrow", "tonight", "in two weeks".
   - If an EVENT has a specific day/date AND an explicit time (e.g., "next Thursday at 2 PM", "Oct 25 at 10 AM"):
     * Output start_time and end_time in ISO 8601 with timezone offset (e.g. 2026-10-22T14:00:00-04:00).
   - If an EVENT has a specific day/date but NO explicit time (e.g., "Client sync on Thursday", "Payroll review on Oct 25th", "onboarding next Tuesday"):
     * Do NOT leave start_time null and do NOT mark as needs_clarification. Intelligently slot it into standard business hours on that specific target date:
       - Morning requested -> 10:00 AM – 11:00 AM on that target date.
       - Afternoon or unspecified -> 2:00 PM – 3:00 PM on that target date.
       - Set status to "proposed" so it immediately schedules to Google Calendar.
   - If an event is for "tonight" with duration (e.g. "review payroll for 2 hours tonight"):
     * Slot into 19:00 – 21:00 on the reference date with status "proposed".
   - If end time is not stated for an event: default duration to 60 minutes.
   - For TASKS with a specific date (e.g., "send migration checklist by Friday", "tax review by Oct 28"):
     * Output due_date as YYYY-MM-DD for that exact date. start_time and end_time MUST be null for tasks.

4. WRITE A PROFESSIONAL, HIGH-CLARITY WHATSAPP CONFIRMATION:
   - Embody the Offload brand for ADP professionals: empowering, clear, stress-relieving.
   - Explicitly confirm what was offloaded (meetings scheduled with date/time, tasks queued with due dates).
   - Mention the business impact (e.g. "✨ Offloaded! Scheduled your Client Sync for Thursday, Oct 22 at 2:00 PM and added 'Send payroll checklist' to Implementation Tasks due Friday.").

5. QUESTIONS & AGENDA QUERIES:
   - If the user is asking what's on their schedule or what's lined up for the rest of the day (e.g., "what's lined up today?", "show my schedule"):
     * Set activities to empty list [].
     * Set needs_clarification to false.
     * In whatsapp_reply, answer conversationally with their agenda summary or encouraging status.

OUTPUT FORMAT:
Return pure JSON matching this exact schema:
{
  "summary": "Short 1-line summary of captured commitments",
  "whatsapp_reply": "Professional WhatsApp confirmation message",
  "activities": [
    {
      "type": "event" | "task",
      "title": "Clean concise title (e.g. 'Delta Airlines · Implementation Sync')",
      "category": "career" | "admin" | "social" | "academics" | "health",
      "start_time": "ISO 8601 string or null",
      "end_time": "ISO 8601 string or null",
      "due_date": "YYYY-MM-DD or null",
      "duration_minutes": integer or null,
      "status": "proposed" | "needs_clarification",
      "clarification_needed": null
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
