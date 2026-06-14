import tempfile
import unittest
from pathlib import Path

from arm64_probe.errors import ExitCode, ProbeError
from arm64_probe.serialization.json_io import dump_json, load_json


ROOT = Path(__file__).resolve().parents[2]


class JsonIoTests(unittest.TestCase):
    def test_rejects_duplicate_object_keys(self):
        path = ROOT / "tests" / "fixtures" / "json" / "duplicate-key.json"

        with self.assertRaises(ProbeError) as error:
            load_json(path)

        self.assertEqual(error.exception.code, ExitCode.CONFIG)
        self.assertIn("duplicate key", error.exception.message)

    def test_rejects_invalid_utf8_and_json(self):
        for payload in (b"\xff", b'{"missing":'):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "invalid.json"
                path.write_bytes(payload)

                with self.assertRaises(ProbeError) as error:
                    load_json(path)

                self.assertEqual(error.exception.code, ExitCode.CONFIG)

    def test_rejects_non_object_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "array.json"
            path.write_text("[]")

            with self.assertRaises(ProbeError) as error:
                load_json(path)

            self.assertEqual(error.exception.code, ExitCode.CONFIG)
            self.assertIn("object root", error.exception.message)

    def test_dump_json_is_deterministic(self):
        self.assertEqual(
            dump_json({"z": 1, "a": {"b": 2}}),
            '{\n  "a": {\n    "b": 2\n  },\n  "z": 1\n}\n',
        )


if __name__ == "__main__":
    unittest.main()
