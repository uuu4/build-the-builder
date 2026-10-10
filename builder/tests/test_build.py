"""build.py without the network or Claude: how it reads its command line, and that it always leaves a submission.

The organisers' form runs `build.py {brief_path} {tool_api_path}`: the tool API comes as a second positional file.
A crashed agent is started once more; with no workflow at all the kit's base agent is submitted rather than nothing."""
import asyncio
import json
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "builder"))
import build  # noqa: E402

API = str(ROOT / "tools/openapi.json")


class Inputs(unittest.TestCase):
    def test_positional_openapi_is_the_tool_api(self):
        self.assertEqual(build.split_inputs(["briefs/brief-a.md", API], None), (["briefs/brief-a.md"], API))

    def test_explicit_tools_wins_and_briefs_keep_their_order(self):
        self.assertEqual(build.split_inputs(["briefs/brief-a.md", "briefs/brief-b.md"], "x.json"),
                         (["briefs/brief-a.md", "briefs/brief-b.md"], "x.json"))

    def test_default_tool_api(self):
        self.assertEqual(build.split_inputs(["briefs/brief-a.md"], None)[1], API)

    def test_a_json_that_is_not_openapi_is_a_brief(self):
        d = tempfile.mkdtemp()
        p = pathlib.Path(d) / "notes.json"
        p.write_text(json.dumps({"bank": "x"}))
        self.assertEqual(build.split_inputs([str(p)], None), ([str(p)], API))


class Flow(unittest.TestCase):
    """main() with a fake agent and a fake deploy."""

    def setUp(self):
        self.slot = "test-build-flow"
        self.out = ROOT / "out" / self.slot
        shutil.rmtree(self.out, ignore_errors=True)
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.deployed = []
        self.calls = []

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)
        for p in (ROOT / "traces").glob(self.slot + "-*"):
            p.unlink()
        sub = ROOT / "submission" / f"{self.slot}.workflow.json"
        if sub.exists():
            sub.unlink()

    def fake_deploy(self, slot, wf, export_to=None):
        self.deployed.append(wf)
        return {"workflow_id": "w", "agent_id": "a", "version": 1}

    def run_main(self, agent):
        argv = ["build.py", "briefs/brief-a.md", API, "--slot", self.slot, "--minutes", "30"]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(build, "run_agent", agent), \
                mock.patch("builder.kit.deploy.deploy", self.fake_deploy):
            build.main()

    def test_tool_api_from_the_form_reaches_the_agent(self):
        async def agent(briefs, tool_api, slot, deadline, trace, again=False):
            self.calls.append((briefs, tool_api, again))
            self.out.mkdir(parents=True, exist_ok=True)
            (self.out / "workflow.json").write_text(json.dumps({"nodes": {}, "initial_node": "x"}))
        self.run_main(agent)
        self.assertEqual(self.calls, [(["briefs/brief-a.md"], API, False)])
        self.assertEqual(len(self.deployed), 1)

    def test_a_crashed_agent_is_started_once_more(self):
        async def agent(briefs, tool_api, slot, deadline, trace, again=False):
            self.calls.append(again)
            if not again:
                raise RuntimeError("Claude API: overloaded")
            self.out.mkdir(parents=True, exist_ok=True)
            (self.out / "workflow.json").write_text(json.dumps({"nodes": {}, "initial_node": "x"}))
        self.run_main(agent)
        self.assertEqual(self.calls, [False, True])
        self.assertEqual(self.deployed, [{"nodes": {}, "initial_node": "x"}])

    def test_a_generator_left_behind_is_run_instead_of_a_second_agent(self):
        async def agent(briefs, tool_api, slot, deadline, trace, again=False):
            self.calls.append(again)
            self.out.mkdir(parents=True, exist_ok=True)
            (self.out / "gen.py").write_text("import json, pathlib\n"
                                             f"pathlib.Path({str(self.out / 'workflow.json')!r}).write_text(json.dumps(dict(nodes=dict(), initial_node='g')))\n")
            raise RuntimeError("connection reset")
        self.run_main(agent)
        self.assertEqual(self.calls, [False])
        self.assertEqual(self.deployed[0]["initial_node"], "g")

    def test_nothing_built_submits_the_base_agent(self):
        async def agent(briefs, tool_api, slot, deadline, trace, again=False):
            self.calls.append(again)
            raise RuntimeError("Claude API down")
        self.run_main(agent)
        self.assertEqual(self.calls, [False, True])
        self.assertEqual(self.deployed, [json.load(open(build.FALLBACK))])
        trace = next((ROOT / "traces").glob(self.slot + "-*.jsonl")).read_text()
        self.assertIn("close_fallback", trace)
        self.assertIn("agent_retry", trace)

    def test_no_second_agent_when_too_little_time_is_left(self):
        async def agent(briefs, tool_api, slot, deadline, trace, again=False):
            self.calls.append(again)
            raise RuntimeError("down")
        with mock.patch.object(build, "RETRY_MINUTES", 1000):
            self.run_main(agent)
        self.assertEqual(self.calls, [False])


if __name__ == "__main__":
    unittest.main()
