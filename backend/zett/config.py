import os
from pathlib import Path

USER_DATA_DIR = Path.home() / ".zettelekasten"


class Settings:
    # Every persisted object path is relative to this one root.
    storage_root: Path = Path(os.getenv("ZETT_STORAGE_ROOT", USER_DATA_DIR))
    database_path: Path = Path(os.getenv("ZETT_DATABASE_PATH", storage_root / "zett.db"))
    agent_database_path: Path = Path(os.getenv("ZETT_AGENT_DATABASE_PATH", storage_root / "agent.db"))
    provider_key_path: Path = Path(os.getenv("ZETT_PROVIDER_KEY_PATH", storage_root / "provider.key"))
    max_asset_size_bytes: int = int(os.getenv("ZETT_MAX_ASSET_SIZE_BYTES", str(250 * 1024 * 1024)))
    log_directory: Path = Path(os.getenv("ZETT_LOG_DIR", storage_root / "logs"))
    log_level: str = os.getenv("ZETT_LOG_LEVEL", "INFO").upper()
    host: str = os.getenv("ZETT_HOST", "127.0.0.1")
    port: int = int(os.getenv("ZETT_PORT", "6280"))
    process_supervisor_enabled: bool = os.getenv("ZETT_PROCESS_SUPERVISOR_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    supervisor_poll_seconds: float = float(os.getenv("ZETT_SUPERVISOR_POLL_SECONDS", "5"))
    heartbeat_interval_seconds: float = float(os.getenv("ZETT_HEARTBEAT_INTERVAL_SECONDS", "5"))
    heartbeat_timeout_seconds: float = float(os.getenv("ZETT_HEARTBEAT_TIMEOUT_SECONDS", "20"))
    worker_processes: int = int(os.getenv("ZETT_WORKER_PROCESSES", "1"))


settings = Settings()
