import dataclasses
import os
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from arm64_probe.environment.constants import REPOSITORY_ID
from arm64_probe.environment.journal import JournalStore
from arm64_probe.environment.models import ControllerRequest, ControllerState
from arm64_probe.errors import ProbeError


FIXED_TIME = datetime(2026, 6, 15, 0, 0, 0, tzinfo=UTC)


class EnvironmentJournalTests(unittest.TestCase):
    def store(self, root: Path) -> JournalStore:
        return JournalStore(
            root,
            repository_id=REPOSITORY_ID,
            required_owner_uid=os.getuid(),
            clock=lambda: FIXED_TIME,
            transaction_id_factory=lambda: "a" * 32,
        )

    def journal(self, store: JournalStore):
        request = ControllerRequest("linux.cpufreq", (("governor", "performance"),))
        before = ControllerState(
            "linux.cpufreq",
            "available",
            (("governor", "powersave"),),
            (),
        )
        return store.new("linux-arm64", "gb10", (request,), (before,))

    def test_round_trip_generation_and_unfinished_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.store(Path(tmp) / "state")
            journal = self.journal(store)

            path = store.create(journal)

            self.assertEqual(journal.transaction_id, "a" * 32)
            self.assertEqual(journal.created_at, "2026-06-15T00:00:00Z")
            self.assertEqual(store.read(path), journal)
            self.assertEqual(store.unfinished(), (journal,))
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o755)

    def test_updates_enforce_lifecycle_and_preserve_last_valid_on_replace_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.store(Path(tmp) / "state")
            created = self.journal(store)
            path = store.create(created)
            applying = dataclasses.replace(created, state="applying")
            store.update(applying)
            with self.assertRaises(ProbeError):
                store.update(dataclasses.replace(applying, backend_id="other"))
            prepared = dataclasses.replace(applying, state="prepared")
            store.update(prepared)
            restoring = dataclasses.replace(prepared, state="restoring")
            store.update(restoring)
            with patch("arm64_probe.environment.journal.os.replace", side_effect=OSError):
                with self.assertRaises(ProbeError):
                    store.update(dataclasses.replace(restoring, state="restore-failed"))
            self.assertEqual(store.read(path), restoring)

            restored = dataclasses.replace(restoring, state="restored")
            store.update(restored)

            self.assertEqual(store.read(path), restored)
            self.assertEqual(store.unfinished(), ())
            with self.assertRaises(ProbeError):
                store.update(dataclasses.replace(restored, state="applying"))

    def test_rejects_duplicate_keys_unknown_fields_and_invalid_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.store(Path(tmp) / "state")
            journal = self.journal(store)
            path = store.create(journal)

            path.write_text('{"schema_version": 1, "schema_version": 1}\n')
            with self.assertRaises(ProbeError):
                store.read(path)

            path.write_text('{"command": "rm", "schema_version": 1}\n')
            with self.assertRaises(ProbeError):
                store.read(path)

            with self.assertRaises(ProbeError):
                store.create(dataclasses.replace(journal, transaction_id="not-managed"))


if __name__ == "__main__":
    unittest.main()
