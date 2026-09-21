import json
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from sohib import onboarding as app
from sohib.tools.config import ToolSettings


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.env = patch.dict(os.environ, {'SOHIB_HOME': str(self.root)}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_setup_private_idempotent_and_independent_of_checkout(self):
        app.setup()
        first = app.read_config()
        self.assertEqual(app.setup()['status'], 'configured')
        self.assertEqual(app.read_config(), first)
        if sys.platform != 'win32':
            self.assertEqual((self.root / 'config.json').stat().st_mode & 0o777, 0o600)
        settings = ToolSettings.load()
        self.assertEqual(settings.mode, 'browser')
        self.assertEqual(settings.connection_file, str(self.root / 'browser.json'))
        self.assertEqual(settings.profile, str(self.root / 'chrome'))

    def test_explicit_environment_wins(self):
        app.setup()
        with patch.dict(
            os.environ,
            {'STOCKBIT_MODE': 'fixture', 'STOCKBIT_BROWSER_CONNECTION_FILE': '/tmp/explicit.json'},
        ):
            settings = ToolSettings.load()
        self.assertEqual(settings.mode, 'fixture')
        self.assertEqual(settings.connection_file, str(Path('/tmp/explicit.json').resolve()))

    def test_existing_connection_never_launches_replacement(self):
        path = self.root / 'existing.json'
        path.write_text(json.dumps({'endpoint': 'http://127.0.0.1:12345'}))
        app.setup(path, self.root / 'original-profile')
        with (
            patch.object(app, 'endpoint_alive', return_value=False),
            patch.object(app.subprocess, 'Popen') as launch,
        ):
            with self.assertRaisesRegex(ValueError, 'no replacement'):
                app.connect()
            launch.assert_not_called()

    def test_running_browser_reused(self):
        app.setup()
        with (
            patch.object(app, 'endpoint_alive', return_value=True),
            patch.object(app.subprocess, 'Popen') as launch,
        ):
            self.assertEqual(app.connect()['status'], 'browser_running')
            launch.assert_not_called()

    def test_explicit_connect_preserves_profile_across_restarts(self):
        app.setup()
        with (
            patch.object(app, 'endpoint_alive', side_effect=[False, False, True]),
            patch.object(app, 'chrome_path', return_value='/test/chrome'),
            patch.object(app.subprocess, 'Popen') as launch,
        ):
            self.assertEqual(app.connect()['status'], 'browser_opened')
            args = launch.call_args.args[0]
            self.assertIn(f'--user-data-dir={self.root / "chrome"}', args)
            self.assertIn('--remote-debugging-port=0', args)
        self.assertEqual(app.read_config()['profile'], str(self.root / 'chrome'))

    def test_configs_share_installed_executable_and_user_state(self):
        app.setup()
        codex = tomllib.loads(app.harness_config('codex'))['mcp_servers']['sohib']
        for client in ['claude', 'mcp', 'openclaw']:
            entry = json.loads(app.harness_config(client))['mcpServers']['sohib']
            self.assertEqual(entry['command'], codex['command'])
            self.assertEqual(entry['env'], codex['env'])
            self.assertEqual(entry['env']['SOHIB_HOME'], str(self.root))

    def test_defaults_without_setup_live_in_private_home(self):
        settings = ToolSettings.load()
        self.assertEqual(settings.mode, 'disabled')
        self.assertEqual(settings.connection_file, str(self.root / 'browser.json'))
        self.assertEqual(settings.profile, str(self.root / 'chrome'))

    def test_corrupt_config_fails_without_fallback(self):
        (self.root / 'config.json').write_text('{bad')
        with self.assertRaisesRegex(ValueError, 'invalid'):
            ToolSettings.load()
