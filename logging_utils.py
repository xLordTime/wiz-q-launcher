"""Logging setup and utilities."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: Path, config: dict) -> None:
    """Configure logging with file rotation."""
    log_level = config.get("log_level", "INFO").upper()
    level = getattr(logging, log_level, logging.INFO)

    log_file = log_dir / "launcher.log"
    handler = RotatingFileHandler(
        log_file,
        maxBytes=int(config.get("log_max_bytes", 1048576)),
        backupCount=int(config.get("log_backup_count", 5)),
        encoding="utf-8",
    )

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)

    logging.basicConfig(level=level, handlers=[handler])
