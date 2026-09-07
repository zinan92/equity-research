from __future__ import annotations

import errno
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

import market_regime_runtime as runtime  # noqa: E402


class FileLockDeadlockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.lock_path = Path(self.tmp.name) / "run.lock"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_acquires_after_transient_edeadlk(self) -> None:
        calls = {"n": 0}

        def flaky_flock(descriptor: int, flags: int) -> None:
            calls["n"] += 1
            if calls["n"] <= 2:
                raise OSError(errno.EDEADLK, "Resource deadlock avoided")

        with patch.object(runtime.fcntl, "flock", side_effect=flaky_flock), patch.object(runtime.time, "sleep") as sleep:
            descriptor = runtime._try_file_lock(self.lock_path)
        self.assertIsNotNone(descriptor)
        self.assertEqual(calls["n"], 3)
        self.assertEqual(sleep.call_count, 2)
        os.close(descriptor)

    def test_persistent_edeadlk_reports_busy_instead_of_crashing(self) -> None:
        def always_deadlock(descriptor: int, flags: int) -> None:
            raise OSError(errno.EDEADLK, "Resource deadlock avoided")

        with patch.object(runtime.fcntl, "flock", side_effect=always_deadlock), patch.object(runtime.time, "sleep"):
            self.assertIsNone(runtime._try_file_lock(self.lock_path))
            self.assertTrue(runtime._file_lock_busy(self.lock_path))

    def test_eagain_is_busy_without_retry(self) -> None:
        def would_block(descriptor: int, flags: int) -> None:
            raise BlockingIOError(errno.EAGAIN, "Resource temporarily unavailable")

        with patch.object(runtime.fcntl, "flock", side_effect=would_block), patch.object(runtime.time, "sleep") as sleep:
            self.assertIsNone(runtime._try_file_lock(self.lock_path))
        self.assertEqual(sleep.call_count, 0)

    def test_other_errors_still_raise(self) -> None:
        def broken(descriptor: int, flags: int) -> None:
            raise OSError(errno.EBADF, "Bad file descriptor")

        with patch.object(runtime.fcntl, "flock", side_effect=broken):
            with self.assertRaises(OSError):
                runtime._try_file_lock(self.lock_path)

    def test_real_lock_roundtrip(self) -> None:
        descriptor = runtime._try_file_lock(self.lock_path)
        self.assertIsNotNone(descriptor)
        self.assertTrue(runtime._file_lock_busy(self.lock_path))
        runtime._unlock_file(descriptor)
        self.assertFalse(runtime._file_lock_busy(self.lock_path))


if __name__ == "__main__":
    unittest.main()
