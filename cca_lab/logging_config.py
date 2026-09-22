"""Application-only logging; never enable transport payload logging."""
import logging
import os


def configure_logging():
    logger = logging.getLogger("cca_lab")
    level = os.getenv("CCA_LAB_LOG_LEVEL", "INFO").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        level = "INFO"
    logger.setLevel(level)
    if not any(getattr(h, "_cca_lab", False) for h in logger.handlers):
        handler = logging.StreamHandler()
        handler._cca_lab = True
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
