"""Catch false compatibility claims before enabling automatic dispatch."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "orchestra/scripts/native.py"


def snapshot():
    return {
        "session_id": "s1", "turn_id": "t1", "model": "gpt-6-sol",
        "effort": "high", "native_cap": 5, "backend": "v2",
        "selection_source": "live_turn", "verified": True,
    }


def report():
    return {
        "codex_version": "0.157.1", "python_version": "3.12.3",
        "catalog": {"gpt-6-sol": ["low", "medium", "high"]},
        "snapshot": snapshot(),
        "checks": {
            "active_selection": "PASS", "pre_dispatch_guard": "PASS",
            "effective_values": "PASS", "native_cap": "PASS",
            "root_only_dispatch": "PASS", "lifecycle": "PASS",
            "config_isolation": "PASS",
        },
        "evidence_paths": ["characterization.json"],
    }


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SCRIPT.exists():
            spec = importlib.util.spec_from_file_location("orchestra_native", SCRIPT)
            cls.native = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = cls.native
            spec.loader.exec_module(cls.native)
        else:
            cls.native = None

    def adapter(self):
        self.assertIsNotNone(self.native, "The capability checker has not been implemented")
        return self.native

    def test_verified_supported_report_is_compatible(self):
        self.assertTrue(self.adapter().is_compatible(report()))

    def test_empty_checks_do_not_allow_execution(self):
        value = report()
        value["checks"] = {}
        self.assertFalse(self.adapter().is_compatible(value))

    def test_unverified_guard_blocks_execution(self):
        value = report()
        value["checks"]["pre_dispatch_guard"] = "UNVERIFIED"
        self.assertFalse(self.adapter().is_compatible(value))

    def test_failed_guard_blocks_execution(self):
        value = report()
        value["checks"]["pre_dispatch_guard"] = "FAIL"
        self.assertFalse(self.adapter().is_compatible(value))

    def test_unknown_version_requires_reverification(self):
        value = report()
        value["codex_version"] = "0.158.0"
        self.assertFalse(self.adapter().is_compatible(value))

    def test_missing_effort(self):
        value = snapshot()
        value["effort"] = None
        self.assertIn("EFFORT_UNKNOWN", self.adapter().validate_snapshot(value, "s1", "t1"))

    def test_session_mismatch(self):
        self.assertIn("SESSION_MISMATCH", self.adapter().validate_snapshot(snapshot(), "s2", "t1"))

    def test_stale_turn(self):
        self.assertIn("TURN_STALE", self.adapter().validate_snapshot(snapshot(), "s1", "t2"))

    def test_config_default_is_not_live_selection(self):
        value = snapshot()
        value["selection_source"] = "config_default"
        self.assertIn("SELECTION_UNVERIFIED", self.adapter().validate_snapshot(value, "s1", "t1"))

    def test_absent_snapshot_is_not_compatible(self):
        value = report()
        value["snapshot"] = None
        self.assertFalse(self.adapter().is_compatible(value))

    def test_unsupported_model_effort_is_not_compatible(self):
        value = report()
        value["catalog"]["gpt-6-sol"] = ["low", "medium"]
        self.assertFalse(self.adapter().is_compatible(value))

    def test_invalid_capacity_is_not_compatible(self):
        for capacity in [None, 0, -1, True, "5"]:
            with self.subTest(capacity=capacity):
                value = report()
                value["snapshot"]["native_cap"] = capacity
                self.assertFalse(self.adapter().is_compatible(value))

    def test_missing_evidence_is_not_compatible(self):
        value = report()
        value["evidence_paths"] = []
        self.assertFalse(self.adapter().is_compatible(value))

    def test_unknown_control_event_is_rejected(self):
        with self.assertRaises(ValueError):
            self.adapter().normalize_event({"hook_event_name": "Unknown"}, "v2")

    def test_pre_tool_event_keeps_requested_values_separate_from_effective(self):
        value = {"hook_event_name": "PreToolUse", "session_id": "s1", "turn_id": "t1",
                 "tool_name": "collaborationspawn_agent", "tool_use_id": "call1",
                 "tool_input": {"model": "gpt-6-luna", "reasoning_effort": "low"}}
        result = self.adapter().normalize_event(value, "v2")
        self.assertEqual(result["event"], "pre_tool_use")
        self.assertEqual(result["input"], value["tool_input"])
        self.assertIsNone(result["output"])
        self.assertIsNone(result["actor_id"])
        self.assertNotIn("effective_effort", result)

    def test_event_without_identity_is_rejected(self):
        value = {"hook_event_name": "PreToolUse", "tool_name": "collaborationspawn_agent",
                 "tool_input": {}}
        with self.assertRaises(ValueError):
            self.adapter().normalize_event(value, "v2")

    def test_installed_cli_can_be_found_without_interactive_shell_path(self):
        native = self.adapter()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / ".local/bin/codex"
            binary.parent.mkdir(parents=True)
            binary.write_text('#!/usr/bin/env python3\nimport sys\n'
                              'print("codex-cli 0.157.1" if "--version" in sys.argv else \'{"models": []}\')\n')
            binary.chmod(0o755)
            with patch.object(native.shutil, "which", return_value=None), patch.object(native.Path, "home", return_value=root):
                result = native.inspect_environment(root)
            self.assertEqual(result["codex_version"], "0.157.1")
            self.assertEqual(result["checks"]["pre_dispatch_guard"], "FAIL")
            self.assertIsNone(result["snapshot"])
            self.assertFalse(native.is_compatible(result))


if __name__ == "__main__":
    unittest.main()
