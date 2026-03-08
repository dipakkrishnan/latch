import logging
import os
import sys


def env_flag(name):
    return os.environ.get(name, "").lower() in ("1", "true", "yes", "on")


def debug_enabled(local_flag=None):
    if local_flag is not None:
        return local_flag
    return env_flag("LATCH_DEBUG")


def init_logger(name, *, debug=False):
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("[%(name)s %(asctime)s] %(message)s"))
        logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    return logger
