"""Small shared publication lock for the daily evidence/narrative chain."""
from __future__ import annotations

from contextlib import contextmanager
import errno
import os
import time
from pathlib import Path
from typing import Iterator

LOCK_RETRIES = 5
LOCK_RETRY_DELAY_SECONDS = 0.2

try:  # macOS/Linux local runtime; the no-op fallback keeps read-only tests portable.
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]


@contextmanager
def daily_publication_lock(root: Path | str) -> Iterator[None]:
    lock_root = Path(root).expanduser().resolve()
    lock_root.mkdir(parents=True, exist_ok=True)
    if fcntl is None:  # pragma: no cover
        yield
        return
    fd = os.open(lock_root / ".daily-publication.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        _acquire(fd)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _acquire(fd: int, *, attempts: int = LOCK_RETRIES, delay: float = LOCK_RETRY_DELAY_SECONDS) -> None:
    """Blocking exclusive flock, tolerating macOS's spurious EDEADLK.

    macOS reports EDEADLK (errno 11, "Resource deadlock avoided") for ordinary
    contention here, not just for real cycles; a raw blocking flock turned that
    into a whole failed run. Retry briefly, then fail loudly rather than
    pretending the lock was taken.
    """
    for attempt in range(1, attempts + 1):
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            return
        except OSError as exc:
            if exc.errno != errno.EDEADLK or attempt == attempts:
                raise
            time.sleep(delay * attempt)
