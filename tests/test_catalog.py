from datetime import datetime, timezone
import unittest
from helpers import module, snapshot, request


def model(name, efforts=("low", "medium", "high", "xhigh", "max", "ultra"), **changes):
    return {"slug": name, "visibility": "list", "description": "Workhorse model",
            "supported_reasoning_levels": [{"effort": effort} for effort in efforts], **changes}


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = module("catalog")
        self.now = datetime(2026, 9, 30, tzinfo=timezone.utc)

    def build(self, *models, **options):
        return self.catalog.build_catalog({"models": list(models)}, now=options.get("now", self.now))

    def test_new_sol_is_available_without_a_code_allowlist_change(self):
        result = self.build(model("gpt-6-sol"), model("gpt-6.1-sol"))
        self.assertIn("gpt-6.1-sol", result["catalog"])
        self.assertEqual(result["routing_candidates"]["sol"], ["gpt-6.1-sol", "gpt-6-sol"])

    def test_future_versions_are_sorted_numerically(self):
        result = self.build(model("gpt-6.2-sol"), model("gpt-6.10-sol"), model("gpt-7-sol"))
        self.assertEqual(result["routing_candidates"]["sol"], ["gpt-7-sol", "gpt-6.10-sol", "gpt-6.2-sol"])

    def test_models_disappearing_from_the_source_do_not_survive(self):
        before = self.build(model("gpt-5.5"), model("gpt-6.1-sol"))
        after = self.build(model("gpt-6.1-sol"))
        self.assertNotIn("gpt-5.5", after["catalog"])
        self.assertNotEqual(before["catalog_id"], after["catalog_id"])

    def test_retirement_excludes_a_model_even_if_it_remains_in_a_cached_list(self):
        row = model("gpt-5.5", upgrade={"model": "gpt-5.6-sol", "retirement_at": "2026-10-14T19:00:00Z"})
        before = self.build(row)
        after = self.build(row, now=datetime(2026, 10, 14, 19, tzinfo=timezone.utc))
        self.assertIn("gpt-5.5", before["catalog"])
        self.assertEqual(before["model_metadata"]["gpt-5.5"]["replacement"], "gpt-5.6-sol")
        self.assertNotIn("gpt-5.5", after["catalog"])
        self.assertEqual(after["excluded_models"], [{"model": "gpt-5.5", "reason": "retired"}])

    def test_hidden_and_deprecated_models_are_excluded(self):
        result = self.build(model("gpt-reserve", visibility="hide"), model("gpt-6-sol", deprecated=True))
        self.assertEqual(result["catalog"], {})

    def test_invalid_retirement_date_is_not_assumed_to_be_safe(self):
        for value in ("bad", "2026-10-14T19:00:00", 10):
            with self.subTest(value=value):
                result = self.build(model("gpt-5.5", upgrade={"retirement_at": value}))
                self.assertNotIn("gpt-5.5", result["catalog"])

    def test_new_efforts_do_not_expand_the_approved_effort_range(self):
        result = self.build(model("gpt-7-sol", efforts=("low", "max", "ultra", "unknown")))
        self.assertEqual(result["catalog"]["gpt-7-sol"], ["low", "max"])

    def test_native_schema_can_exclude_models_and_efforts(self):
        current = self.build(model("gpt-6.1-sol"), model("gpt-6-luna"))["catalog"]
        filtered = self.catalog.intersect_catalog(current, {"gpt-6.1-sol": ["low", "medium"]})
        self.assertEqual(filtered, {"gpt-6.1-sol": ["low", "medium"]})

    def test_unknown_family_is_visible_without_inventing_a_role(self):
        result = self.build(model("gpt-7-newfamily"))
        self.assertEqual(result["routing_candidates"]["unclassified"], ["gpt-7-newfamily"])

    def test_bad_envelopes_and_duplicate_models_are_rejected(self):
        for value in ({}, {"models": "bad"}, {"models": [model("gpt-6-sol"), model("gpt-6-sol")]}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.catalog.build_catalog(value)

    def test_new_model_leader_and_child_still_obey_effort_ceiling(self):
        policy = module("policy")
        selection = {**snapshot(), "model": "gpt-6.1-sol"}
        current = self.build(model("gpt-6.1-sol"))["catalog"]
        self.assertEqual(policy.validate_selection(selection), [])
        self.assertEqual(policy.validate_dispatch(request(model="gpt-6.1-sol", effort="high"), selection, current), [])
        self.assertIn("EFFORT_CAP_EXCEEDED", policy.validate_dispatch(request(model="gpt-6.1-sol", effort="max"), selection, current))
