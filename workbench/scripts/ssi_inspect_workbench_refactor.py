import json
from pathlib import Path

# This script is intended to be executed by the wrapper's Safe System Inspection tool runner.
# It only prints read-only inspection information.


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[ERROR READING {p}: {e}]"


def main() -> int:
    root = Path.cwd().resolve()

    targets = [
        "traceability_matrix.md",
        "specs",
        "impl-docs",
        "src",
        "workbench",
    ]

    report = {
        "project_root": str(root),
        "exists": {},
        "tree_snippets": {},
        "git": {},
        "files": {},
    }

    for t in targets:
        p = root / t
        report["exists"][t] = {
            "path": str(p),
            "exists": p.exists(),
            "is_dir": p.is_dir(),
            "is_file": p.is_file(),
        }

    # Capture key file contents (limited) for alignment decisions
    for fp in [
        "traceability_matrix.md",
        "impl-docs/06_tooling_protocol.md",
        "impl-docs/01_core_system.md",
        "src/main.py",
        "src/ai_client.py",
    ]:
        p = root / fp
        report["files"][fp] = {
            "exists": p.exists(),
            "size": p.stat().st_size if p.exists() else None,
            "head": _read_text(p)[:2000] if p.exists() else None,
        }

    # Print a small directory listing for workbench/scripts and src/scripts
    for d in ["workbench", "workbench/scripts", "src/scripts"]:
        p = root / d
        if p.exists() and p.is_dir():
            try:
                report["tree_snippets"][d] = sorted([str(x.relative_to(root)) for x in p.rglob("*") if x.is_file()])[:200]
            except Exception as e:
                report["tree_snippets"][d] = [f"[ERROR: {e}]"]
        else:
            report["tree_snippets"][d] = None

    # Git status summary (read-only)
    # The wrapper will execute git commands; here we just print placeholders.
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
