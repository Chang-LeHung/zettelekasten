import os
from pathlib import Path


USER_DATA_DIR = Path.home() / ".knowledge_cards"


class Settings:
    database_path: Path = Path(os.getenv("CARDS_DATABASE_PATH", USER_DATA_DIR / "cards.db"))
    host: str = os.getenv("CARDS_HOST", "127.0.0.1")
    port: int = int(os.getenv("CARDS_PORT", "8000"))
    cors_origins: str = os.getenv("CARDS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")

    @property
    def origins(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


settings = Settings()
