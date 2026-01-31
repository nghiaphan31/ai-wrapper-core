import subprocess
import sys


def _run_git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    # 1) Collect staged file list
    proc_names = _run_git(["diff", "--cached", "--name-only"])
    if proc_names.returncode != 0:
        sys.stderr.write("ERROR: Failed to run: git diff --cached --name-only\n")
        if (proc_names.stderr or "").strip():
            sys.stderr.write(proc_names.stderr)
        return 2

    names = [ln.strip() for ln in (proc_names.stdout or "").splitlines() if ln.strip()]

    # 2) Collect staged stat
    proc_stat = _run_git(["diff", "--cached", "--stat"])
    if proc_stat.returncode != 0:
        sys.stderr.write("ERROR: Failed to run: git diff --cached --stat\n")
        if (proc_stat.stderr or "").strip():
            sys.stderr.write(proc_stat.stderr)
        return 2

    stat = (proc_stat.stdout or "").rstrip("\n")

    # 3) Print summary
    print("=== GIT PRE-COMMIT SUMMARY (staged / --cached) ===")

    if not names:
        print("No staged files detected. (git diff --cached --name-only is empty)")
        print("\nTip: stage changes with: git add <files>\n")
        return 0

    print(f"Staged files: {len(names)}")
    for p in names:
        print(f"- {p}")

    print("\n--- git diff --cached --stat ---")
    if stat.strip():
        print(stat)
    else:
        print("(empty)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
