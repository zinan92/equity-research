"""Small shared publication lock for the daily evidence/narrative chain."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
from typing import Iterator

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
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
