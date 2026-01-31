from __future__ import annotations

import argparse
from pathlib import Path
import sys


def count_lines_exact(path: Path) -> int:
    # Exact line count = number of '\n' line breaks plus 1 if file is non-empty and doesn't end with '\n'
    # But the simplest exact definition for "number of lines" in text files is:
    #   len(file.read().splitlines())
    # which counts the last line even if it lacks a trailing newline.
    text = path.read_text(encoding="utf-8", errors="replace")
    return len(text.splitlines())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Count exact number of lines in a file.")
    parser.add_argument(
        "path",
        nargs="?",
        default="src/main.py",
        help="Project-root relative path to file (default: src/main.py)",
    )
    args = parser.parse_args(argv)

    project_root = Path.cwd().resolve()
    target = (project_root / args.path).resolve()

    # Ensure target is within project root for safety
    try:
        target.relative_to(project_root)
    except Exception:
        print(f"ERROR: Target path escapes project root: {target}", file=sys.stderr)
        return 2

    if not target.exists() or not target.is_file():
        print(f"ERROR: File not found: {args.path}", file=sys.stderr)
        return 2

    n = count_lines_exact(target)
    # Stable, parseable output
    print(f"{args.path}\t{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
