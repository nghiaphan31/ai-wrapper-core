import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from src.config import GLOBAL_CONFIG


@dataclass(frozen=True)
class WorkbenchRunResult:
    returncode: int
    stdout: str
    stderr: str


class WorkbenchRunner:
    """Restricted runner for executing *versioned* workbench scripts.

    Implements REQ_CORE_055 (Workbench Execution Sandbox): execution is strictly
    limited to scripts located under `workbench/scripts/`.

    UX (updated):
      - The CLI `exec` command should accept only a script name (or subpath)
        relative to `workbench/scripts/`, plus any script arguments.
        Examples:
          - exec hello_world.py
          - exec audits/scan_repo.py --flag value

    Security model:
      - Accepts a *relative* path (no absolute paths).
      - Resolves it relative to `<project_root>/workbench/scripts/`.
      - Verifies the resolved path stays inside `workbench/scripts/`.
      - Executes with `subprocess.run` (no shell) and a hard timeout.
      - Captures stdout/stderr.

    Notes:
      - This runner is intentionally narrow: it is not a general command runner.
      - It only runs Python scripts via the current interpreter.
    """

    def __init__(self, project_root: Path | None = None, timeout_s: int = 60):
        self.project_root = (project_root or GLOBAL_CONFIG.project_root).resolve()
        self.timeout_s = int(timeout_s)
        self.workbench_scripts_dir = (self.project_root / "workbench" / "scripts").resolve()

    def _resolve_and_validate(self, script_rel_to_workbench: str) -> Path:
        rel = (script_rel_to_workbench or "").strip()
        if not rel:
            raise ValueError("Empty script path")

        p = Path(rel)
        if p.is_absolute():
            raise ValueError("Absolute paths are forbidden. Provide a path relative to workbench/scripts/.")

        # Resolve relative to workbench/scripts (new simplified UX contract)
        candidate = (self.workbench_scripts_dir / p).resolve()

        # Security check: ensure candidate is within workbench/scripts
        try:
            candidate.relative_to(self.workbench_scripts_dir)
        except Exception:
            raise ValueError("Blocked: script path is outside workbench/scripts/")

        if not candidate.exists():
            raise FileNotFoundError(f"Script not found: {candidate}")

        if not candidate.is_file():
            raise ValueError(f"Not a file: {candidate}")

        if candidate.suffix.lower() != ".py":
            raise ValueError("Only .py scripts are allowed in WorkbenchRunner")

        return candidate

    def run_script(self, script_rel_to_workbench: str, script_args: list[str] | None = None) -> tuple[int, str, str]:
        """Execute a workbench script located under workbench/scripts/.

        Args:
            script_rel_to_workbench: path relative to workbench/scripts/ (e.g. hello_world.py, audits/scan.py)
            script_args: arguments passed through to the script.

        Returns:
            (returncode, stdout, stderr)

        Timeout:
            60 seconds by default.
        """
        script_path = self._resolve_and_validate(script_rel_to_workbench)
        args = list(script_args or [])

        try:
            proc = subprocess.run(
                [sys.executable, str(script_path), *args],
                capture_output=True,
                text=True,
                check=False,
                cwd=str(self.project_root),
                timeout=self.timeout_s,
            )
            return int(proc.returncode), (proc.stdout or ""), (proc.stderr or "")
        except subprocess.TimeoutExpired as e:
            out = (getattr(e, "stdout", None) or "")
            err = (getattr(e, "stderr", None) or "")
            if err:
                err += "\n"
            err += f"[WRAPPER] Workbench script timed out after {self.timeout_s}s"
            return 124, out, err
        except Exception as e:
            return 1, "", f"[WRAPPER] Workbench script execution failed: {e}"
