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


def json_plan(*arguments: str) -> dict[str, object]:
    result = run_probe("plan", *arguments, "-o", "json")
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return json.loads(result.stdout)


class CliPlanTests(unittest.TestCase):
    def test_single_combined_and_parent_selections(self):
        single = json_plan(
            "--platform", "gb10", "--select", "cache-latency.l1-latency"
        )
        combined = json_plan(
            "--platform",
            "gb10",
            "--select",
            "cache-latency.l2-latency",
            "--select",
            "migration-latency.cross-cluster",
        )
        parent = json_plan("--platform", "gb10", "--select", "cache-latency")

        self.assertEqual(len(single["cases"]), 1)
        self.assertEqual(len(combined["cases"]), 2)
        self.assertEqual(len(parent["cases"]), 5)

    def test_semantic_selectors_and_parameter_overrides(self):
        plan = json_plan(
            "--platform",
            "gb10",
            "--select",
            "cache-latency.l1-latency",
            "--cluster",
            "c0",
            "--core-group",
            "x925",
            "--samples",
            "3",
            "--working-set",
            "48KiB",
            "--page-policy",
            "hugepage",
        )

        case = plan["cases"][0]
        self.assertEqual(case["cpu"], 5)
        self.assertEqual(case["parameters"]["samples"]["value"], 3)
        self.assertEqual(case["parameters"]["samples"]["source"], "cli")
        self.assertEqual(case["parameters"]["working-set"]["value"], "48KiB")
        self.assertEqual(case["parameters"]["page-policy"]["value"], "hugepage")
        self.assertEqual(
            [item["id"] for item in case["execution_requirements"]],
            ["cpu-affinity", "page-policy"],
        )

    def test_table_preview_lists_host_and_case_requirements(self):
        result = run_probe("plan", "--platform", "gb10", "--profile", "baseline")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HOST REQUIREMENTS", result.stdout)
        self.assertIn("cpu-frequency", result.stdout)
        self.assertIn("CASE REQUIREMENTS", result.stdout)
        self.assertIn("cpu-affinity", result.stdout)
        self.assertIn("page-policy", result.stdout)

    def test_profile_and_skip_unavailable(self):
        plan = json_plan(
            "--platform",
            "m4",
            "--profile",
            "smoke",
            "--skip-unavailable",
        )

        self.assertTrue(plan["skip_unavailable"])
        self.assertEqual({case["status"] for case in plan["cases"]}, {"unsupported"})

    def test_auto_platform_is_limited_to_darwin_arm64(self):
        result = run_probe("plan", "--profile", "smoke", "-o", "json")

        if platform.system() == "Darwin" and platform.machine() in {"arm64", "aarch64"}:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["platform_id"], "m4")
        else:
            self.assertEqual(result.returncode, 4)

    def test_unapproved_short_options_fail(self):
        for option in ("-p", "-s", "-v", "-q"):
            with self.subTest(option=option):
                result = run_probe("plan", option, "value")
                self.assertEqual(result.returncode, 2)

    def test_json_errors_use_public_contract(self):
        result = run_probe(
            "plan",
            "--platform",
            "gb10",
            "--select",
            "unknown",
            "-o",
            "json",
        )

        self.assertEqual(result.returncode, 5)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["code"], 5)
        self.assertEqual(payload["category"], "planning")
        self.assertIn("unknown selection", payload["message"])

    def test_last_output_option_controls_structured_errors(self):
        result = run_probe(
            "plan",
            "--platform",
            "gb10",
            "--select",
            "unknown",
            "-o",
            "table",
            "-o",
            "json",
        )

        self.assertEqual(result.returncode, 5)
        self.assertEqual(json.loads(result.stdout)["category"], "planning")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
