from pathlib import Path
import tempfile
import unittest
import zipfile
from helpers import ROOT, module


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.installer = module("install_orchestra")
        self.source = ROOT / "orchestra"

    def test_same_files_installed_and_archived(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "orchestra"
            self.installer.install(self.source, target)
            archive = Path(directory) / "orchestra.zip"
            self.installer.build_zip(self.source, archive)
            self.assertEqual(self.installer.manifest(self.source), self.installer.manifest(target))
            self.installer.validate_zip(archive)
            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual(len(bundle.namelist()), len(self.installer.manifest(self.source)))
                self.assertFalse(any('__pycache__' in name or name.endswith('.db') for name in bundle.namelist()))

    def test_existing_skill_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "orchestra"
            target.mkdir()
            (target / "SKILL.md").write_text("Existing user skill")
            backup = self.installer.install(self.source, target)
            self.assertEqual((backup / "SKILL.md").read_text(), "Existing user skill")

    def test_archive_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "unsafe.zip"
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.writestr('orchestra/../../secret', 'bad')
            with self.assertRaises(ValueError):
                self.installer.validate_zip(archive)


if __name__ == "__main__":
    unittest.main()
