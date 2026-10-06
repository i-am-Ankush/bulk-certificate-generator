import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Runtime configuration. Every value can be overridden via environment variables."""

    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./certgen.db")
    )
    storage_dir: Path = field(
        default_factory=lambda: Path(os.getenv("STORAGE_DIR", "./storage"))
    )
    max_recipients: int = field(
        default_factory=lambda: int(os.getenv("MAX_RECIPIENTS", "1000"))
    )
