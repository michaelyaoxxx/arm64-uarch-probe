import dataclasses
import unittest
from pathlib import Path

from arm64_probe.domain.models import RunResult, Sample, make_run_result
from arm64_probe.planning.planner import Planner
from arm64_probe.planning.request import PlanRequest
from arm64_probe.registry.catalog import Catalog
from arm64_probe.serialization.model_json import to_data
from tests.contract.test_public_schemas import SCHEMA_REQUIRED


ROOT = Path(__file__).resolve().parents[2]


class ResultContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = Planner(Catalog.load(ROOT)).plan(
            PlanRequest(
                platform_id="gb10",
                selections=("cache-latency.l1-latency",),
            )
        )
        cls.run_id = "20260614T120000Z-ddc9c33"

    def sample(self, index: int = 0, case_id: str | None = None) -> Sample:
        return Sample(
            run_id=self.run_id,
            case_id=case_id or self.plan.cases[0].id,
            sample_index=index,
            status="ok",
            metrics=(("latency_ns", 1.5),),
        )

    def test_sample_and_run_result_are_frozen(self):
        sample = self.sample()
        result = make_run_result(
            self.run_id,
            self.plan,
            (sample,),
            (("case_count", 1),),
            (("restoration_status", "not-run"),),
        )

        with self.assertRaises(dataclasses.FrozenInstanceError):
            sample.status = "error"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.run_id = "changed"

    def test_sample_validates_index_and_status(self):
        with self.assertRaises(ValueError):
            self.sample(index=-1)
        with self.assertRaises(ValueError):
            Sample(self.run_id, self.plan.cases[0].id, 0, "unknown", ())

    def test_run_result_rejects_unknown_case_reference(self):
        with self.assertRaises(ValueError):
            make_run_result(
                self.run_id,
                self.plan,
                (self.sample(case_id="unknown"),),
                (),
                (),
            )

    def test_run_result_rejects_duplicate_sample_identity(self):
        sample = self.sample()
        with self.assertRaises(ValueError):
            make_run_result(self.run_id, self.plan, (sample, sample), (), ())

    def test_run_result_rejects_mismatched_run_id(self):
        sample = self.sample()
        with self.assertRaises(ValueError):
            make_run_result("different", self.plan, (sample,), (), ())

    def test_result_serialization_matches_public_keys(self):
        sample = self.sample()
        result = make_run_result(self.run_id, self.plan, (sample,), (), ())

        self.assertEqual(
            set(to_data(sample)),
            set(SCHEMA_REQUIRED["sample.schema.json"]),
        )
        self.assertEqual(
            set(to_data(result)),
            set(SCHEMA_REQUIRED["run-result.schema.json"]),
        )
        self.assertIsInstance(result, RunResult)


if __name__ == "__main__":
    unittest.main()
