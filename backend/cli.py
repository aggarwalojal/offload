#!/usr/bin/env python3
"""
Interactive CLI for TimeSlice AI Agent.
Allows testing WhatsApp brain dumps locally with real-time AI parsing and terminal visualization.
"""

import sys
from pathlib import Path
from datetime import datetime
import pytz

# Bootstrap sys.path to find backend modules
REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from backend.schemas import ParseRequest, ActivityType
from backend.ai.parser import parse_brain_dump
from backend.ai.planner import validate_and_plan

# ANSI color codes for terminal display
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
PURPLE = "\033[95m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

CATEGORY_ICONS = {
    "academics": f"{BLUE}📚 Academics{RESET}",
    "career": f"{PURPLE}💼 Career{RESET}",
    "social": f"{GREEN}🎉 Social{RESET}",
    "health": f"{CYAN}🏃 Health{RESET}",
    "admin": f"{YELLOW}📝 Admin{RESET}",
}

SAMPLE_PROMPTS = [
    "I need to study Java for two hours tonight, apply to an internship tomorrow, and go to my club meeting Friday at 7 PM.",
    "Hit the gym tomorrow at 8 AM for an hour, finish MATH 1554 homework by Thursday, and grab boba with Sarah at 4 PM on Saturday.",
    "Pay my rent tomorrow, schedule dentist appointment next Monday at 10 AM, and prep for the Amazon technical interview tonight from 6 to 8.",
]


def print_banner():
    print(f"\n{BOLD}{CYAN}===================================================={RESET}")
    print(f"{BOLD}{CYAN}        🍕 TimeSlice — AI Agent Terminal Tester     {RESET}")
    print(f"{BOLD}{CYAN}===================================================={RESET}")
    print(f"{DIM}Type a chaotic brain dump, or 'sample' for examples, or 'exit' to quit.{RESET}\n")


def display_results(response):
    print(f"\n{BOLD}🤖 AI Analysis & Summary:{RESET} {response.summary}")
    print(f"\n{BOLD}📲 Simulated WhatsApp Reply:{RESET}")
    print(f"   ┌────────────────────────────────────────────────────────┐")
    for line in response.whatsapp_reply.split("\n"):
        print(f"   │ {line}")
    print(f"   └────────────────────────────────────────────────────────┘\n")

    print(f"{BOLD}📋 Extracted Activities ({len(response.activities)}):{RESET}")
    print(f"{'─' * 60}")

    total_event_minutes = 0
    category_minutes = {}

    for idx, act in enumerate(response.activities, 1):
        type_badge = f"{BOLD}[EVENT 📅]{RESET}" if act.type == ActivityType.event else f"{BOLD}[TASK 📋]{RESET}"
        cat_str = CATEGORY_ICONS.get(act.category.value, act.category.value)

        print(f" {idx}. {type_badge} {BOLD}{act.title}{RESET}")
        print(f"    • Category: {cat_str}")

        if act.type == ActivityType.event:
            start_str = act.start_time.strftime("%a %b %d, %I:%M %p") if act.start_time else "TBD"
            end_str = act.end_time.strftime("%I:%M %p") if act.end_time else "TBD"
            duration = act.duration_minutes or 0
            print(f"    • Schedule: {start_str} → {end_str} ({duration} mins)")
            total_event_minutes += duration
            category_minutes[act.category.value] = category_minutes.get(act.category.value, 0) + duration
        else:
            due = act.due_date or "No specific date"
            print(f"    • Due Date: {due}")

        if act.clarification_needed:
            print(f"    • {YELLOW}⚠️ Clarification:{RESET} {act.clarification_needed}")

        print(f"{'─' * 60}")

    if total_event_minutes > 0:
        print(f"\n{BOLD}📊 Screen Time Slice Distribution (Planned Time: {total_event_minutes / 60:.1f} hrs):{RESET}")
        for cat, mins in sorted(category_minutes.items(), key=lambda x: x[1], reverse=True):
            pct = (mins / total_event_minutes) * 100
            bar = "█" * int(pct / 5)
            cat_display = CATEGORY_ICONS.get(cat, cat)
            print(f"   {cat_display:<22} {bar:<20} {pct:5.1f}% ({mins / 60:.1f} hrs)")
    print()


def main():
    print_banner()

    while True:
        try:
            user_input = input(f"{BOLD}{GREEN}💬 Brain Dump >> {RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting TimeSlice CLI. Goodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "q"):
            print("Goodbye!")
            break

        if user_input.lower() == "sample":
            print(f"\n{BOLD}Select a sample brain dump:{RESET}")
            for i, s in enumerate(SAMPLE_PROMPTS, 1):
                print(f"  [{i}] {s}")
            choice = input(f"{DIM}Enter number (1-3) or press Enter to cancel: {RESET}").strip()
            if choice in ("1", "2", "3"):
                user_input = SAMPLE_PROMPTS[int(choice) - 1]
                print(f"\n{DIM}Selected: \"{user_input}\"{RESET}")
            else:
                continue

        print(f"\n{DIM}⏳ Parsing with Gemini AI...{RESET}")
        try:
            req = ParseRequest(
                message=user_input,
                timezone="America/New_York",
                current_time=datetime.now(pytz.timezone("America/New_York")),
            )
            res = parse_brain_dump(req)
            validated, _ = validate_and_plan(res.activities)
            res.activities = validated
            display_results(res)
        except Exception as e:
            print(f"{YELLOW}❌ Error: {e}{RESET}\n")


if __name__ == "__main__":
    main()
