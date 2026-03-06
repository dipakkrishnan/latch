import logging
import os
import sys


def env_flag(name):
    return os.environ.get(name, "").lower() in ("1", "true", "yes", "on")


def init_logger(name, *, debug=False):
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("[%(name)s %(asctime)s] %(message)s"))
        logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    return logger
