"""Read models for model request and token activity."""

from datetime import date

from pydantic import BaseModel, Field


class UsageActivityDayRecord(BaseModel):
    """Daily token counters returned by the usage activity storage boundary."""

    date: date
    requests: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_read_tokens: int = Field(ge=0)
    cache_write_tokens: int = Field(ge=0)
    reasoning_tokens: int = Field(ge=0)

    @property
    def total_tokens(self) -> int:
        """Return input plus output tokens for this day."""
        return self.input_tokens + self.output_tokens


class ModelUsageActivitySeries(BaseModel):
    """Daily usage activity grouped by one provider and model pair."""

    provider: str | None = None
    model: str | None = None
    days: list[UsageActivityDayRecord] = Field(default_factory=list)
