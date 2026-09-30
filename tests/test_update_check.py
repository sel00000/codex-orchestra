import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError
from helpers import module


class UpdateCheckTests(unittest.TestCase):
    def setUp(self):
        self.updates = module("update_check")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.release = Path(self.temp.name) / "release.json"
        self.release.write_text('{"schema_version":1,"version":"1.1.0"}')

    def read(self, value):
        with patch.object(self.updates, "urlopen", return_value=io.BytesIO(json.dumps(value).encode())) as opened:
            result = self.updates.check_update(self.release)
        self.assertEqual(opened.call_args.kwargs["timeout"], 4)
        self.assertEqual(opened.call_args.args[0].full_url, self.updates.RELEASE_URL)
        self.assertFalse(result["automatic_install"])
        return result

    def test_newer_release_produces_a_notification(self):
        result = self.read({"schema_version": 1, "version": "1.2.0"})
        self.assertEqual(result["status"], "update_available")
        self.assertEqual(self.release.read_text(), '{"schema_version":1,"version":"1.1.0"}')

    def test_equal_release_is_up_to_date(self):
        self.assertEqual(self.read({"schema_version": 1, "version": "1.1.0"})["status"], "up_to_date")

    def test_local_newer_release_is_not_downgraded(self):
        self.assertEqual(self.read({"schema_version": 1, "version": "1.0.0"})["status"], "local_ahead")

    def test_network_failure_is_unverified(self):
        with patch.object(self.updates, "urlopen", side_effect=URLError("offline")):
            result = self.updates.check_update(self.release)
        self.assertEqual(result["status"], "unverified")
        self.assertEqual(result["installed_version"], "1.1.0")

    def test_bad_release_schema_and_payload_are_rejected(self):
        for value in ({"schema_version": 2, "version": "1.2.0"}, {"schema_version": 1, "version": "run code"}):
            with self.subTest(value=value):
                self.assertEqual(self.read(value)["status"], "unverified")
        with patch.object(self.updates, "urlopen", return_value=io.BytesIO(b'x' * 8193)):
            self.assertEqual(self.updates.check_update(self.release)["status"], "unverified")
