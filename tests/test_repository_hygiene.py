from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import check_repository_hygiene as hygiene


class RepositoryHygieneTests(unittest.TestCase):
    def test_current_repository_passes(self) -> None:
        self.assertEqual(hygiene.audit(), [])

    def test_new_large_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "new-result.jsonl"
            path.write_bytes(b"x" * (hygiene.MAX_TRACKED_BYTES + 1))
            with mock.patch.object(hygiene, "tracked_paths", return_value=[path]):
                self.assertEqual(len(hygiene.audit(root)), 1)

    def test_small_fixture_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "fixture.json"
            path.write_text("{}", encoding="utf-8")
            with mock.patch.object(hygiene, "tracked_paths", return_value=[path]):
                self.assertEqual(hygiene.audit(root), [])


if __name__ == "__main__":
    unittest.main()
