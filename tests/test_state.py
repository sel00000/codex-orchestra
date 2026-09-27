from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from helpers import module, run, task, request, result


class StateTests(unittest.TestCase):
    def setUp(self):
        self.state = module("state")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.state.RunStore(self.root / "state.db")
        self.store.create_run(run(self.root))
        self.store.put_tasks("r1", [task("t" + str(i)) for i in range(1, 24)])

    def fill(self, count):
        return [self.store.reserve("r1", "t" + str(i), 1, request("t" + str(i))) for i in range(1, count + 1)]

    def test_capacity_five_and_confirmed_close(self):
        reservations = self.fill(5)
        with self.assertRaises(self.state.CapacityFull):
            self.store.reserve("r1", "t6", 1, request("t6"))
        self.store.bind(reservations[0]["reservation_id"], "agent1", {"evidence": "native spawn response"})
        self.store.mark_agent_state("r1", "agent1", "STOPPING", "interrupt sent")
        self.assertEqual(self.store.summary("r1")["occupied"], 5)
        self.store.mark_agent_state("r1", "agent1", "CLOSED", "native close confirmed")
        self.assertEqual(self.store.summary("r1")["occupied"], 4)

    def test_capacity_twenty(self):
        other = self.state.RunStore(self.root / "twenty.db")
        other.create_run(run(self.root, 20))
        other.put_tasks("r1", [task(str(i)) for i in range(21)])
        for i in range(20):
            other.reserve("r1", str(i), 1, request(str(i)))
        with self.assertRaises(self.state.CapacityFull):
            other.reserve("r1", "20", 1, request("20"))
        self.assertEqual(other.summary("r1")["occupied"], 20)

    def test_last_slot_race_uses_two_real_connections(self):
        self.fill(4)
        barrier = threading.Barrier(2)
        def reserve(i):
            other = self.state.RunStore(self.root / "state.db")
            barrier.wait()
            try:
                other.reserve("r1", i, 1, request(i))
                return "reserved"
            except self.state.CapacityFull:
                return "full"
        with ThreadPoolExecutor(2) as pool:
            outcomes = list(pool.map(reserve, ["t5", "t6"]))
        self.assertCountEqual(outcomes, ["reserved", "full"])
        self.assertEqual(self.store.summary("r1")["occupied"], 5)

    def test_duplicate_cannot_trigger_second_spawn(self):
        first = self.store.reserve("r1", "t1", 1, request())
        second = self.store.reserve("r1", "t1", 1, request())
        self.assertEqual(first["action"], "spawn")
        self.assertEqual(second["action"], "wait_existing")
        self.assertEqual(first["reservation_id"], second["reservation_id"])

    def test_unknown_spawn_holds_slot_and_reopen_retains_it(self):
        reserved = self.store.reserve("r1", "t1", 1, request())
        self.store.mark_reservation_state(reserved["reservation_id"], "UNKNOWN", "response lost")
        reopened = self.state.RunStore(self.root / "state.db")
        self.assertEqual(reopened.summary("r1")["occupied"], 1)

    def test_retry_requires_previous_release_and_stops_after_three(self):
        for attempt in (1, 2, 3):
            value = request(attempt=attempt)
            slot = self.store.reserve("r1", "t1", attempt, value)
            with self.assertRaises(ValueError):
                self.store.reserve("r1", "t1", attempt + 1, request(attempt=attempt+1))
            self.store.mark_reservation_state(slot["reservation_id"], "FAILED", "native create failed")
            self.store.transition_task("r1", "t1", "REWORK", {"summary": "retry needed"})
        with self.assertRaises(ValueError):
            self.store.reserve("r1", "t1", 4, request(attempt=4))
        self.assertEqual(self.store.summary("r1")["retry_counts"]["t1"], 2)
        self.assertEqual(self.store.summary("r1")["tasks"][0]["state"], "BLOCKED")

    def test_put_tasks_cannot_reset_attempt_or_change_active_contract(self):
        self.store.reserve("r1", "t1", 1, request())
        self.store.put_tasks("r1", [task("t1")])
        self.assertEqual(self.store.summary("r1")["occupied"], 1)
        with self.assertRaises(ValueError):
            self.store.put_tasks("r1", [task("t1", write_paths=["new.py"])])

    def test_edit_collision_is_rejected(self):
        self.store.put_tasks("r1", [task("t1", write_paths=["src"]), task("t2", write_paths=["src/a.py"])])
        self.store.reserve("r1", "t1", 1, request(write_paths=["src"]))
        with self.assertRaisesRegex(ValueError, "WRITE_CONFLICT"):
            self.store.reserve("r1", "t2", 1, request("t2", write_paths=["src/a.py"]))

    def test_failed_dependency_does_not_release_followup(self):
        self.store.put_tasks("r1", [task("t2", depends_on=["t1"])])
        self.store.transition_task("r1", "t1", "BLOCKED", {"summary": "missing input"})
        with self.assertRaises(ValueError):
            self.store.reserve("r1", "t2", 1, request("t2", depends_on=["t1"]))

    def test_result_does_not_free_agent_slot(self):
        slot = self.store.reserve("r1", "t1", 1, request())
        self.store.bind(slot["reservation_id"], "a1", {"evidence": "created"})
        self.store.transition_task("r1", "t1", "REVIEW_PENDING", result())
        self.store.transition_task("r1", "t1", "COMPLETE", result())
        self.assertEqual(self.store.summary("r1")["occupied"], 1)

    def test_complete_requires_evidence_and_independent_review_when_requested(self):
        self.store.put_tasks("r1", [task("t1", needs_review=True)])
        slot = self.store.reserve("r1", "t1", 1, request())
        self.store.bind(slot["reservation_id"], "a1", {"evidence": "created"})
        self.store.transition_task("r1", "t1", "REVIEW_PENDING", result())
        with self.assertRaises(ValueError):
            self.store.transition_task("r1", "t1", "COMPLETE", result())

    def test_stale_selection_and_small_native_cap(self):
        snap = run(self.root)["snapshot"]
        snap["selection_id"] = "sel2"
        snap["effort"] = "medium"
        self.store.update_snapshot("r1", snap)
        with self.assertRaisesRegex(ValueError, "SELECTION_STALE"):
            self.store.reserve("r1", "t1", 1, request())
        snap["native_cap"] = 4
        with self.assertRaises(ValueError):
            self.store.update_snapshot("r1", {**snap, "selection_id": "sel3"})

    def test_actual_mismatch_stops_new_assignments(self):
        slot = self.store.reserve("r1", "t1", 1, request())
        self.store.bind(slot["reservation_id"], "a1", {"model": "gpt-6-luna", "effort": "max", "evidence": "observed"})
        with self.assertRaisesRegex(ValueError, "CONFIG_MISMATCH"):
            self.store.reserve("r1", "t2", 1, request("t2"))
        self.assertEqual(self.store.summary("r1")["occupied"], 1)

    def test_database_lock_does_not_create_reservation(self):
        with sqlite3.connect(self.root / "state.db") as connection:
            connection.execute("BEGIN IMMEDIATE")
            with self.assertRaises(sqlite3.OperationalError):
                self.store.reserve("r1", "t1", 1, request())
        self.assertEqual(self.store.summary("r1")["occupied"], 0)

    def test_repeated_bind_preserves_task_progress_and_idle_state(self):
        for index, progress in enumerate(["COMPLETE", "REVIEW_PENDING", "REWORK", "BLOCKED"], 1):
            name = "t" + str(index)
            with self.subTest(progress=progress):
                slot = self.store.reserve("r1", name, 1, request(name))
                actual = {"evidence": "original native response"}
                agent = "repeat" + str(index)
                self.store.bind(slot["reservation_id"], agent, actual)
                self.store.transition_task("r1", name, "REVIEW_PENDING", result())
                if progress != "REVIEW_PENDING":
                    self.store.transition_task("r1", name, progress, result())
                self.store.mark_agent_state("r1", agent, "IDLE", "native idle observed")
                self.store.bind(slot["reservation_id"], agent, actual)
                summary = self.store.summary("r1")
                recorded = next(item for item in summary["tasks"] if item["task_id"] == name)
                bound = next(item for item in summary["agents"] if item["agent_id"] == agent)
                self.assertEqual(recorded["state"], progress)
                self.assertEqual(bound["state"], "IDLE")

    def test_late_bind_tracks_cancelled_child_without_resurrecting_task(self):
        slot = self.store.reserve("r1", "t1", 1, request())
        self.store.mark_reservation_state(slot["reservation_id"], "UNKNOWN", "spawn response lost")
        self.store.transition_task("r1", "t1", "CANCELLED", {"summary": "user cancelled"})
        self.store.bind(slot["reservation_id"], "late-child", {"evidence": "native listing reconciles identifier"})
        summary = self.store.summary("r1")
        self.assertEqual(summary["tasks"][0]["state"], "CANCELLED")
        self.assertEqual(summary["open_agents"][0]["agent_id"], "late-child")
        self.assertEqual(summary["open_agents"][0]["state"], "STOPPING")

    def test_dependency_failure_propagates_through_reverse_order_graph(self):
        self.store.put_tasks("r1", [task("c", depends_on=["b"]), task("b", depends_on=["a"]), task("a")])
        self.store.transition_task("r1", "a", "CANCELLED", {"summary": "cancelled"})
        states = {item["task_id"]: item["state"] for item in self.store.summary("r1")["tasks"]}
        self.assertEqual([states["a"], states["b"], states["c"]], ["CANCELLED", "BLOCKED", "BLOCKED"])


if __name__ == "__main__":
    unittest.main()
