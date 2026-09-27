import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from helpers import ROOT, module, run, task, request, result


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.cli = module("orchestra")
        self.state = module("state")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.state.RunStore(self.root / "db.sqlite")
        self.cli.process_command("init", run(self.root), self.store)
        self.cli.process_command("plan", {"run_id": "r1", "tasks": [task()]}, self.store)

    def test_check_denies_over_cap_without_reservation(self):
        answer = self.cli.process_command("check", {"run_id": "r1", "request": request(effort="max")}, self.store)
        self.assertFalse(answer["ok"])
        self.assertIn("EFFORT_CAP_EXCEEDED", answer["errors"])
        self.assertEqual(self.store.summary("r1")["occupied"], 0)

    def test_child_helper_call_is_rejected_as_workflow_misuse(self):
        with self.assertRaisesRegex(ValueError, "LEADER_ONLY"):
            self.cli.process_command("reserve", {"run_id": "r1", "actor": "child", "request": request()}, self.store)

    def test_duplicate_command_does_not_spawn_twice(self):
        payload = {"run_id": "r1", "request": request()}
        one = self.cli.process_command("reserve", payload, self.store)
        two = self.cli.process_command("reserve", payload, self.store)
        self.assertEqual((one["action"], two["action"]), ("spawn", "wait_existing"))

    def test_bind_and_cleanup_only_reference_owned_run(self):
        first = self.cli.process_command("reserve", {"run_id": "r1", "request": request()}, self.store)
        other_run = {**run(self.root), "run_id": "r2"}
        self.store.create_run(other_run)
        self.store.put_tasks("r2", [task()])
        second = self.store.reserve("r2", "t1", 1, request(run_id="r2"))
        self.store.bind(second["reservation_id"], "other-a1", {"evidence": "native response"})
        with self.assertRaises(ValueError):
            self.cli.process_command("bind", {"run_id": "r1", "reservation_id": second["reservation_id"], "agent_id": "bad", "actual": {"evidence": "bad"}}, self.store)
        self.store.bind(first["reservation_id"], "a1", {"evidence": "native response"})
        answer = self.cli.process_command("cleanup-plan", {"run_id": "r1"}, self.store)
        self.assertEqual(answer["agent_ids"], ["a1"])

    def test_cancel_and_unknown_agent_do_not_report_success(self):
        slot = self.store.reserve("r1", "t1", 1, request())
        self.store.mark_reservation_state(slot["reservation_id"], "UNKNOWN", "lost reply")
        self.store.transition_task("r1", "t1", "CANCELLED", {"summary": "user cancelled"})
        answer = self.cli.process_command("report", {"run_id": "r1", "target": str(self.root / "report.md")}, self.store)
        self.assertEqual(answer["outcome"], "CLEANUP_REQUIRED")
        self.assertEqual(answer["occupied"], 1)
        self.assertTrue((self.root / "report.md").is_file())

    def test_success_keeps_unverified_actual_distinct(self):
        slot = self.store.reserve("r1", "t1", 1, request())
        self.store.bind(slot["reservation_id"], "a1", {"evidence": "native creation response only"})
        self.store.transition_task("r1", "t1", "REVIEW_PENDING", result())
        self.store.transition_task("r1", "t1", "COMPLETE", result())
        self.store.mark_agent_state("r1", "a1", "CLOSED", "native close result")
        answer = self.cli.process_command("report", {"run_id": "r1"}, self.store)
        self.assertEqual(answer["outcome"], "SUCCESS")
        self.assertIsNone(answer["agents"][0]["actual"]["model"])
        self.assertEqual(answer["agents"][0]["request"]["model"], "gpt-6-luna")

    def test_bad_json_exits_nonzero_and_returns_structured_error(self):
        command = ["python3", str(ROOT / "orchestra/scripts/orchestra.py"), "check", "--db", str(self.root / "bad.sqlite")]
        executed = subprocess.run(command, input="{bad", text=True, capture_output=True)
        self.assertEqual(executed.returncode, 2)
        self.assertFalse(json.loads(executed.stdout)["ok"])

    def test_non_object_check_request_returns_structured_rejection(self):
        for value in [None, [], "bad"]:
            with self.subTest(value=value):
                executed = subprocess.run(["python3", str(ROOT / "orchestra/scripts/orchestra.py"),
                                           "check", "--db", str(self.root / "db.sqlite")],
                                          input=json.dumps({"run_id": "r1", "request": value}), text=True, capture_output=True)
                self.assertEqual(executed.returncode, 2)
                self.assertFalse(json.loads(executed.stdout)["ok"])
                self.assertIn("REQUEST_REQUIRED", json.loads(executed.stdout)["errors"])


if __name__ == "__main__":
    unittest.main()
