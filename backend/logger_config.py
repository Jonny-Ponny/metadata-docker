# logger_config.py
import logging
import logging.handlers
import os
from pathlib import Path

LOG_DIR = Path('/logs')
LOG_DIR.mkdir(exist_ok=True, parents=True)

class AppLogger:
    """Application logger singleton"""
    _instance = None
    _logger = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup_logger()
        return cls._instance

    def _setup_logger(self):
        """Setup the logger with file and console handlers"""
        # Create logger
        self._logger = logging.getLogger('app')
        self._logger.setLevel(logging.INFO)

        # Avoid adding handlers multiple times
        if self._logger.handlers:
            return

        # Formatter
        log_formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        try:
            # File handler with rotation
            file_handler = logging.handlers.RotatingFileHandler(
                LOG_DIR / "app.log",
                maxBytes=10_000_000,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setFormatter(log_formatter)
            self._logger.addHandler(file_handler)
        except Exception as e:
            # Log to console if file handler fails (e.g., permission issues)
            print(f"Warning: Could not create file handler: {e}")

        # Console handler (replaces print)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_formatter)
        self._logger.addHandler(console_handler)

    @property
    def logger(self):
        return self._logger

# Create a global instance
app_logger = AppLogger().logger

# Convenience functions
def get_logger():
    return app_logger

def log_info(msg):
    app_logger.info(msg)

def log_error(msg):
    app_logger.error(msg)

def log_warning(msg):
    app_logger.warning(msg)

def log_debug(msg):
    app_logger.debug(msg)