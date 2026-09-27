from pathlib import Path
import tempfile
import unittest
from helpers import module, run, task, request, result


class WorkflowTests(unittest.TestCase):
    def test_independent_tasks_complete_only_after_cleanup(self):
        state = module("state")
        with tempfile.TemporaryDirectory() as directory:
            store = state.RunStore(Path(directory) / "state.db")
            store.create_run(run(directory))
            store.put_tasks("r1", [task("a"), task("b")])
            for name in ("a", "b"):
                slot = store.reserve("r1", name, 1, request(name))
                store.bind(slot["reservation_id"], name, {"evidence": "fixture native response"})
                store.transition_task("r1", name, "REVIEW_PENDING", result())
                store.transition_task("r1", name, "COMPLETE", result())
            self.assertEqual(store.summary("r1")["outcome"], "CLEANUP_REQUIRED")
            for name in ("a", "b"):
                store.mark_agent_state("r1", name, "CLOSED", "fixture native close confirmation")
            self.assertEqual(store.summary("r1")["outcome"], "SUCCESS")

    def test_review_rework_preserves_attempts_and_independence(self):
        state = module("state")
        with tempfile.TemporaryDirectory() as directory:
            store = state.RunStore(Path(directory) / "state.db")
            store.create_run(run(directory))
            store.put_tasks("r1", [task("build", needs_review=True), task("review")])
            one = store.reserve("r1", "build", 1, request("build"))
            store.bind(one["reservation_id"], "builder", {"evidence": "fixture creation"})
            store.transition_task("r1", "build", "REVIEW_PENDING", result())
            store.transition_task("r1", "build", "REWORK", {"summary": "review found defect"})
            store.mark_agent_state("r1", "builder", "CLOSED", "fixture close")
            two = store.reserve("r1", "build", 2, request("build", attempt=2))
            store.bind(two["reservation_id"], "builder2", {"evidence": "fixture creation"})
            review = store.reserve("r1", "review", 1, request("review", role="reviewer", model="gpt-6-astra", effort="high"))
            store.bind(review["reservation_id"], "reviewer", {"evidence": "fixture creation"})
            accepted = {**result(), "review": {"agent_id": "reviewer", "status": "PASS", "evidence": "independent reviewed artifact"}}
            store.transition_task("r1", "build", "REVIEW_PENDING", accepted)
            store.transition_task("r1", "build", "COMPLETE", accepted)
            self.assertEqual(store.summary("r1")["retry_counts"]["build"], 1)


if __name__ == "__main__":
    unittest.main()
