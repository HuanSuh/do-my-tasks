"""Logging configuration for DMT."""

from __future__ import annotations

import logging
import sys


def setup_logger(verbose: bool = False) -> logging.Logger:
    """Set up and return the DMT logger."""
    logger = logging.getLogger("dmt")

    if logger.handlers:
        return logger

    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)

    if not verbose:
        fmt = "%(levelname)s: %(message)s"
    else:
        fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    formatter = logging.Formatter(fmt)
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    return logger


def get_logger() -> logging.Logger:
    """Get the DMT logger."""
    return logging.getLogger("dmt")
