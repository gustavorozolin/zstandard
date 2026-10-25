import os
import pathlib
import subprocess
import tempfile
import unittest


SCRIPT = pathlib.Path(__file__).parents[1] / "prepare_ios_flutter.sh"
REVISION = "d3b14c876900e553bc736ca19295fc09e3853e8e"


class PrivateFlutterTests(unittest.TestCase):
    def cleanup(self, temporary, folder):
        return subprocess.run(
            ["bash", str(SCRIPT), "--cleanup"],
            env={**os.environ, "RUNNER_TEMP": str(temporary),
                 "ZSTANDARD_IOS_FLUTTER_DIR": str(folder)},
            capture_output=True, text=True, timeout=10,
        )

    def folder(self, root, name, marker=None):
        folder = root / name
        folder.mkdir()
        (folder / "keep").write_text("owned fixture", encoding="utf-8")
        if marker is not None:
            (folder / ".zstandard-ios-flutter").write_text(marker, encoding="utf-8")
        return folder

    def test_unrelated_directory_survives_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary).resolve()
            folder = self.folder(root, "diagnostics", REVISION)
            self.assertNotEqual(self.cleanup(root, folder).returncode, 0)
            self.assertTrue((folder / "keep").is_file())

    def test_missing_marker_survives_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary).resolve()
            folder = self.folder(root, "zstandard-ios-flutter.unowned")
            self.assertNotEqual(self.cleanup(root, folder).returncode, 0)
            self.assertTrue((folder / "keep").is_file())

    def test_unknown_marker_survives_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary).resolve()
            folder = self.folder(root, "zstandard-ios-flutter.foreign", "another SDK")
            self.assertNotEqual(self.cleanup(root, folder).returncode, 0)
            self.assertTrue((folder / "keep").is_file())

    def test_symlink_target_survives_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary).resolve()
            folder = self.folder(root, "target", REVISION)
            link = root / "zstandard-ios-flutter.link"
            link.symlink_to(folder, target_is_directory=True)
            self.assertNotEqual(self.cleanup(root, link).returncode, 0)
            self.assertTrue(link.is_symlink())
            self.assertTrue((folder / "keep").is_file())

    def test_directory_outside_job_temp_survives_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary).resolve()
            job = root / "job"
            job.mkdir()
            folder = self.folder(root, "zstandard-ios-flutter.other-job", REVISION)
            self.assertNotEqual(self.cleanup(job, folder).returncode, 0)
            self.assertTrue((folder / "keep").is_file())

    def test_marked_job_directory_can_be_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary).resolve()
            folder = self.folder(root, "zstandard-ios-flutter.owned", REVISION)
            self.assertEqual(self.cleanup(root, folder).returncode, 0)
            self.assertFalse(folder.exists())


if __name__ == "__main__":
    unittest.main()
