"""build.py without the network or Claude: how it reads its command line, and that it always leaves a submission.

The organisers' form runs `build.py {brief_path} {tool_api_path}`: the tool API comes as a second positional file.
A crashed agent is started once more; with no workflow at all the kit's base agent is submitted rather than nothing."""
import asyncio
import json
import os
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


class Trace(unittest.TestCase):
    def test_one_model_response_is_one_call_and_the_close_counts_steps_and_tools(self):
        d = pathlib.Path(tempfile.mkdtemp())
        rows = [{"t": "1", "type": "AssistantMessage", "message_id": "m1", "model": "x", "content": [{"thinking": ""}]},
                {"t": "2", "type": "AssistantMessage", "message_id": "m1", "model": "x", "content": [{"name": "Bash", "input": "ls"}]},
                {"t": "3", "type": "AssistantMessage", "message_id": "m2", "model": "x", "content": [{"text": "done"}]},
                {"t": "4", "type": "event", "kind": "created", **build.shape(json.load(open(ROOT / "examples/base-agent.json")))}]
        (d / "t.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
        build.summary(d / "t.jsonl", d / "t.log")
        text = (d / "t.log").read_text()
        self.assertIn("model calls 2", text)
        self.assertIn("model call 1 (x): Bash: ls", text)
        self.assertNotIn("(thinking)", text)
        self.assertIn('"steps": ', text)
        self.assertIn('"tools": 4', text)                  # the kit README: two steps, four tools

    def test_chat_smoke_test_is_logged_and_ends_the_chat(self):
        import freya
        d = pathlib.Path(tempfile.mkdtemp()); trace = d / "t.jsonl"
        sent = []

        def fake_api(method, path, body=None, **kw):
            sent.append((path, body))
            return {"callId": "c1", "ended": True} if path.endswith("/end") else {"response": "Hello, is this Daniel?", "callId": "c1"}
        with mock.patch.object(freya, "api", fake_api):
            build.smoke("w1", {"first_name": "Daniel"}, trace)
        e = json.loads(trace.read_text())
        self.assertEqual((e["kind"], e["passed"]), ("test", True))
        self.assertEqual([p for p, _ in sent], ["/api/v2/chat/message"] * 2 + ["/api/v2/chat/end"])
        self.assertEqual(sent[1][1]["callId"], "c1")

        def down(method, path, body=None, **kw):       # a workflow that cannot start a call: logged as a failed test, no raise
            raise RuntimeError("POST /api/v2/chat/message -> 500")
        with mock.patch.object(freya, "api", down):
            build.smoke("w1", {}, trace)
        self.assertFalse(json.loads(trace.read_text().splitlines()[-1])["passed"])


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
        # main() sets TRACE_PATH, TOOL_API in os.environ; restored here so later tests do not write into this trace
        with mock.patch.dict(os.environ), mock.patch.object(sys, "argv", argv), mock.patch.object(build, "run_agent", agent), \
                mock.patch("builder.kit.deploy.deploy", self.fake_deploy), mock.patch.object(build, "smoke", lambda *a: None):
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

    def test_a_failed_save_at_the_close_still_leaves_the_submission(self):        # rehearsal, 11 October: 504 at the close
        def failing_deploy(slot, wf, export_to=None):
            raise RuntimeError("POST /api/v2/workflow -> 504: error code: 504")
        async def agent(briefs, tool_api, slot, deadline, trace, again=False):
            self.out.mkdir(parents=True, exist_ok=True)
            (self.out / "workflow.json").write_text(json.dumps({"nodes": {}, "initial_node": "x"}))
            (self.out / "deployed.json").write_text(json.dumps({"workflow_id": "w1", "agent_id": "a1"}))
        self.fake_deploy = failing_deploy
        self.run_main(agent)
        sub = json.load(open(ROOT / "submission" / f"{self.slot}.workflow.json"))
        self.assertEqual((sub["workflow_id"], sub["workflow"]["initial_node"]), ("w1", "x"))
        trace = next((ROOT / "traces").glob(self.slot + "-*.jsonl")).read_text()
        self.assertIn("close_fallback_file", trace)

    def test_no_second_agent_when_too_little_time_is_left(self):
        async def agent(briefs, tool_api, slot, deadline, trace, again=False):
            self.calls.append(again)
            raise RuntimeError("down")
        with mock.patch.object(build, "RETRY_MINUTES", 1000):
            self.run_main(agent)
        self.assertEqual(self.calls, [False])


if __name__ == "__main__":
    unittest.main()
