from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from helpers import module, snapshot, request, task


def row(name):
    return {"slug": name, "visibility": "list", "description": "Workhorse model",
            "supported_reasoning_levels": [{"effort": effort} for effort in ("low", "medium", "high", "max")]}


class ModelSyncTests(unittest.TestCase):
    def setUp(self):
        self.cli = module("orchestra")
        self.catalog = module("catalog")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = module("state").RunStore(self.root / 'state.db')
        self.native = {name: ["low", "medium", "high", "max"] for name in ("gpt-6-sol", "gpt-6.1-sol", "gpt-5.5")}
        self.set_models("gpt-6-sol", "gpt-6.1-sol", "gpt-5.5")
        self.reader = patch.object(self.cli, "inspect_environment", side_effect=lambda _: self.report)
        self.reader.start()
        self.addCleanup(self.reader.stop)
        self.selection = {**snapshot(), "model": "gpt-6.1-sol"}
        self.init = self.cli.process_command("init", {"run_id": "r1", "goal": "Adaptive model test", "project": str(self.root),
                                                  "max_agents": 5, "snapshot": self.selection, "native_catalog": self.native}, self.store)
        self.store.put_tasks("r1", [task()])

    def set_models(self, *names):
        self.report = {**self.catalog.build_catalog({"models": [row(name) for name in names]},
                                                  now=datetime(2026, 9, 30, tzinfo=timezone.utc)),
                       "catalog_source": "codex_debug_models", "diagnostics": []}

    def assignment(self, **changes):
        return request(model="gpt-6.1-sol", effort="medium", catalog_id=self.init["catalog_id"], **changes)

    def test_new_sol_can_be_reserved_without_changing_the_leader(self):
        answer = self.cli.process_command("reserve", {"run_id": "r1", "request": self.assignment()}, self.store)
        self.assertEqual(answer["action"], "spawn")
        self.assertEqual(self.store.summary("r1")["run"]["snapshot"], self.selection)

    def test_disappearance_is_checked_before_a_new_reservation(self):
        self.set_models("gpt-6-sol", "gpt-6.1-sol")
        old = request(model="gpt-5.5", catalog_id=self.init["catalog_id"])
        answer = self.cli.process_command("check", {"run_id": "r1", "request": old}, self.store)
        self.assertIn("MODEL_UNAVAILABLE", answer["errors"])
        self.assertIn("CATALOG_STALE", answer["errors"])
        self.assertEqual(self.store.summary("r1")["occupied"], 0)

    def test_a_prepared_request_must_be_rechecked_after_catalog_change(self):
        prepared = self.assignment()
        self.set_models("gpt-6.1-sol")
        with self.assertRaisesRegex(ValueError, "CATALOG_STALE"):
            self.cli.process_command("reserve", {"run_id": "r1", "request": prepared}, self.store)
        current = self.store.summary("r1")["run"]["catalog_id"]
        self.assertEqual(self.cli.process_command("reserve", {"run_id": "r1", "request": {**prepared, "catalog_id": current}}, self.store)["action"], "spawn")

    def test_retired_existing_reservation_is_reconciled_without_spawning_again(self):
        existing = request(model="gpt-5.5", catalog_id=self.init["catalog_id"])
        first = self.cli.process_command("reserve", {"run_id": "r1", "request": existing}, self.store)
        self.store.mark_reservation_state(first["reservation_id"], "UNKNOWN", "Lost fixture response")
        self.set_models("gpt-6.1-sol")
        self.cli.process_command("sync-models", {"run_id": "r1"}, self.store)
        repeated = self.cli.process_command("reserve", {"run_id": "r1", "request": existing}, self.store)
        self.assertEqual(repeated["action"], "wait_existing")
        self.assertEqual(repeated["reservation_id"], first["reservation_id"])
        self.assertEqual(self.store.summary("r1")["occupied"], 1)
        self.assertEqual(self.store.summary("r1")["agents"][0]["state"], "UNKNOWN")

    def test_catalog_failure_does_not_reuse_old_availability(self):
        self.report = {"catalog": {}, "diagnostics": ["CATALOG_READ_FAILED"]}
        answer = self.cli.process_command("check", {"run_id": "r1", "request": self.assignment()}, self.store)
        self.assertFalse(answer["ok"])
        self.assertEqual(answer["catalog"], {})
        self.assertEqual(self.store.summary("r1")["run"]["snapshot"], self.selection)

    def test_native_schema_changes_are_applied_without_raising_effort(self):
        limited = {"gpt-6.1-sol": ["low"]}
        answer = self.cli.process_command("check", {"run_id": "r1", "request": self.assignment(), "native_catalog": limited}, self.store)
        self.assertIn("EFFORT_UNSUPPORTED", answer["errors"])
        self.assertEqual(answer["catalog"], limited)
        run = self.store.summary("r1")["run"]
        self.assertEqual(run["routing_candidates"]["sol"], ["gpt-6.1-sol"])
        self.assertNotIn("gpt-6-sol", run["model_metadata"])

    def test_inspection_reports_available_update_without_installing_it(self):
        with patch.object(self.cli, "check_update", return_value={"status": "update_available", "automatic_install": False}) as checked:
            answer = self.cli.process_command("inspect", {"project": str(self.root), "native_catalog": self.native})
        self.assertTrue(answer["ok"])
        self.assertTrue(answer["native_schema_checked"])
        self.assertEqual(answer["skill_update"]["status"], "update_available")
        checked.assert_called_once()
