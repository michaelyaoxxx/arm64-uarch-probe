import unittest

from arm64_probe.domain.models import EnvironmentRequirement
from arm64_probe.environment.models import ControllerRequest
from arm64_probe.environment.requests import requests_from_requirements


def requirement(
    capability_id="linux.cpufreq",
    scope="host",
    mutation=True,
):
    return EnvironmentRequirement(
        "cpu-frequency",
        capability_id,
        scope,
        (("governor", "performance"),),
        mutation,
        True,
    )


class EnvironmentRequestTests(unittest.TestCase):
    def test_converts_and_orders_host_mutation_requirements(self):
        requests = requests_from_requirements(
            (
                EnvironmentRequirement(
                    "hugepage-pool",
                    "linux.hugepage",
                    "host",
                    (("count", 8), ("size-kb", 2048)),
                    True,
                    True,
                ),
                requirement(),
            )
        )

        self.assertEqual(
            requests,
            (
                ControllerRequest(
                    "linux.cpufreq",
                    (("governor", "performance"),),
                ),
                ControllerRequest(
                    "linux.hugepage",
                    (("count", 8), ("size-kb", 2048)),
                ),
            ),
        )

    def test_rejects_non_host_non_mutation_unknown_and_duplicate_controllers(self):
        invalid = (
            (requirement(scope="case"),),
            (requirement(mutation=False),),
            (requirement(capability_id="unknown"),),
            (requirement(), requirement()),
        )
        for requirements in invalid:
            with self.subTest(requirements=requirements):
                with self.assertRaises(ValueError):
                    requests_from_requirements(requirements)


if __name__ == "__main__":
    unittest.main()
