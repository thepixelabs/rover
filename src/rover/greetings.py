"""Time-of-day greeting system for rover.

Structure mirrors altergo's altergo_greetings.py: 8 time windows,
time-seeded random so the greeting is stable within the same minute,
and a day-of-week nature icon.

Public API
----------
pick_greeting(now=None) -> tuple[str, str]   # (emoji, text)
pick_icon(now=None) -> str                   # nature emoji by weekday
"""

import random
import time
from datetime import datetime

# ---------------------------------------------------------------------------
# Time windows
# ---------------------------------------------------------------------------

_WINDOWS: list[tuple[str, range]] = [
    ("dead_of_night",   range(0,  3)),   # 00-02
    ("late_night",      range(3,  6)),   # 03-05
    ("early_morning",   range(6,  9)),   # 06-08
    ("morning",         range(9,  12)),  # 09-11
    ("midday",          range(12, 14)),  # 12-13
    ("afternoon",       range(14, 17)),  # 14-16
    ("evening",         range(17, 20)),  # 17-19
    ("night",           range(20, 24)),  # 20-23
]

_GREETINGS: dict[str, list[tuple[str, str]]] = {
    "dead_of_night": [
        ("🌑", "The agents don't sleep. Apparently neither do you."),
        ("🌑", "SSHing in at this hour. The codebase fears you."),
        ("🌑", "You and the cron jobs. The only ones awake."),
    ],
    "late_night": [
        ("🌒", "Either you never went to bed or you're very, very dedicated."),
        ("🌒", "Your agents worked the night shift. You didn't miss much. Maybe."),
        ("🌒", "Still on? The queue is judging you. Fondly."),
    ],
    "early_morning": [
        ("🌅", "Up before the standup. Respect."),
        ("🌅", "Checking agents before coffee. Bold strategy."),
        ("🌅", "The logs are fresh. You're fresher. Debatable."),
    ],
    "morning": [
        ("☀️",  "Good morning. Your agents have opinions about last night's commits."),
        ("☀️",  "Fresh session, fresh problems. Let's see what burned down."),
        ("☀️",  "Morning check-in. The queue waited up for you."),
    ],
    "midday": [
        ("🌤️", "Lunch check-in. At least one agent is definitely stuck."),
        ("🌤️", "Halfway through the day. The queue has thoughts."),
        ("🌤️", "Mid-day recon from wherever you are. The agents are managing."),
    ],
    "afternoon": [
        ("🌥️", "Afternoon from the road. Your Mac is holding it together. Probably."),
        ("🌥️", "Phoning in from wherever you are. The agents are covering for you."),
        ("🌥️", "SSH drop + reconnect. Classic afternoon move."),
    ],
    "evening": [
        ("🌆", "Off hours, still shipping. That's the job."),
        ("🌆", "Evening recon. Check what finished, dread what didn't."),
        ("🌆", "End of day, but the queue didn't get the memo."),
    ],
    "night": [
        ("🌃", "Late session check. If it's blocked, it waited this long, it can wait till morning."),
        ("🌃", "Night mode engaged. Minimal context, maximum efficiency."),
        ("🌃", "One last look before you close the laptop. You said that an hour ago."),
    ],
}

# Day-of-week nature icons: Monday=0 through Sunday=6
NATURE_ICONS: list[str] = ["🌊", "🌿", "⛰️", "🌳", "🔥", "🌄", "🌑"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _window_for_hour(hour: int) -> str:
    for name, rng in _WINDOWS:
        if hour in rng:
            return name
    # Fallback — should never be reached for valid hours 0-23.
    return "night"


def _seeded_rng() -> random.Random:
    """Return an RNG seeded to the current minute so picks are stable."""
    seed = int(time.time() // 60)
    return random.Random(seed)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def pick_greeting(now: datetime | None = None) -> tuple[str, str]:
    """Return (emoji, text) for the current time window.

    Pass `now` explicitly in tests to get deterministic output.
    """
    if now is None:
        now = datetime.now()

    window = _window_for_hour(now.hour)
    candidates = _GREETINGS[window]
    rng = _seeded_rng()
    return rng.choice(candidates)


def pick_icon(now: datetime | None = None) -> str:
    """Return a nature emoji based on day of week (Monday=0, Sunday=6)."""
    if now is None:
        now = datetime.now()
    return NATURE_ICONS[now.weekday()]
