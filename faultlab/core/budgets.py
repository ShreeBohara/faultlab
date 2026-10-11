"""Declared limits. Every field is optional so a plan states only the caps it enforces."""

from pydantic import Field

from faultlab.core.model import StrictModel


class Caps(StrictModel):
    model_calls: int | None = Field(default=None, ge=0)
    http_attempts: int | None = Field(default=None, ge=0)
    tokens: int | None = Field(default=None, ge=0)
    dollars: float | None = Field(default=None, ge=0)
    wall_seconds: float | None = Field(default=None, ge=0)
    ticks: int | None = Field(default=None, ge=0)
