import os
from pathlib import Path

USER_DATA_DIR = Path.home() / ".zettelekasten"

#: Access-log sampling: one line per this many matching requests, defaulting to
#: the liveness endpoints a supervised process polls every few seconds.
DEFAULT_ACCESS_LOG_SAMPLE_RATES = "/api/health=100"


def parse_access_log_sample_rates(value: str) -> dict[str, int]:
    """Parse ``prefix=count`` pairs into access-log sampling rules.

    The first prefix a request path starts with wins, so the most specific rules
    must come first. Missing, unparsable, or non-positive entries are ignored
    rather than failing startup over a log preference.
    """
    rates: dict[str, int] = {}
    for entry in value.split(","):
        prefix, separator, raw_count = entry.partition("=")
        if not separator:
            continue
        try:
            count = int(raw_count)
        except ValueError:
            continue
        if prefix.strip() and count > 0:
            rates[prefix.strip()] = count
    return rates


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
    runtime_state_path: Path = Path(os.getenv("ZETT_RUNTIME_STATE_PATH", storage_root / "runtime.json"))
    process_supervisor_enabled: bool = os.getenv("ZETT_PROCESS_SUPERVISOR_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    supervisor_poll_seconds: float = float(os.getenv("ZETT_SUPERVISOR_POLL_SECONDS", "5"))
    heartbeat_interval_seconds: float = float(os.getenv("ZETT_HEARTBEAT_INTERVAL_SECONDS", "5"))
    heartbeat_timeout_seconds: float = float(os.getenv("ZETT_HEARTBEAT_TIMEOUT_SECONDS", "20"))
    process_watchdog_enabled: bool = os.getenv("ZETT_PROCESS_WATCHDOG_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    process_watchdog_interval_seconds: float = float(os.getenv("ZETT_PROCESS_WATCHDOG_INTERVAL_SECONDS", "5"))
    process_watchdog_failure_threshold: int = int(os.getenv("ZETT_PROCESS_WATCHDOG_FAILURE_THRESHOLD", "3"))
    worker_processes: int = int(os.getenv("ZETT_WORKER_PROCESSES", "1"))
    #: How long ``zett start`` waits for the detached server to bind its port
    #: before reporting a failed background start.
    background_start_timeout_seconds: float = float(os.getenv("ZETT_START_TIMEOUT_SECONDS", "30"))
    #: Path prefix to "log one line per this many requests"; unmatched paths log
    #: every request. Example: "/api/health=100,/api/files=20".
    access_log_sample_rates: dict[str, int] = parse_access_log_sample_rates(
        os.getenv("ZETT_ACCESS_LOG_SAMPLE_RATES", DEFAULT_ACCESS_LOG_SAMPLE_RATES)
    )


settings = Settings()
