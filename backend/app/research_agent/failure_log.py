"""Best-effort private supervisor diagnostics, independent of SQLite availability."""
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from threading import Lock
from datetime import datetime, timezone
from .event_diagnostics import private_trace

MAX_BYTES = 262144
BACKUPS = 2
_lock = Lock()


def record(database, exception):
    """Never mask the original failure or record exception arguments/provider output.

    One backend coordinator owns this bounded log. It is operator-only, not an API
    or replay source; a logged failure does not mean a DB transition committed.
    """
    handler = None
    try:
        with _lock:
            folder = Path(database.path).parent / 'research-private'
            if folder.is_symlink():
                return False
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(folder, 0o700)
            path = folder / 'coordinator-failures.jsonl'
            if any(p.is_symlink() for p in [path, *[Path(str(path)+'.'+str(i)) for i in range(1, BACKUPS+1)]]):
                return False
            fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
            os.close(fd)
            os.chmod(path, 0o600)
            # No logging framework propagation, console traceback or raw message.
            handler = RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding='utf-8')
            document = dict(timestamp=datetime.now(timezone.utc).isoformat(),
                            component='research.director', error_code='COORDINATOR_CYCLE_FAILED',
                            state_committed=False, trace=private_trace(exception))
            line = json.dumps(document, allow_nan=False)
            item = logging.LogRecord('research.private', logging.ERROR, '', 0, line, (), None)
            # Call the underlying operations ourselves: logging.handleError can
            # print the record and internal exception if disk writes fail.
            if handler.shouldRollover(item):
                handler.doRollover()
                os.chmod(path, 0o600)
            handler.stream.write(line+'\n')
            handler.flush()
            handler.close()
            handler = None
            return True
    except Exception:
        return False
    finally:
        if handler is not None:
            try: handler.close()
            except Exception: pass
