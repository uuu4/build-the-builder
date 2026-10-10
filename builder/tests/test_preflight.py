"""The machine checks of tools/preflight.py, with the outside world replaced."""
import importlib.util
import pathlib
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("preflight", ROOT / "tools" / "preflight.py")
pf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pf)


class MachineChecks(unittest.TestCase):
    def setUp(self):
        pf.problems.clear()
        pf.notes.clear()
        self.out = mock.patch("builtins.print").start()
        self.addCleanup(mock.patch.stopall)

    def test_missing_sdk_is_a_problem(self):
        def boom(name):
            raise ImportError(name)
        pf.check_sdk(boom)
        self.assertEqual(len(pf.problems), 1)
        self.assertIn("claude_agent_sdk", pf.problems[0])
        pf.problems.clear()
        pf.check_sdk(lambda name: object())
        self.assertEqual(pf.problems, [])

    def test_keys(self):
        pf.check_keys(env={}, which=lambda x: None)
        self.assertEqual(len(pf.problems), 3)                       # both Freya keys and no way to call a model
        pf.problems.clear()
        pf.check_keys(env={"FREYA_API_KEY": "x", "FREYA_BANK_TEAM_KEY": "y"}, which=lambda x: "/usr/bin/claude")
        self.assertEqual(pf.problems, [])
        pf.check_keys(env={"FREYA_API_KEY": "x", "FREYA_BANK_TEAM_KEY": "y", "ANTHROPIC_API_KEY": "z"}, which=lambda x: None)
        self.assertEqual(pf.problems, [])

    def test_unreachable_bank_is_a_warning_not_a_failure(self):
        probe = lambda url, **k: (False, "ConnectionResetError") if "workers.dev" in url else (True, "")      # noqa: E731
        pf.check_network(env={}, probe=probe)
        self.assertEqual(pf.problems, [])
        self.assertTrue(any("NOT reachable" in n for n in pf.notes))

    def test_unreachable_platform_is_a_failure(self):
        pf.check_network(env={}, probe=lambda url, **k: (False, "URLError"))
        self.assertEqual(len(pf.problems), 1)

    def test_old_python(self):
        pf.check_python((3, 9))
        self.assertEqual(len(pf.problems), 1)


if __name__ == "__main__":
    unittest.main()
