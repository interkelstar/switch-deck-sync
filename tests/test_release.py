import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release', ROOT / 'scripts/build_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def test_archives_are_reproducible_and_manifest_matches_actual_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in release.FILES:
                dest = root / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, dest)
            paths = release.build(root)
            hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
            self.assertEqual(hashes, [hashlib.sha256(p.read_bytes()).hexdigest() for p in release.build(root)])
            with zipfile.ZipFile(paths[0]) as z:
                prefix = z.namelist()[0].split('/')[0] + '/'
                manifest = json.loads(z.read(prefix + 'SHA256SUMS.json'))
                for name, expected in manifest.items():
                    self.assertEqual(hashlib.sha256(z.read(prefix + name)).hexdigest(), expected)
                for name in ('Install.desktop', 'install.sh'):
                    self.assertEqual((z.getinfo(prefix + name).external_attr >> 16) & 0o777, 0o755)
                self.assertFalse(any(Path(n).name in release.FORBIDDEN for n in z.namelist()))

    def test_downloaded_desktop_launcher_resolves_its_package_in_a_path_with_spaces(self):
        if not shutil.which('gio'):
            self.skipTest('GLib launcher unavailable')
        with tempfile.TemporaryDirectory(prefix='downloaded installer ') as temp:
            root = Path(temp)
            marker = root / 'was opened'
            (root / 'install.py').write_text('from pathlib import Path\nPath(' + repr(str(marker)) + ').write_text("ok")\n')
            desktop = root / 'Install.desktop'
            shutil.copy2(ROOT / 'Install.desktop', desktop)
            desktop.chmod(0o755)
            result = subprocess.run(['gio', 'launch', str(desktop)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            import time
            for _ in range(20):
                if marker.exists():
                    break
                time.sleep(0.05)
            self.assertTrue(marker.exists(), 'Desktop entry did not launch the neighbouring installer')


if __name__ == '__main__':
    unittest.main()
