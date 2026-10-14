"""
Centralized System Logging Module for Shipping Watch
Streams logs to console and persistently writes to logs/system_monitor.log.
Captures timestamps, log level, process context (CONTAINER vs HOST), return codes,
downloads, model queries, and full exception tracebacks.
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Determine if running inside container or on host
IS_CONTAINER = os.path.exists("/.dockerenv") or os.getenv("CONTAINER_MODE") == "1"
SOURCE_TAG = "CONTAINER" if IS_CONTAINER else "HOST"

# Unified log file destinations
LOG_DIR = os.getenv("LOG_DIR", "logs")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

PRIMARY_LOG_FILE = os.path.join(LOG_DIR, "system_monitor.log")
OUTPUT_LOG_FILE = os.path.join(OUTPUT_DIR, "system_monitor.log")


class UnifiedLogger:
    """
    Thread-safe unified logger writing structured logs to console and disk.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(UnifiedLogger, cls).__new__(cls)
            cls._instance._setup()
        return cls._instance

    def _setup(self):
        self.logger = logging.getLogger("ShippingWatchSystem")
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False

        # Clear existing handlers if any
        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        # Custom format: [TIMESTAMP] [LEVEL] [SOURCE] [MODULE] Message
        log_format = logging.Formatter(
            fmt=f"[%(asctime)s.%(msecs)03d] [%(levelname)-7s] [{SOURCE_TAG}] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # 1. Console Stream Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(log_format)
        self.logger.addHandler(console_handler)

        # 2. Rotating File Handler (primary logs/system_monitor.log)
        try:
            file_handler = RotatingFileHandler(
                PRIMARY_LOG_FILE,
                maxBytes=15 * 1024 * 1024,  # 15 MB
                backupCount=5,
                encoding="utf-8"
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(log_format)
            self.logger.addHandler(file_handler)
        except Exception as e:
            sys.stderr.write(f"Warning: Could not bind primary log file: {e}\n")

        # 3. Mirroring File Handler (output/system_monitor.log for mounted volume access)
        try:
            mirror_handler = RotatingFileHandler(
                OUTPUT_LOG_FILE,
                maxBytes=15 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8"
            )
            mirror_handler.setLevel(logging.DEBUG)
            mirror_handler.setFormatter(log_format)
            self.logger.addHandler(mirror_handler)
        except Exception as e:
            sys.stderr.write(f"Warning: Could not bind mirror log file: {e}\n")

        self.info("Unified logger initialized successfully.")

    def info(self, msg: str, module: str = "SYSTEM"):
        self.logger.name = module
        self.logger.info(msg)

    def debug(self, msg: str, module: str = "SYSTEM"):
        self.logger.name = module
        self.logger.debug(msg)

    def warning(self, msg: str, module: str = "SYSTEM"):
        self.logger.name = module
        self.logger.warning(msg)

    def error(self, msg: str, exc: Exception = None, module: str = "SYSTEM"):
        self.logger.name = module
        if exc:
            self.logger.error(f"{msg} | Exception: {type(exc).__name__}: {str(exc)}", exc_info=True)
        else:
            self.logger.error(msg)

    def log_process(self, process_name: str, return_code: int, stdout_snippet: str = "", stderr_snippet: str = ""):
        """Logs process exit codes and return messages."""
        if return_code == 0:
            self.info(f"Process '{process_name}' completed successfully (exit code 0).", module="PROCESS")
        else:
            self.error(
                f"Process '{process_name}' failed with exit code {return_code}. Stderr: {stderr_snippet}",
                module="PROCESS"
            )


# Global singleton logger instance
logger = UnifiedLogger()
