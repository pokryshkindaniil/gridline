"""Block until PostgreSQL accepts connections (exponential backoff). Used by container entrypoints."""

from __future__ import annotations

import logging
import os
import sys
import time

from sqlalchemy import create_engine, text

from .config import get_settings
from .logging_setup import configure_logging

log = logging.getLogger("gridline.wait_for_db")


def wait_for_db(timeout: float = 60.0) -> bool:
    engine = create_engine(get_settings().database_url, connect_args={"connect_timeout": 3})
    deadline = time.monotonic() + timeout
    delay, attempt = 0.5, 0
    while True:
        attempt += 1
        try:
            with engine.connect() as conn:
                conn.execute(text("select 1"))
            log.info("database ready", extra={"attempts": attempt})
            return True
        except Exception as exc:
            if time.monotonic() + delay > deadline:
                log.error("database not reachable", extra={"attempts": attempt, "failure_reason": type(exc).__name__})
                return False
            log.warning("waiting for database", extra={"attempt": attempt, "retry_in_s": delay})
            time.sleep(delay)
            delay = min(delay * 2, 5.0)


if __name__ == "__main__":
    configure_logging(get_settings().log_level)
    sys.exit(0 if wait_for_db(float(os.environ.get("WAIT_FOR_DB_TIMEOUT", "60"))) else 1)
