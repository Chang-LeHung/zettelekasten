from pydantic import BaseModel, ConfigDict


class AIProviderRuntime(BaseModel):
    """Session-independent provider identity used by model consumers."""

    model_config = ConfigDict(frozen=True)

    provider: str
    model: str
