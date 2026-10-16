import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'app/emudeck_controls.sh'


class EmuDeckControlsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sds automap with spaces ')
        self.base = Path(self.temp.name)
        self.backend = self.base / 'EmuDeck backend'
        (self.backend / 'functions').mkdir(parents=True)
        self.config = self.base / 'managed host/Config.json'
        self.config.parent.mkdir()
        self.original = {'input_config': [{'name': 'Old host controller'}],
                         'game_dirs': ['/card/roms'], 'res_scale': 2}
        self.config.write_text(json.dumps(self.original))
        self.proof = self.base / 'launched.json'
        self.consumer = self.base / 'emulator fixture.py'
        self.consumer.write_text('import json,os,sys\nfrom pathlib import Path\n'
                                 'Path(sys.argv[1]).write_text(json.dumps({'
                                 '"config":json.loads(Path(sys.argv[2]).read_text()),'
                                 '"filter":os.environ.get("SDL_GAMECONTROLLER_IGNORE_DEVICES"),'
                                 '"args":sys.argv[3:]}))\n')

    def tearDown(self):
        self.temp.cleanup()

    def run_hook(self, body):
        (self.backend / 'functions/all.sh').write_text(body)
        return subprocess.run(['/bin/bash', str(SCRIPT), str(self.config), str(self.backend),
                               '/usr/bin/python3', str(self.consumer), str(self.proof),
                               str(self.config), '--fullscreen', '/card/a game.xci'],
                              capture_output=True, text=True)

    def test_native_hook_updates_only_controls_and_preserves_exported_filters(self):
        untouched = self.base / 'original EmuDeck Config.json'
        untouched.write_text(json.dumps({'proof': 'keep the original'}))
        body = '''Ryujinx_configFile="''' + str(untouched) + '''"
Ryujinx_set_gamepad_name() {
  export SDL_GAMECONTROLLER_IGNORE_DEVICES='fixture-device-filter'
  /usr/bin/python3 - "$Ryujinx_configFile" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); c=json.loads(p.read_text())
c.update(input_config=[{'name':'Native AutoMap controller'}],game_dirs=['wrong'],res_scale=99)
p.write_text(json.dumps(c))
PY
}
'''
        result = self.run_hook(body)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(self.proof.read_text())
        expected = dict(self.original, input_config=[{'name': 'Native AutoMap controller'}])
        self.assertEqual(value['config'], expected)
        self.assertEqual(value['filter'], 'fixture-device-filter')
        self.assertEqual(value['args'], ['--fullscreen', '/card/a game.xci'])
        self.assertEqual(json.loads(untouched.read_text()), {'proof': 'keep the original'})

    def test_disabled_automap_preserves_manual_host_mapping(self):
        result = self.run_hook('Ryujinx_set_gamepad_name() { return 0; }\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.proof.read_text())['config'], self.original)

    def test_no_controller_in_desktop_keeps_mapping_and_launches(self):
        result = self.run_hook('Ryujinx_set_gamepad_name() { return 1; }\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.proof.read_text())['config'], self.original)

    def test_missing_native_hook_stops_before_emulator_without_disclosing_settings(self):
        result = self.run_hook("echo 'private setting fixture'\ntrue\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.proof.exists())
        self.assertNotIn('private setting fixture', result.stdout + result.stderr)
        self.assertEqual(json.loads(self.config.read_text()), self.original)

    def test_invalid_hook_result_stops_before_emulator(self):
        result = self.run_hook('Ryujinx_set_gamepad_name() { echo \'{"input_config":"invalid"}\' > "$Ryujinx_configFile"; }\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.proof.exists())
        self.assertEqual(json.loads(self.config.read_text()), self.original)


if __name__ == '__main__':
    unittest.main()
