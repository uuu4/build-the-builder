"""What the build does when the platform or the bank is unreachable."""
import json
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import builder.cli as cli  # noqa: E402
from builder.kit import deploy as kdeploy  # noqa: E402


class FakeRun:
    def __init__(self, stdout="", stderr="", rc=1, write=None):
        self.stdout, self.stderr, self.returncode, self.write = stdout, stderr, rc, write


class TestUnavailable(unittest.TestCase):
    def setUp(self):
        self.slot = "res-test"
        d = ROOT / "out" / self.slot
        d.mkdir(parents=True, exist_ok=True)
        (d / "deployed.json").write_text(json.dumps({"agent_id": "a1"}))
        self.out = d
        self.patches = [mock.patch.object(cli, "minutes_left", return_value=25), mock.patch.object(cli.time, "sleep")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        for f in self.out.glob("*"):
            f.unlink()
        self.out.rmdir()

    def test_unreachable_bank_is_reported_as_unavailable_and_retried_once(self):
        crash = FakeRun(stderr="urllib.error.URLError: <urlopen error [Errno 54] Connection reset by peer>")
        with mock.patch.object(cli.subprocess, "run", return_value=crash) as run, mock.patch("builtins.print") as pr:
            rc = cli.cmd_test(self.slot, ["--brief", "A"])
        self.assertEqual(rc, 3)
        self.assertEqual(run.call_count, 2)
        said = " ".join(str(c.args[0]) for c in pr.call_args_list)
        self.assertIn("TEST_UNAVAILABLE", said)
        self.assertIn("do not change it", said)

    def test_a_bug_in_the_test_command_is_not_called_unavailable(self):
        with mock.patch.object(cli.subprocess, "run", return_value=FakeRun(stderr="KeyError: 'x'")), mock.patch("builtins.print") as pr:
            rc = cli.cmd_test(self.slot, [])
        self.assertEqual(rc, 1)
        self.assertNotIn("TEST_UNAVAILABLE", " ".join(str(c.args[0]) for c in pr.call_args_list))

    def test_timeout_is_unavailable(self):
        def boom(*a, **k):
            raise subprocess.TimeoutExpired("x", 1)
        with mock.patch.object(cli.subprocess, "run", side_effect=boom), mock.patch("builtins.print"):
            self.assertEqual(cli.cmd_test(self.slot, []), 3)

    def test_a_finished_run_passes_through(self):
        def ok(cmd, **k):
            out = pathlib.Path(cmd[cmd.index("--out") + 1])
            out.write_text(json.dumps({"passed": 9, "total": 10, "final": [{"id": "PUB-01", "pass": False}]}))
            return FakeRun(stdout="9 / 10 passed", rc=0)
        with mock.patch.object(cli.subprocess, "run", side_effect=ok), mock.patch("builtins.print"):
            self.assertEqual(cli.cmd_test(self.slot, []), 0)


class TestDeployRetry(unittest.TestCase):
    def test_transient_errors_are_repeated(self):
        calls = {"n": 0}

        def flaky(slot, wf, state_file=None):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("POST /api/v2/workflow -> 502: bad gateway")
            return {"workflow_id": "w", "agent_id": "a", "version": 1}
        with mock.patch.object(kdeploy.freya, "validate_workflow"), mock.patch.object(kdeploy.freya, "save_workflow", side_effect=flaky), \
                mock.patch.object(kdeploy.time, "sleep"):
            self.assertEqual(kdeploy.deploy("s", {"nodes": {}})["workflow_id"], "w")
        self.assertEqual(calls["n"], 3)

    def test_a_rejection_is_not_repeated(self):
        with mock.patch.object(kdeploy.freya, "validate_workflow", side_effect=RuntimeError("POST /api/v2/workflow -> 400: bad node")) as v, \
                mock.patch.object(kdeploy.time, "sleep"):
            with self.assertRaises(RuntimeError):
                kdeploy.deploy("s", {"nodes": {}})
        self.assertEqual(v.call_count, 1)

    def test_failed_export_still_leaves_a_submission_file(self):
        d = pathlib.Path(tempfile.mkdtemp()) / "sub" / "x.workflow.json"
        with mock.patch.object(kdeploy.freya, "validate_workflow"), \
                mock.patch.object(kdeploy.freya, "save_workflow", return_value={"workflow_id": "w", "agent_id": "a"}), \
                mock.patch.object(kdeploy.freya, "export_workflow", side_effect=RuntimeError("GET -> 503: down")), \
                mock.patch.object(kdeploy.time, "sleep"):
            out = kdeploy.deploy("s", {"nodes": {"a": {}}}, export_to=d)
        self.assertIn("platform export failed", out["export"])
        self.assertEqual(json.loads(d.read_text())["workflow"], {"nodes": {"a": {}}})


if __name__ == "__main__":
    unittest.main()
