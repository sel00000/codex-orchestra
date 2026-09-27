from pathlib import Path
import tempfile
import unittest
from helpers import module, snapshot, catalog, request, task


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = module("policy")

    def test_stronger_advisor_keeps_parent_effort(self):
        self.assertEqual(self.policy.validate_dispatch(request(model="gpt-6-astra", effort="high", role="advisor"), snapshot(), catalog()), [])

    def test_above_parent_is_rejected(self):
        self.assertIn("EFFORT_CAP_EXCEEDED", self.policy.validate_dispatch(request(effort="max"), snapshot(), catalog()))

    def test_unsupported_model_combination_and_omission(self):
        for changes, code in [({"model": "gpt-5.5", "effort": "max"}, "EFFORT_UNSUPPORTED"),
                              ({"effort": None}, "EFFORT_REQUIRED"), ({"model": "unavailable"}, "MODEL_UNAVAILABLE")]:
            with self.subTest(changes=changes):
                self.assertIn(code, self.policy.validate_dispatch(request(**changes), snapshot(), catalog()))

    def test_old_selection_cannot_authorize_dispatch(self):
        self.assertIn("SELECTION_STALE", self.policy.validate_dispatch(request(selection_id="old"), snapshot(), catalog()))

    def test_config_default_is_not_user_selection(self):
        value = snapshot()
        value["selection_source"] = "config_default"
        self.assertIn("SELECTION_UNCONFIRMED", self.policy.validate_selection(value))

    def test_limits_default_boundaries_and_bad_types(self):
        self.assertEqual(self.policy.normalize_limit(None), 5)
        self.assertEqual(self.policy.normalize_limit(20), 20)
        for value in [True, 4, 21, 5.5, "5"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.policy.normalize_limit(value)

    def test_task_graph_rejects_missing_cycle_and_duplicate(self):
        for tasks, code in [([task(depends_on=["absent"])], "DEPENDENCY_MISSING"),
                            ([task("a", depends_on=["b"]), task("b", depends_on=["a"])], "DEPENDENCY_CYCLE"),
                            ([task(), task()], "TASK_DUPLICATE")]:
            self.assertIn(code, self.policy.validate_graph(tasks))
        self.assertEqual(self.policy.validate_graph([task("a"), task("b", depends_on=["a"])]), [])

    def test_parent_and_child_paths_conflict_but_siblings_do_not(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertTrue(self.policy.paths_overlap("src", "src/../src/a.py", root))
            self.assertFalse(self.policy.paths_overlap("src/a.py", "src/b.py", root))

    def test_symlink_and_windows_wsl_aliases_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "real").mkdir()
            (root / "alias").symlink_to(root / "real", target_is_directory=True)
            self.assertTrue(self.policy.paths_overlap("real/a", "alias/a", root))
            self.assertTrue(self.policy.paths_overlap("C:\\Users\\Example\\file.txt", "/mnt/c/users/example/file.txt", root))

    def test_expired_request_is_rejected(self):
        self.assertIn("DEADLINE_EXPIRED", self.policy.validate_dispatch(request(deadline_at="2000-01-01T00:00:00Z"), snapshot(), catalog()))

    def test_result_needs_verification_evidence(self):
        for bad in [{}, {"summary": "done", "checks": []},
                    {"summary": "done", "checks": [{"status": "PASS", "evidence": ""}]}]:
            self.assertTrue(self.policy.validate_result(bad))


if __name__ == "__main__":
    unittest.main()
