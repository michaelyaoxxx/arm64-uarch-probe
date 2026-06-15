import json
import platform
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_probe(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "arm64_probe", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


class CliDoctorTests(unittest.TestCase):
    def test_doctor_help_is_public_and_side_effect_free(self):
        for arguments in (("doctor", "--help"), ("help", "doctor")):
            with self.subTest(arguments=arguments):
                result = run_probe(*arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--platform", result.stdout)
                self.assertNotIn("--allow-mutation", result.stdout)

    def test_doctor_rejects_mutation_authorization_option(self):
        result = run_probe("doctor", "--allow-mutation")

        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    @unittest.skipUnless(
        platform.system() == "Darwin" and platform.machine() in {"arm64", "aarch64"},
        "requires Darwin ARM64 host",
    )
    def test_darwin_json_report_is_successful_and_explicitly_unsupported(self):
        result = run_probe("doctor", "--platform", "m4", "-o", "json")

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["backend_id"], "darwin-arm64")
        self.assertEqual(report["platform_id"], "m4")
        observations = {item["capability_id"]: item for item in report["observations"]}
        self.assertEqual(observations["linux.cpufreq"]["status"], "unsupported")
        self.assertEqual(observations["linux.hugepage"]["status"], "unsupported")


if __name__ == "__main__":
    unittest.main()
