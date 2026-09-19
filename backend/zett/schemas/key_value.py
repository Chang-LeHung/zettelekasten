"""Read models for versioned JSON key-value records."""

from datetime import datetime

from pydantic import BaseModel, Field

from .common import JsonValue


class KeyValueRecord(BaseModel):
    """One current record returned by the versioned key-value boundary."""

    id: str = Field(description="Stable UUIDv7 identity retained across updates")
    key: str = Field(description="Unique indexed logical key")
    value: JsonValue = Field(description="JSON-compatible value decoded from SQLite text")
    version: int = Field(ge=1, description="Per-key revision number starting at one")
    created_at: datetime = Field(description="UTC time when this key was created")
    updated_at: datetime = Field(description="UTC time when this value was last updated")
