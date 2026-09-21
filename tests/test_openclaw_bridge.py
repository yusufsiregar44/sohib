import argparse
import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'integrations/openclaw/bridge.py'
SPEC = importlib.util.spec_from_file_location('sohib_openclaw_bridge', PATH)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class OpenClawBridgeTests(unittest.TestCase):
    def test_uses_installed_python_and_explicit_config_from_another_directory(self):
        with (
            patch.dict(os.environ, {'SOHIB_HOME': '/private/sohib'}, clear=True),
            patch.object(bridge.shutil, 'which', return_value='/usr/bin/node'),
            patch.object(bridge, 'python_executable', return_value='/env/bin/python'),
            patch.object(Path, 'is_file', return_value=True),
        ):
            argv, env = bridge.command(argparse.Namespace(command='list'))
        self.assertEqual(argv[argv.index('--cwd') + 1], str(bridge.ROOT))
        self.assertEqual(argv[argv.index('--config') + 1], str(bridge.HERE / 'mcporter.json'))
        self.assertEqual(argv[argv.index('--stdio') + 1], '/env/bin/python')
        self.assertEqual(argv[argv.index('--stdio-arg') + 3], 'sohib.interfaces.mcp_server')
        self.assertEqual(env['STOCKBIT_MODE'], 'browser')
        # Session paths come from `sohib setup`, not from the checkout.
        self.assertEqual(env['SOHIB_HOME'], '/private/sohib')
        self.assertNotIn('STOCKBIT_BROWSER_CONNECTION_FILE', env)
        self.assertNotIn('--persist', argv)

    def test_python_resolution_prefers_override_then_installed_package(self):
        with patch.dict(os.environ, {'SOHIB_PYTHON': '/override/python'}):
            self.assertEqual(bridge.python_executable(), '/override/python')
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(bridge.importlib.util, 'find_spec', return_value=object()),
        ):
            self.assertEqual(bridge.python_executable(), bridge.sys.executable)

    def test_arguments_are_one_json_argument_without_shell_interpolation(self):
        query = 'a "quote"; $(not-a-command)'
        args = argparse.Namespace(
            command='call', tool='search_companies', arguments=json.dumps({'query': query})
        )
        with (
            patch.object(bridge.shutil, 'which', return_value='/usr/bin/node'),
            patch.object(bridge, 'python_executable', return_value='/env/bin/python'),
            patch.object(Path, 'is_file', return_value=True),
        ):
            argv, _ = bridge.command(args)
        self.assertEqual(json.loads(argv[argv.index('--args') + 1]), {'query': query})

    def test_missing_dependency_is_actionable(self):
        with patch.object(bridge.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'npm ci'):
                bridge.command(argparse.Namespace(command='list'))
