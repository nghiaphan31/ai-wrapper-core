import shlex
import subprocess
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SafeCommandResult:
    returncode: int
    stdout: str
    stderr: str


class SafeCommandRunner:
    """Restricted runner for read-only system inspection commands.

    REQ_CORE_050 (Safe Local Execution): provide a restricted interface to execute
    read-only commands to verify ground truth state while blocking destructive
    behavior and input injection.

    Security model (best-effort):
      - Strict allowlist of commands.
      - Reject shell chaining / redirection characters.
      - Never uses shell=True.
      - Parses using shlex.split.

    Note:
      This is not a full sandbox. It is a pragmatic, conservative guardrail.
    """

    # Requested allowlist (as strings). Multi-word entries represent exact prefixes.
    ALLOWLIST: list[str] = [
        "tree",
        "ls",
        "dir",
        "git status",
        "git log",
        "git diff",
        "find",
        "grep",
        "cat",
    ]

    # Chaining / redirection characters to reject.
    # (We reject them entirely to avoid shell injection and piping.)
    _REJECT_TOKENS: tuple[str, ...] = ("&&", ";", "|", ">")

    def __init__(self, cwd: str | None = None):
        self.cwd = cwd

    def _contains_rejected_tokens(self, command_str: str) -> bool:
        if not command_str:
            return False
        for tok in self._REJECT_TOKENS:
            if tok in command_str:
                return True
        return False

    def _is_allowlisted(self, tokens: list[str]) -> bool:
        """Check whether tokenized command matches allowlist.

        Rules:
          - Single-word allowlist entries match tokens[0].
          - Multi-word allowlist entries match exact prefix tokens.
            Example: allow "git status" matches ["git","status", ...]
        """
        if not tokens:
            return False

        for allowed in self.ALLOWLIST:
            allowed_tokens = allowed.split()
            if len(allowed_tokens) == 1:
                if tokens[0] == allowed_tokens[0]:
                    return True
            else:
                if tokens[: len(allowed_tokens)] == allowed_tokens:
                    return True

        return False

    def run_safe_command(self, command_str: str) -> SafeCommandResult:
        """Run an allowlisted command safely.

        Args:
          command_str: user-provided command string.

        Returns:
          SafeCommandResult with stdout/stderr captured.

        Raises:
          ValueError: if command is empty, not allowlisted, or contains rejected tokens.
        """
        command_str = (command_str or "").strip()
        if not command_str:
            raise ValueError("Empty command")

        # Security check: reject chaining and redirection characters.
        if self._contains_rejected_tokens(command_str):
            raise ValueError("Rejected unsafe shell operators (&&, ;, |, >)")

        # Split safely (no shell parsing beyond shlex).
        try:
            tokens = shlex.split(command_str)
        except ValueError as e:
            raise ValueError(f"Failed to parse command: {e}")

        if not tokens:
            raise ValueError("Empty command")

        # Allowlist enforcement
        if not self._is_allowlisted(tokens):
            raise ValueError("Command not allowlisted")

        proc = subprocess.run(
            tokens,
            capture_output=True,
            text=True,
            check=False,
            cwd=self.cwd,
        )

        return SafeCommandResult(
            returncode=int(proc.returncode),
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )
