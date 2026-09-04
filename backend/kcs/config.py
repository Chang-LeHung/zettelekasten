import os
from pathlib import Path

USER_DATA_DIR = Path.home() / ".knowledge_cards"


class Settings:
    database_path: Path = Path(os.getenv("KCS_DATABASE_PATH", USER_DATA_DIR / "cards.db"))
    asset_directory: Path = Path(os.getenv("KCS_ASSET_DIR", USER_DATA_DIR / "assets"))
    max_asset_size_bytes: int = int(os.getenv("KCS_MAX_ASSET_SIZE_BYTES", str(25 * 1024 * 1024)))
    log_directory: Path = Path(os.getenv("KCS_LOG_DIR", USER_DATA_DIR / "logs"))
    log_level: str = os.getenv("KCS_LOG_LEVEL", "INFO").upper()
    host: str = os.getenv("KCS_HOST", "127.0.0.1")
    port: int = int(os.getenv("KCS_PORT", "6280"))
    cors_origins: str = os.getenv("KCS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    compaction_trigger_tokens: int = int(os.getenv("KCS_COMPACTION_TRIGGER_TOKENS", "24000"))
    compaction_recent_messages: int = int(os.getenv("KCS_COMPACTION_RECENT_MESSAGES", "12"))
    compaction_min_messages: int = int(os.getenv("KCS_COMPACTION_MIN_MESSAGES", "8"))
    agent_max_tool_rounds: int = int(os.getenv("KCS_AGENT_MAX_TOOL_ROUNDS", "12"))
    shell_timeout_seconds: int = int(os.getenv("KCS_SHELL_TIMEOUT_SECONDS", "30"))
    max_tool_output_characters: int = int(os.getenv("KCS_MAX_TOOL_OUTPUT_CHARACTERS", "50000"))

    @property
    def origins(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


settings = Settings()
