import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release', ROOT / 'scripts/build_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def test_launcher_uses_gio_environment_if_desktop_field_is_missing(self):
        with tempfile.TemporaryDirectory(prefix='installer fallback ') as temp:
            root = Path(temp)
            marker = root / 'opened'
            (root / 'install.py').write_text('from pathlib import Path\nPath(' + repr(str(marker)) + ').touch()\n')
            desktop = root / 'Install.desktop'
            shutil.copy2(ROOT / 'Install.desktop', desktop)
            command = next(line[5:] for line in desktop.read_text().splitlines() if line.startswith('Exec='))
            args = shlex.split(command)
            self.assertEqual(args.pop(), '%k')
            env = {k: v for k, v in os.environ.items() if k not in ('LD_LIBRARY_PATH', 'PYTHONHOME', 'PYTHONPATH')}
            env['GIO_LAUNCHED_DESKTOP_FILE'] = str(desktop)
            result = subprocess.run(args, capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(marker.exists())

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
        env = {k: v for k, v in os.environ.items() if k not in ('LD_LIBRARY_PATH', 'PYTHONHOME', 'PYTHONPATH')}
        probe = subprocess.run(['/usr/bin/python3', '-c', 'from gi.repository import Gio; assert Gio.DesktopAppInfo'],
                               env=env, capture_output=True)
        if probe.returncode:
            self.skipTest('System Python GObject bindings unavailable; required in CI')
        with tempfile.TemporaryDirectory(prefix='downloaded installer ') as temp:
            root = Path(temp)
            marker = root / 'was opened'
            (root / 'install.py').write_text('from pathlib import Path\nPath(' + repr(str(marker)) + ').write_text("ok")\n')
            desktop = root / 'Install.desktop'
            shutil.copy2(ROOT / 'Install.desktop', desktop)
            desktop.chmod(0o755)
            # Match a file manager: load the desktop file by filename. Older
            # `gio launch` implementations reconstruct it from a keyfile, losing
            # its filename and therefore both %k and GIO_LAUNCHED_DESKTOP_FILE.
            code = 'import sys; from gi.repository import Gio; app=Gio.DesktopAppInfo.new_from_filename(sys.argv[1]); assert app; app.launch([],None)'
            result = subprocess.run(['/usr/bin/python3', '-c', code, str(desktop)], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            import time
            for _ in range(100):
                if marker.exists():
                    break
                time.sleep(0.05)
            self.assertTrue(marker.exists(), 'Desktop entry did not launch the neighbouring installer: ' + result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
