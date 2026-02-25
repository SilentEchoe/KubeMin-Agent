"""Cron job type definitions."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ScheduleType(Enum):
    """Type of schedule for a cron job."""

    CRON = "cron"       # Standard cron expression
    EVERY = "every"     # Interval in seconds
    AT = "at"           # Specific datetime


@dataclass
class CronJob:
    """A scheduled job definition."""

    id: str
    name: str
    message: str
    schedule_type: ScheduleType
    schedule_value: str
    channel: str = ""
    chat_id: str = ""
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_run: str | None = None
