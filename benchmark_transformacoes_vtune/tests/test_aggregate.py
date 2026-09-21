import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "aggregate.py"
SPEC = importlib.util.spec_from_file_location("vtune_aggregate", MODULE_PATH)
aggregate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(aggregate)


class AggregateTest(unittest.TestCase):
    def make_campaign(self, complete=True):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        run_dir = Path(temporary.name)
        collection_id = "threads_040__static__Negative"
        (run_dir / "manifest.csv").write_text(
            "Collection_ID,Collection_Repetition,Num_Threads,OMP_Schedule_Raw,"
            "OMP_Schedule,Schedule_Kind,Chunk_Size,Transformation,Workload_Iterations\n"
            f"{collection_id},1,40,static,static,static,,Negative,2\n",
            encoding="utf-8",
        )
        collection = run_dir / "collections" / collection_id
        reports = collection / "reports"
        reports.mkdir(parents=True)
        (collection / "metadata.env").write_text(
            "Campaign_ID=test\nHost=node\nVTune_Version=2021.1.1\n",
            encoding="utf-8",
        )
        if not complete:
            (collection / "failure.txt").write_text("test failure\n", encoding="utf-8")
            return run_dir

        (collection / "result").mkdir()
        (collection / ".complete").touch()
        (collection / "timings.csv").write_text(
            "Collection_ID,Collection_Repetition,Image,Num_Threads,OMP_Schedule,"
            "Transformation,Workload_Iteration,Workload_Iterations,Frame_ID,Time_ms\n"
            f"{collection_id},1,a.png,40,static,Negative,1,2,1,1.0\n"
            f"{collection_id},1,a.png,40,static,Negative,2,2,2,2.0\n"
            f"{collection_id},1,b.png,40,static,Negative,1,2,3,3.0\n"
            f"{collection_id},1,b.png,40,static,Negative,2,2,4,4.0\n",
            encoding="utf-8",
        )
        (reports / "summary.csv").write_text(
            "Metric Name,Metric Value\nElapsed Time,8.0s\nMemory Bound,N/A\n",
            encoding="utf-8",
        )
        (reports / "hotspots.csv").write_text(
            "Function,Module,CPU Time\napply_negative,benchmark,7.0s\n",
            encoding="utf-8",
        )
        (reports / "hw-events.csv").write_text(
            "Function,Hardware Event Count:,Module\n"
            ",INST_RETIRED.ANY,\n"
            "apply_negative,1000,benchmark\n",
            encoding="utf-8",
        )
        (reports / "frames.csv").write_text(
            "Frame,CPU Time\ninf01077.transform.Negative,7.0s\n",
            encoding="utf-8",
        )
        return run_dir

    def test_complete_campaign_is_merged_and_validated(self):
        run_dir = self.make_campaign()
        status = aggregate.main(
            [str(run_dir), "--require-complete", "--expected-collections", "1"]
        )
        self.assertEqual(status, 0)
        with (run_dir / "benchmark_transformacoes_vtune.csv").open(
            newline="", encoding="utf-8"
        ) as stream:
            rows = list(csv.DictReader(stream))
        types = [row["Record_Type"] for row in rows]
        self.assertEqual(types.count("collection"), 1)
        self.assertEqual(types.count("timing"), 4)
        self.assertEqual(types.count("function"), 2)
        self.assertEqual(types.count("frame"), 1)
        collection = next(row for row in rows if row["Record_Type"] == "collection")
        self.assertEqual(collection["Summary__Elapsed_Time"], "8.0s")
        self.assertEqual(collection["Unsupported_Metrics"], "Memory Bound")
        hardware = next(row for row in rows if row["Report_Type"] == "hw_events")
        self.assertEqual(
            hardware["hw_events__Hardware_Event_Count_INST_RETIRED_ANY"], "1000"
        )

    def test_incomplete_campaign_produces_traceable_manifest_row(self):
        run_dir = self.make_campaign(complete=False)
        status = aggregate.main([str(run_dir), "--expected-collections", "1"])
        self.assertEqual(status, 0)
        with (run_dir / "benchmark_transformacoes_vtune.csv").open(
            newline="", encoding="utf-8"
        ) as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Status"], "failed")
        self.assertEqual(rows[0]["Failure"], "test failure")

    def test_require_complete_rejects_incomplete_campaign(self):
        run_dir = self.make_campaign(complete=False)
        status = aggregate.main([str(run_dir), "--require-complete"])
        self.assertEqual(status, 1)


if __name__ == "__main__":
    unittest.main()
