from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


class Source(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str | None = Field(default=None, max_length=200)
    cwd: str | None = Field(default=None, max_length=1000)
    host: str | None = Field(default=None, max_length=200)


class Option(BaseModel):
    id: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9._-]+$")
    label: str = Field(min_length=1, max_length=80)
    value: str | None = Field(default=None, max_length=4000)


class RequestIn(BaseModel):
    id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    thread_id: str = Field(min_length=1, max_length=300)
    markdown: str = Field(min_length=1, max_length=30000)
    options: list[Option] = Field(default_factory=list, max_length=8)
    source: Source | None = None

    @model_validator(mode="after")
    def unique_options(self):
        if not self.markdown.strip():
            raise ValueError("markdown must contain text")
        if len({o.id for o in self.options}) != len(self.options):
            raise ValueError("option ids must be unique")
        return self


class NotificationIn(BaseModel):
    id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    thread_id: str = Field(min_length=1, max_length=300)
    markdown: str = Field(min_length=1, max_length=30000)
    source: Source | None = None


class CloseIn(BaseModel):
    thread_id: str = Field(min_length=1, max_length=300)


class ReceiptIn(BaseModel):
    status: Literal["accepted", "failed", "unknown"]
    detail: str = Field(default="", max_length=2000)
