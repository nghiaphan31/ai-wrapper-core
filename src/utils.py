import subprocess
from typing import Iterable

from src.console import GLOBAL_CONSOLE


def run_git_command(args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run a git command with captured output.

    Always uses check=False so callers can interpret return codes.
    """
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )


def _combined_git_output(proc: subprocess.CompletedProcess) -> str:
    out = (proc.stdout or "")
    err = (proc.stderr or "")
    return f"{out}\n{err}".lower()


def git_commit_resilient(commit_message: str, cwd: str | None = None) -> bool:
    """Run `git commit -m <msg>` with REQ_CORE_080 resilience.

    Rules:
      - returncode == 0: success
      - returncode == 1 AND output contains "nothing to commit" OR "working tree clean":
          log warning and return True (soft success)
      - else: return False

    This function MUST NOT raise for the "nothing to commit" case.
    """
    proc = run_git_command(["commit", "-m", commit_message], cwd=cwd)

    if proc.returncode == 0:
        return True

    if proc.returncode == 1:
        combined = _combined_git_output(proc)
        if ("nothing to commit" in combined) or ("working tree clean" in combined):
            # Required exact log message per user request
            GLOBAL_CONSOLE.print("[Git] ⚠️ Nothing to commit (clean tree). Proceeding...")
            return True

    details = (proc.stderr or proc.stdout or "").strip()
    if details:
        GLOBAL_CONSOLE.error(
            f"[Git] Commit failed (rc={proc.returncode}). Details: {details}"
        )
    else:
        GLOBAL_CONSOLE.error(f"[Git] Commit failed (rc={proc.returncode}).")
    return False


def git_run_ok(args: list[str], cwd: str | None = None) -> bool:
    """Run an arbitrary git command and return True on rc==0, else False."""
    proc = run_git_command(args, cwd=cwd)
    if proc.returncode == 0:
        return True

    details = (proc.stderr or proc.stdout or "").strip()
    if details:
        GLOBAL_CONSOLE.error(
            f"[Git] Command failed: git {' '.join(args)} (rc={proc.returncode}). Details: {details}"
        )
    else:
        GLOBAL_CONSOLE.error(
            f"[Git] Command failed: git {' '.join(args)} (rc={proc.returncode})."
        )
    return False


def git_add_force_tracked_paths(paths: Iterable[str], cwd: str | None = None) -> bool:
    """Stage only the whitelisted versioned paths.

    Uses: git add -f -- <paths...>
    """
    p = [str(x) for x in paths if str(x).strip()]
    if not p:
        return True
    return git_run_ok(["add", "-f", "--", *p], cwd=cwd)
