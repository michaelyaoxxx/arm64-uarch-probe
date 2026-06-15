import os
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from arm64_probe.environment.constants import REPOSITORY_ID
from arm64_probe.environment.journal import JournalStore
from arm64_probe.errors import ProbeError


class JournalSecurityTests(unittest.TestCase):
    def store(self, root: Path) -> JournalStore:
        return JournalStore(
            root,
            repository_id=REPOSITORY_ID,
            required_owner_uid=os.getuid(),
            clock=lambda: datetime(2026, 6, 15, tzinfo=UTC),
            transaction_id_factory=lambda: "b" * 32,
        )

    def test_read_only_discovery_does_not_create_missing_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "missing"
            store = self.store(root)

            self.assertEqual(store.unfinished(), ())
            self.assertFalse(root.exists())

    def test_managed_paths_reject_outside_nested_and_symlink_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"
            store = self.store(root)
            root.mkdir(mode=0o755)
            journals = root / "journals"
            journals.mkdir(mode=0o755)
            outside = Path(tmp) / f"{'c' * 32}.json"
            outside.write_text("{}")
            nested = journals / "nested" / f"{'c' * 32}.json"
            nested.parent.mkdir()
            target = journals / f"{'c' * 32}.json"
            target.symlink_to(outside)

            for path in (outside, nested, target, journals / "../escape.json"):
                with self.subTest(path=path):
                    with self.assertRaises(ProbeError):
                        store.validate_managed_path(path)

    def test_mutation_rejects_unsafe_existing_modes_without_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"
            root.mkdir(mode=0o777)
            os.chmod(root, 0o777)
            store = self.store(root)

            with self.assertRaises(ProbeError):
                store.create(store.new("linux-arm64", "gb10", (), ()))

            self.assertEqual(root.stat().st_mode & 0o777, 0o777)

    def test_symlink_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.mkdir()
            root = Path(tmp) / "state"
            root.symlink_to(target)
            store = self.store(root)

            with self.assertRaises(ProbeError):
                store.unfinished()


if __name__ == "__main__":
    unittest.main()
