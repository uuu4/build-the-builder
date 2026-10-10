"""Shared helpers for the builder's code tools. Standard library only."""
import json
import os
import pathlib
import time


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _no_braces(text):
    # Freya leaves a literal {{var}} in code and the snippet crashes, so no double brace may appear.
    while "{{" in text or "}}" in text:
        text = text.replace("{{", "{ {").replace("}}", "} }")
    return text


def _sanitize(obj):
    if isinstance(obj, str):
        return _no_braces(obj)
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, dict):
        return {_no_braces(str(k)): _sanitize(v) for k, v in obj.items()}
    return obj


def code_literal(obj):
    """A Python string literal holding obj as JSON, safe to put inside a Freya code snippet.

    The snippet reads it back with json.loads(...). The literal contains no '{{' and no '}}'.
    """
    text = _no_braces(json.dumps(_sanitize(obj), ensure_ascii=True, separators=(", ", ": ")))
    lit = repr(text)
    assert "{{" not in lit and "}}" not in lit
    return lit


def assert_code_safe(code, where="code"):
    if "{{" in code or "}}" in code:
        raise ValueError(f"{where}: contains '{{{{' or '}}}}', Freya would leave it unresolved")
    compile(code, where, "exec")


def event(tool, summary, inputs=(), output=None, **fields):
    """Append one line to the builder's trace, if TRACE_PATH is set (O owns the file)."""
    path = os.environ.get("TRACE_PATH")
    line = {"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "tool": tool, "in": [str(x) for x in inputs],
            "out": str(output) if output else None, "summary": summary, **fields}
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return line
