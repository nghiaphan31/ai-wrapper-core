from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


TARGET_SCRIPTS = [
    "structural_audit.py",
    "audit_trinity.py",
    "code_logic_extractor.py",
    "deep_semantic_audit.py",
    "git_pre_commit_summary.py",
]


def run(cmd: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return p.returncode, p.stdout, p.stderr


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    scripts_dir = repo_root / "workbench" / "scripts"

    print("=== WORKBENCH TOOLS TRACKING AUDIT ===")
    print(f"Repo root: {repo_root}")
    print(f"Scripts dir: {scripts_dir}")

    if not scripts_dir.exists():
        print("ERROR: workbench/scripts directory not found")
        return 2

    # Determine git tracked status using `git ls-files --error-unmatch`
    untracked: list[str] = []
    missing: list[str] = []
    tracked: list[str] = []

    for name in TARGET_SCRIPTS:
        path = scripts_dir / name
        if not path.exists():
            missing.append(name)
            continue

        rc, _, err = run(["git", "-C", str(repo_root), "ls-files", "--error-unmatch", str(path.relative_to(repo_root))])
        if rc == 0:
            tracked.append(name)
        else:
            # When untracked, git prints: "error: pathspec ... did not match any file(s) known to git"
            untracked.append(name)

    print("\n--- Target scripts status ---")
    print(f"Tracked ({len(tracked)}): {', '.join(tracked) if tracked else '(none)'}")
    print(f"Untracked ({len(untracked)}): {', '.join(untracked) if untracked else '(none)'}")
    print(f"Missing ({len(missing)}): {', '.join(missing) if missing else '(none)'}")

    # Also print `git status --porcelain` lines for workbench/scripts for context
    rc, out, err = run(["git", "-C", str(repo_root), "status", "--porcelain", "workbench/scripts"]) 
    print("\n--- git status --porcelain workbench/scripts ---")
    if out.strip():
        print(out.rstrip())
    else:
        print("(clean)")
    if err.strip():
        print("[stderr]", err.rstrip())

    # Check traceability_matrix.md for REQ_ARCH_020/021 mentions
    tm_path = repo_root / "traceability_matrix.md"
    print("\n--- Traceability check (REQ_ARCH_020 / REQ_ARCH_021) ---")
    if not tm_path.exists():
        print("traceability_matrix.md: NOT FOUND")
    else:
        text = tm_path.read_text(encoding="utf-8", errors="replace")
        found_020 = "REQ_ARCH_020" in text
        found_021 = "REQ_ARCH_021" in text
        print(f"traceability_matrix.md present: yes")
        print(f"Contains REQ_ARCH_020: {found_020}")
        print(f"Contains REQ_ARCH_021: {found_021}")

        # Provide a small snippet context if found
        for req in ("REQ_ARCH_020", "REQ_ARCH_021"):
            if req in text:
                idx = text.index(req)
                start = max(0, idx - 200)
                end = min(len(text), idx + 400)
                snippet = text[start:end]
                print(f"\nSnippet around {req}:\n---\n{snippet}\n---")

    # Exit code indicates whether any targets are untracked (useful for chaining decisions)
    if untracked:
        print("\nRESULT: One or more target scripts appear UNTRACKED.")
        return 10
    print("\nRESULT: No target scripts appear untracked (or they are missing).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
