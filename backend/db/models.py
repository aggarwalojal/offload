"""Eva's boundary models; proposed AI integration contract is in docs/eva-integration.md."""
from datetime import date, datetime
from enum import Enum
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class Category(str, Enum):
    academics = "academics"
    career = "career"
    social = "social"
    health = "health"
    admin = "admin"


class Activity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    type: Literal["event", "task"]
    title: str = Field(min_length=1, max_length=300)
    category: Category
    start_time: AwareDatetime | None = None
    end_time: AwareDatetime | None = None
    due_date: date | None = None
    status: Literal["proposed", "needs_clarification", "executing", "completed", "failed"] = "proposed"
    external_id: str | None = Field(default=None, max_length=1024)
    source: Literal["whatsapp"] = "whatsapp"

    @field_validator("title", "external_id")
    @classmethod
    def nonblank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Titles and external IDs cannot be blank")
        return value

    @model_validator(mode="after")
    def valid_times(self):
        if self.type == "task" and (self.start_time or self.end_time):
            raise ValueError("Tasks do not carry scheduled durations")
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError("Provide both event times or neither")
        if self.start_time and self.end_time <= self.start_time:
            raise ValueError("Event end must follow start")
        if self.status in {"executing", "completed"} and self.type == "event" and not self.start_time:
            raise ValueError("Synced events require start and end")
        if self.status == "completed" and not self.external_id:
            raise ValueError("Successful sync requires a Google ID")
        return self

    def ready_to_create(self) -> bool:
        return (self.status == "proposed" and not self.external_id
                and (self.type == "task" or self.start_time is not None))


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actions: list[Activity] = Field(default_factory=list, max_length=30)
    reply: str = Field(default="", max_length=3000)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({a.id for a in self.actions}) != len(self.actions):
            raise ValueError("Action IDs must be unique")
        return self


class User(BaseModel):
    id: UUID
    whatsapp_number: str
    timezone: str = "America/New_York"
    whatsapp_opt_in: bool = False
    morning_enabled: bool = False
    evening_enabled: bool = False
    morning_time: str = "08:00:00"
    evening_time: str = "21:00:00"
    last_inbound_at: AwareDatetime | None = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        ZoneInfo(value)
        return value
