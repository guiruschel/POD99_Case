"""Structured (JSON) logging for Glue jobs, so CloudWatch Logs stay queryable."""
import json
import logging
import sys


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_event(logger: logging.Logger, message: str, **fields) -> None:
    """Logs a single JSON line: {"message": ..., <extra fields>}."""
    logger.info(json.dumps({"message": message, **fields}))
