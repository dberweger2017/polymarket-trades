# market_sync/util.py
import time
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

def now_ts() -> int:
    ts = int(time.time())
    logger.debug("now_ts=%d", ts)
    return ts

def iso_parse(value) -> Optional[str]:
    if value is None:
        logger.debug("iso_parse: value is None")
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            v = int(value)
            if v > 10**12:
                v = v / 1000.0
            dt = datetime.fromtimestamp(v, tz=timezone.utc)
            iso = dt.isoformat()
            logger.debug("iso_parse: numeric %s -> %s", value, iso)
            return iso
        if isinstance(value, str):
            s = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            iso = dt.isoformat()
            logger.debug("iso_parse: string %s -> %s", value, iso)
            return iso
    except Exception as e:
        logger.exception("iso_parse error for value=%r: %s", value, e)
        return None
    return None

