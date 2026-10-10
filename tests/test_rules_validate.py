"""Tests for cli rules-validate, against the kit's Brief A text."""
import json
import pathlib
import unittest

from builder.cli.rules_validate import validate
from builder.cli.tools import build_tools

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS = build_tools(json.loads((ROOT / "tools" / "openapi.json").read_text()))


def table():
    return {
        "brief_id": "brief-a",
        "sources": [{"id": "S1", "path": "briefs/brief-a.md", "kind": "spec", "date": None}],
        "rules": [
            {"id": "R1", "type": "holiday", "value": {"dates": ["2026-10-26"]},
             "source": {"doc": "S1", "quote": "Business days are Monday to Friday, except Freya Bank holidays"},
             "confidence": "certain", "applies_to": ["all"]},
            {"id": "R2", "type": "statement", "value": {"when": "after_promise", "gist": "text message"},
             "source": {"doc": "S1", "quote": "You will receive a text message confirming this promise."},
             "confidence": "certain", "applies_to": ["all"]},
            {"id": "R3", "type": "identity_fields",
             "value": {"fields": [{"name": "date_of_birth"}, {"name": "phone_last4"}], "max_failures": 3},
             "source": {"doc": "S1", "quote": "Three wrong answers in total end the check"},
             "confidence": "certain", "applies_to": ["all"]},
        ],
    }


class RulesValidate(unittest.TestCase):
    def test_good_table(self):
        rep = validate(table(), ROOT, TOOLS, strict=True)
        self.assertEqual(rep["errors"], [])
        self.assertEqual(rep["effective"], ["R1", "R2", "R3"])

    def test_quote_not_in_source(self):
        t = table(); t["rules"][1]["source"]["quote"] = "You will get a free phone."
        rep = validate(t, ROOT, TOOLS, strict=True)
        self.assertTrue(any("quote not found" in e["msg"] for e in rep["errors"]))
        rep = validate(t, ROOT, TOOLS, strict=False)
        self.assertEqual(rep["errors"], [])
        self.assertIn("R2", rep["uncertain"])

    def test_markdown_and_spacing_are_ignored_in_quotes(self):
        t = table(); t["rules"][0]["source"]["quote"] = "Business days are   Monday to Friday,\nexcept Freya Bank holidays"
        self.assertEqual(validate(t, ROOT, TOOLS, strict=True)["errors"], [])

    def test_supersedes_and_conflicts(self):
        t = table()
        t["rules"].append({"id": "R4", "type": "holiday", "value": {"dates": ["2026-10-27"]}, "supersedes": "R1",
                           "source": {"doc": "S1", "quote": "Business days are Monday to Friday"}, "applies_to": ["all"]})
        rep = validate(t, ROOT, TOOLS, strict=True)
        self.assertEqual(rep["superseded"], ["R1"])
        self.assertNotIn("R1", rep["effective"])
        self.assertEqual(rep["errors"], [])
        t["rules"][3].pop("supersedes")
        rep = validate(t, ROOT, TOOLS, strict=True)
        self.assertTrue(any("conflict" in e["msg"] for e in rep["errors"]))
        self.assertEqual(validate(t, ROOT, TOOLS, strict=False)["errors"], [])

    def test_cycle_and_unknown_supersedes(self):
        t = table(); t["rules"][0]["supersedes"] = "R9"
        self.assertTrue(any("unknown rule" in e["msg"] for e in validate(t, ROOT, TOOLS, strict=True)["errors"]))
        t = table(); t["rules"][0]["supersedes"] = "R2"; t["rules"][1]["supersedes"] = "R1"
        self.assertTrue(any("cycle" in e["msg"] for e in validate(t, ROOT, TOOLS, strict=True)["errors"]))

    def test_identity_field_checked_against_tool_api(self):
        t = table(); t["rules"][2]["value"]["fields"].append({"name": "postcode"})
        rep = validate(t, ROOT, TOOLS, strict=True)
        self.assertTrue(any("postcode" in w["msg"] for w in rep["warnings"]))

    def test_empty_table_is_the_only_hard_error_at_build_time(self):
        self.assertTrue(validate({}, ROOT, TOOLS)["errors"])
        self.assertTrue(validate({"rules": []}, ROOT, TOOLS)["errors"])


if __name__ == "__main__":
    unittest.main()
