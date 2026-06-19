"""ResultIngester and LegacyImporter tests."""
import tempfile
import unittest
from pathlib import Path

from arm64_probe.analysis.ingestion import ResultIngester, LegacyImporter
from arm64_probe.analysis.models import ImportedRecord
from arm64_probe.execution.result_store import ResultStore
from arm64_probe.domain.models import (
    Sample,
    Plan,
    Case,
    make_run_result,
)


class ResultIngesterTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.store = ResultStore(results_dir=self.tmpdir)
        self.ingester = ResultIngester(self.store)

    def _write_run(self, run_id, case_ids):
        samples = tuple(
            Sample(
                run_id=run_id, case_id=cid, sample_index=i,
                status="ok", metrics=(("latency_ns", 4.0 + i),),
            )
            for i, cid in enumerate(case_ids)
        )
        plan = Plan(
            platform_id="gb10", profile_id="smoke",
            selections=case_ids,
            cases=tuple(
                Case(
                    id=cid, scenario_id="cache-latency.l1-latency",
                    platform_id="gb10", status="ready", reason=None,
                    cpu=0, src_cpu=None, dst_cpu=None,
                    selectors=(), parameters=(),
                )
                for cid in case_ids
            ),
            environment_phases=(), skip_unavailable=False,
        )
        result = make_run_result(
            run_id=run_id, plan=plan, samples=samples,
            summary=(("platform_id", "gb10"),),
            environment=(),
        )
        self.store.write_result(result)
        return result

    def test_ingest_single_run(self):
        self._write_run("run1", ("case1",))
        results = self.ingester.ingest((self.tmpdir / "run1.json",))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].run_id, "run1")

    def test_ingest_rejects_duplicate_run_ids(self):
        self._write_run("run1", ("case1",))
        with self.assertRaises(ValueError):
            self.ingester.ingest((
                self.tmpdir / "run1.json",
                self.tmpdir / "run1.json",
            ))

    def test_ingest_multiple_runs(self):
        self._write_run("run1", ("case1",))
        self._write_run("run2", ("case2",))
        results = self.ingester.ingest((
            self.tmpdir / "run1.json",
            self.tmpdir / "run2.json",
        ))
        self.assertEqual(len(results), 2)

    def test_ingest_empty_paths_returns_empty(self):
        results = self.ingester.ingest(())
        self.assertEqual(results, ())


class LegacyImporterProtocolTests(unittest.TestCase):
    def test_imported_record_is_frozen(self):
        record = ImportedRecord(
            source_path="/tmp/test.log", parser_version="1.0",
            format="chase_pmu_text", case_id="cache-latency.l1-latency",
            platform_id="gb10",
            metrics=(("latency_ns", 4.36),),
            loss_notes=("warm/cold state inferred",),
        )
        with self.assertRaises(Exception):
            record.case_id = "changed"  # type: ignore[assignment]
