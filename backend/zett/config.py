import os
from pathlib import Path

USER_DATA_DIR = Path.home() / ".zett"


class Settings:
    database_path: Path = Path(os.getenv("ZETT_DATABASE_PATH", USER_DATA_DIR / "zett.db"))
    agent_database_path: Path = Path(os.getenv("ZETT_AGENT_DATABASE_PATH", USER_DATA_DIR / "agent.db"))
    asset_directory: Path = Path(os.getenv("ZETT_ASSET_DIR", USER_DATA_DIR / "assets"))
    artifact_directory: Path = USER_DATA_DIR / "artifacts"
    provider_key_path: Path = Path(os.getenv("ZETT_PROVIDER_KEY_PATH", USER_DATA_DIR / "provider.key"))
    max_asset_size_bytes: int = int(os.getenv("ZETT_MAX_ASSET_SIZE_BYTES", str(25 * 1024 * 1024)))
    log_directory: Path = Path(os.getenv("ZETT_LOG_DIR", USER_DATA_DIR / "logs"))
    log_level: str = os.getenv("ZETT_LOG_LEVEL", "INFO").upper()
    host: str = os.getenv("ZETT_HOST", "127.0.0.1")
    port: int = int(os.getenv("ZETT_PORT", "6280"))


settings = Settings()
