"""Logging setup and utilities."""

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: Path, config: dict) -> None:
    """Configure logging with file rotation."""
    log_dir.mkdir(parents=True, exist_ok=True)

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

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for existing_handler in list(root_logger.handlers):
        root_logger.removeHandler(existing_handler)
    root_logger.addHandler(handler)

    def _log_uncaught_exception(exc_type, exc_value, exc_traceback) -> None:
        if exc_type is KeyboardInterrupt:
            return
        logging.getLogger("launcher").critical(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    def _log_thread_exception(args: threading.ExceptHookArgs) -> None:
        logging.getLogger("launcher").critical(
            "Uncaught thread exception in %s",
            args.thread.name if args.thread else "unknown",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = _log_uncaught_exception
    threading.excepthook = _log_thread_exception
