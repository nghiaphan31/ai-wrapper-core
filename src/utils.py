import subprocess
from typing import Iterable

from src.console import GLOBAL_CONSOLE


def run_git_command(command_list: list[str], cwd: str | None = None) -> bool:
    """Run a git command with REQ_CORE_080 tolerance.

    CRITICAL BEHAVIOR:
      - Uses check=False to avoid auto-raising and aborting the tool loop.
      - Treats `git commit` exit code 1 with "nothing to commit" / "working tree clean"
        as a soft success (logs info/warning and continues).

    Returns:
      True on success (including tolerant "nothing to commit"), otherwise raises.

    Note:
      This function is intentionally opinionated for the wrapper's Git workflow.
    """
    command_list = list(command_list or [])
    if not command_list:
        raise ValueError("run_git_command: empty command_list")

    # ... existing setup ...

    # CRITICAL CHANGE: check=False to prevent auto-crash
    result = subprocess.run(command_list, capture_output=True, text=True, check=False, cwd=cwd)

    if result.returncode == 0:
        return True  # Success

    stdout_l = (result.stdout or "").lower()

    # Handle "Nothing to commit" as Success
    if result.returncode == 1 and (
        ("nothing to commit" in stdout_l) or ("working tree clean" in stdout_l)
    ):
        # Keep message close to requested behavior; use console manager for transcript.
        GLOBAL_CONSOLE.print("ℹ️  Git: Nothing to commit. Proceeding...")
        return True  # FORCE SUCCESS

    # Real Error Handling
    err = (result.stderr or "").strip() or (result.stdout or "").strip()
    if err:
        GLOBAL_CONSOLE.error(f"❌ Git Error: {err}")
    else:
        GLOBAL_CONSOLE.error("❌ Git Error: Unknown error")

    raise subprocess.CalledProcessError(result.returncode, command_list, output=result.stdout, stderr=result.stderr)


def git_commit_resilient(commit_message: str, cwd: str | None = None) -> bool:
    """Commit with tolerance for empty commits (REQ_CORE_080).

    This delegates to run_git_command so the tolerance logic is centralized.
    """
    try:
        return run_git_command(["git", "commit", "-m", commit_message], cwd=cwd)
    except subprocess.CalledProcessError:
        return False


def git_run_ok(args: list[str], cwd: str | None = None) -> bool:
    """Run an arbitrary git subcommand and return True on success.

    This uses run_git_command and converts exceptions to False.
    """
    try:
        return run_git_command(["git", *list(args or [])], cwd=cwd)
    except subprocess.CalledProcessError:
        return False


def git_add_force_tracked_paths(paths: Iterable[str], cwd: str | None = None) -> bool:
    """Stage only the whitelisted versioned paths.

    Uses: git add -f -- <paths...>
    """
    p = [str(x) for x in paths if str(x).strip()]
    if not p:
        return True
    return git_run_ok(["add", "-f", "--", *p], cwd=cwd)
