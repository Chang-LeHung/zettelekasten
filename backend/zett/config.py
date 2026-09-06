import os
from pathlib import Path

USER_DATA_DIR = Path.home() / ".zett"


class Settings:
    database_path: Path = Path(os.getenv("ZETT_DATABASE_PATH", USER_DATA_DIR / "cards.db"))
    agent_database_path: Path = Path(os.getenv("ZETT_AGENT_DATABASE_PATH", USER_DATA_DIR / "agent.db"))
    asset_directory: Path = Path(os.getenv("ZETT_ASSET_DIR", USER_DATA_DIR / "assets"))
    max_asset_size_bytes: int = int(os.getenv("ZETT_MAX_ASSET_SIZE_BYTES", str(25 * 1024 * 1024)))
    log_directory: Path = Path(os.getenv("ZETT_LOG_DIR", USER_DATA_DIR / "logs"))
    log_level: str = os.getenv("ZETT_LOG_LEVEL", "INFO").upper()
    host: str = os.getenv("ZETT_HOST", "127.0.0.1")
    port: int = int(os.getenv("ZETT_PORT", "6280"))
    cors_origins: str = os.getenv("ZETT_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    agent_context_max_tokens: int = int(os.getenv("ZETT_AGENT_CONTEXT_MAX_TOKENS", "128000"))
    agent_keep_recent_tokens: int = int(os.getenv("ZETT_AGENT_KEEP_RECENT_TOKENS", "32000"))
    agent_max_tool_rounds: int = int(os.getenv("ZETT_AGENT_MAX_TOOL_ROUNDS", "12"))
    shell_timeout_seconds: int = int(os.getenv("ZETT_SHELL_TIMEOUT_SECONDS", "30"))
    max_tool_output_characters: int = int(os.getenv("ZETT_MAX_TOOL_OUTPUT_CHARACTERS", "50000"))

    @property
    def origins(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


settings = Settings()
