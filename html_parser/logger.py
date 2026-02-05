"""
Logging configuration for the HTML Parser framework.
"""

import logging
import sys
from typing import Optional


def setup_logger(
    name: str = "html_parser",
    level: int = logging.INFO,
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    Set up and return a logger instance.

    Args:
        name: Logger name
        level: Logging level (default: INFO)
        log_file: Optional file path for logging

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Format: timestamp - module - level - message
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# Default logger instance
logger = setup_logger()


def get_module_logger(module_name: str) -> logging.Logger:
    """
    Get a child logger for a specific module.

    Args:
        module_name: Name of the module (e.g., 'analyzer', 'extractor')

    Returns:
        Child logger instance
    """
    return logging.getLogger(f"html_parser.{module_name}")
