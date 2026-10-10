"""Code tools of the builder. Each command reads files and writes files.

    python3 -m builder.cli <command> [args]

Commands: tools, lint, compile, deploy, rules-validate
"""
import sys

COMMANDS = {
    "tools": "builder.cli.tools",
    "lint": "builder.cli.lint",
    "compile": "builder.cli.compile",
    "deploy": "builder.cli.deploy",
    "rules-validate": "builder.cli.rules_validate",
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help") or argv[0] not in COMMANDS:
        print(__doc__)
        print("Available:", ", ".join(COMMANDS))
        return 0 if argv and argv[0] in ("-h", "--help") else 2
    import importlib
    return importlib.import_module(COMMANDS[argv[0]]).main(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
