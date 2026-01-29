import os
import sys
import argparse
import subprocess
import tempfile
import difflib
import shutil
import shlex
from datetime import datetime
from pathlib import Path
from src.config import GLOBAL_CONFIG
from src.audit import GLOBAL_LEDGER
from src.console import GLOBAL_CONSOLE
from src.ai_client import AIClient
from src.artifact_manager import GLOBAL_ARTIFACTS
from src.context_manager import GLOBAL_CONTEXT

SYSTEM_PROMPT_ARCHITECT = """
You are a Senior Python Architect.
You DO NOT chat. You ONLY output JSON.
Your goal is to generate or update code based on the user request and the PROVIDED CONTEXT.

CRITICAL RULES
Consistency Enforcement:
    1. If you modify logic in `src/`, you MUST also generate the corresponding update for `impl-docs/` in the same response.
    2. If you add/rename/remove commands or arguments, you MUST also update the `_print_help` function (or help strings) to reflect these changes immediately.
    Code, Docs, and Help must never be out of sync.

    3. The `traceability_matrix.md` is the project's 'Source of Truth'. Any code generation or documentation update MUST be reflected in this matrix. If a feature is implemented without a Req_ID, you must alert the user to update the Specs first to maintain the Triple-Layer Alignment.

RESPONSE FORMAT:
{
  "thought_process": "Brief explanation...",
  "artifacts": [
    {
      "path": "src/filename.py",
      "operation": "create", 
      "content": "FULL_PYTHON_CODE"
    }
  ]
}

NOTE: If updating an existing file found in context, provide the FULL new content of the file, not just a diff.
"""


def get_input_from_editor(prompt_text: str) -> str:
    """Collect multi-line user input by opening nano on a temporary file.

    Flow:
      1) Create a NamedTemporaryFile
      2) Open nano so the user can type freely
      3) Read back the file content
      4) Delete the temp file

    Returns the full text (may be empty if user saved nothing).
    """
    GLOBAL_CONSOLE.print(f"{prompt_text} (opening nano; save + exit to continue)")

    tf_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w+",
            delete=False,
            encoding="utf-8",
            prefix="AI_TASK_",
            suffix=".txt",
            dir=os.getcwd(),
        ) as tf:
            tf_path = tf.name
            tf.flush()

        # Let the user edit in nano
        subprocess.run(["nano", tf_path], check=False)

        # Read back content
        with open(tf_path, "r", encoding="utf-8") as f:
            return f.read()

    finally:
        if tf_path:
            try:
                os.remove(tf_path)
            except FileNotFoundError:
                pass


def show_diff(
    target_path: str | Path,
    new_content: str,
    title_new: str = "Incoming Change",
) -> bool:
    """Print a colored unified diff between an existing file and new content.

    - Green for added lines (+)
    - Red for deleted lines (-)

    Returns True if there are changes, False otherwise.
    """
    target_path = Path(target_path)

    old_text = ""
    if target_path.exists():
        try:
            old_text = target_path.read_text(encoding="utf-8")
        except Exception:
            # Fallback: treat unreadable as empty to still show full add diff
            old_text = ""

    old_lines = old_text.splitlines(keepends=True)
    new_lines = (new_content or "").splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=str(target_path),
            tofile=title_new,
            lineterm="",
        )
    )

    if not diff_lines:
        GLOBAL_CONSOLE.print(f"No changes for: {target_path}")
        return False

    RED = "\033[31m"
    GREEN = "\033[32m"
    RESET = "\033[0m"

    GLOBAL_CONSOLE.print(f"--- Diff: {target_path} ---")
    for line in diff_lines:
        # Preserve diff headers without color
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            print(line)
            continue

        if line.startswith("+"):
            print(f"{GREEN}{line}{RESET}")
        elif line.startswith("-"):
            print(f"{RED}{line}{RESET}")
        else:
            print(line)

    return True


def review_and_apply(artifact_folder: str | Path, commit_message: str) -> bool:
    """Interactive review of artifacts with atomic accept-all rule.

    Phase 1 (Review):
      - Iterate all files under artifact_folder
      - For each file, compute destination path by stripping the artifact_folder prefix
      - Show diff and ask user to apply
      - If user says 'n' or 'abort' at any time: return False immediately (no copies)

    If all accepted, this function returns True.
    """
    artifact_folder = Path(artifact_folder)
    if not artifact_folder.exists():
        GLOBAL_CONSOLE.error(f"Artifact folder not found: {artifact_folder}")
        return False

    project_root = GLOBAL_CONFIG.project_root

    artifact_files: list[Path] = [p for p in artifact_folder.rglob("*") if p.is_file()]
    artifact_files.sort(key=lambda p: str(p))

    if not artifact_files:
        GLOBAL_CONSOLE.print("No artifact files to review.")
        return False

    GLOBAL_CONSOLE.print(f"Reviewing {len(artifact_files)} artifact file(s) from: {artifact_folder}")

    for artifact_path in artifact_files:
        rel = artifact_path.relative_to(artifact_folder)
        dest_path = (project_root / rel).resolve()

        # Persistent filename context at decision point
        try:
            rel_dest_path = str(dest_path.relative_to(project_root))
        except Exception:
            rel_dest_path = str(dest_path)

        try:
            new_content = artifact_path.read_text(encoding="utf-8")
        except Exception as e:
            GLOBAL_CONSOLE.error(f"Cannot read artifact file {artifact_path}: {e}")
            return False

        has_changes = show_diff(dest_path, new_content, title_new="Artifact (New)")
        if not has_changes:
            # Still ask? spec says prompts for each file; but no changes should be safe to auto-accept.
            # We'll still prompt to keep behavior consistent.
            pass

        while True:
            ans = GLOBAL_CONSOLE.input(f"[{rel_dest_path}] Apply this change? [y/n/abort]: ").strip().lower()
            if ans in {"y", "yes"}:
                break
            if ans in {"n", "no", "abort"}:
                GLOBAL_CONSOLE.print("Aborted: No changes were applied.")
                return False
            GLOBAL_CONSOLE.print("Please answer with 'y', 'n', or 'abort'.")

    # All accepted
    return True


def _run_git_command(args: list[str]) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr).

    This is intentionally tolerant: it never raises, so callers can print friendly errors.
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode, (proc.stdout or ""), (proc.stderr or "")
    except FileNotFoundError:
        return 127, "", "git executable not found"
    except Exception as e:
        return 1, "", str(e)


def _cmd_status() -> None:
    """Print repository status information using git.

    Output:
      1) Header
      2) `git status -s`
      3) `git log -1 --format="%h - %s (%cr)"`

    If git is not available or fails, prints a friendly error message.
    """
    GLOBAL_CONSOLE.print("--- Repository Status ---")

    rc1, out1, err1 = _run_git_command(["status", "-s"])
    if rc1 != 0:
        GLOBAL_CONSOLE.error(
            "Git status is unavailable. Ensure 'git' is installed and you are inside a git repository."
        )
        if err1.strip():
            GLOBAL_CONSOLE.error(f"Details: {err1.strip()}")
        return

    # Print pending changes (can be empty)
    out1 = out1.rstrip("\n")
    if out1.strip():
        GLOBAL_CONSOLE.print(out1)
    else:
        GLOBAL_CONSOLE.print("Working tree clean.")

    rc2, out2, err2 = _run_git_command(["log", "-1", "--format=%h - %s (%cr)"])
    if rc2 != 0:
        GLOBAL_CONSOLE.error(
            "Git log is unavailable. Ensure this repository has commits and git is working correctly."
        )
        if err2.strip():
            GLOBAL_CONSOLE.error(f"Details: {err2.strip()}")
        return

    out2 = out2.strip()
    if out2:
        GLOBAL_CONSOLE.print(out2)


def _estimate_cost_usd(usage_stats: dict) -> tuple[float, float, float]:
    """Estimate USD cost based on token usage using centralized pricing.

    Uses GLOBAL_CONFIG.PRICING_RATES:
      - input_per_1m
      - output_per_1m

    Returns (input_cost, output_cost, total_cost).
    """
    prompt_tokens = int((usage_stats or {}).get("prompt_tokens", 0) or 0)
    completion_tokens = int((usage_stats or {}).get("completion_tokens", 0) or 0)

    rates = getattr(GLOBAL_CONFIG, "PRICING_RATES", {}) or {}
    input_rate = float(rates.get("input_per_1m", 0.0) or 0.0)
    output_rate = float(rates.get("output_per_1m", 0.0) or 0.0)

    in_cost = (prompt_tokens / 1_000_000.0) * input_rate
    out_cost = (completion_tokens / 1_000_000.0) * output_rate
    return in_cost, out_cost, (in_cost + out_cost)


def _format_int(n: int) -> str:
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n)


def _cmd_report() -> None:
    """Display a clean financial & operational dashboard based on audit_log.jsonl."""
    report = GLOBAL_LEDGER.generate_report("all")

    total_tx = int(report.get("total_requests", 0) or 0)
    in_tok = int(report.get("total_input_tokens", 0) or 0)
    out_tok = int(report.get("total_output_tokens", 0) or 0)
    cost = float(report.get("estimated_cost_usd", 0.0) or 0.0)
    ledger_file = str(report.get("ledger_file", "audit_log.jsonl"))

    GLOBAL_CONSOLE.print("--- 📊 Project Report ---")
    GLOBAL_CONSOLE.print(f"Total Transactions: {total_tx}")
    GLOBAL_CONSOLE.print(f"Tokens: In: {_format_int(in_tok)} / Out: {_format_int(out_tok)}")
    GLOBAL_CONSOLE.print(f"Estimated Cost: ${cost:.6f}")
    GLOBAL_CONSOLE.print(f"Ledger File: {ledger_file}")


def _print_help():
    GLOBAL_CONSOLE.print("Available Albert commands:")
    GLOBAL_CONSOLE.print(
        "  implement [-f file] [--scope {full,code,specs,minimal}] - Execute an implementation task based on instructions"
    )
    GLOBAL_CONSOLE.print("  test_ai             - Send a minimal test request to the AI")
    GLOBAL_CONSOLE.print("  status              - Show git working tree status and last commit")
    GLOBAL_CONSOLE.print("  report              - Show aggregated tokens and estimated cost (from audit_log.jsonl)")
    GLOBAL_CONSOLE.print("  clear               - Clear the terminal screen")
    GLOBAL_CONSOLE.print("  help                - Show this help message")
    GLOBAL_CONSOLE.print("  exit                - Quit the CLI")

    GLOBAL_CONSOLE.print("\nOptions for implement:")
    GLOBAL_CONSOLE.print("  -f, --file   Attach a local file (transient context for this request)")
    GLOBAL_CONSOLE.print(
        "  --scope      Context scope to reduce tokens: full (default), code, specs, minimal"
    )


def _extract_attached_files(tokens: list[str]) -> list[str]:
    """Extract file paths passed via -f/--file from a tokenized command line.

    Supported forms:
      - implement -f path/to/file
      - implement --file path/to/file
      - implement -f path1 -f path2

    Returns list of paths as provided (strings). Unknown flags are ignored.
    """
    attached: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in {"-f", "--file"}:
            if i + 1 < len(tokens):
                attached.append(tokens[i + 1])
                i += 2
                continue
            else:
                # Missing value; caller can decide how to handle.
                attached.append("")
                i += 1
                continue
        i += 1
    # Remove empties (invalid) while keeping order
    return [p for p in attached if p]


def _extract_scope(tokens: list[str]) -> str:
    """Extract --scope value from a tokenized command line.

    Supported forms:
      - implement --scope code
      - implement --scope=code

    Returns scope string; defaults to 'full' if not provided/invalid.
    """
    scope = "full"
    allowed = {"full", "code", "specs", "minimal"}

    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("--scope="):
            val = t.split("=", 1)[1].strip().lower()
            if val in allowed:
                scope = val
            i += 1
            continue

        if t == "--scope":
            if i + 1 < len(tokens):
                val = (tokens[i + 1] or "").strip().lower()
                if val in allowed:
                    scope = val
                i += 2
                continue
            i += 1
            continue

        i += 1

    return scope


def _build_adhoc_file_injection(file_paths: list[str]) -> tuple[str, list[str], bool]:
    """Read attached files and build the transient injection block.

    Returns:
      (injection_text, attached_display_names, ok)

    - injection_text: formatted per spec with delimiters.
    - attached_display_names: list of filenames/paths confirmed to user.
    - ok: False if a critical error should abort the implement flow.

    Behavior:
      - FileNotFoundError: prints error and aborts (ok=False) to avoid silent partial context.
      - Other read errors: prints error and aborts.
    """
    if not file_paths:
        return "", [], True

    injection_parts: list[str] = []
    attached_names: list[str] = []

    for fp in file_paths:
        p = Path(fp)
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            GLOBAL_CONSOLE.error(f"Attached file not found: {fp}")
            return "", attached_names, False
        except Exception as e:
            GLOBAL_CONSOLE.error(f"Failed to read attached file '{fp}': {e}")
            return "", attached_names, False

        attached_names.append(str(fp))
        GLOBAL_CONSOLE.print(f"📎 Attached: {p.name}")

        injection_parts.append(f"\n\n--- ATTACHED FILE: {fp} ---\n{content}\n")

    return "".join(injection_parts), attached_names, True


def main():
    # Tool identity header (explicit, independent from project.json naming)
    GLOBAL_CONSOLE.print("--- ALBERT (Your Personal AI Steward) ---")

    project_name = GLOBAL_CONFIG.get_project_name()
    GLOBAL_CONSOLE.print(f"Project: {project_name}")
    GLOBAL_CONSOLE.print("System initialized. Ready for Phase A/B workflow.")

    parser = argparse.ArgumentParser()
    parser.add_argument("mode", nargs="?", default="interactive")
    args = parser.parse_args()

    client = None

    try:
        while True:
            # Persistent project root context at decision point
            user_input = GLOBAL_CONSOLE.input(
                f"[{GLOBAL_CONFIG.project_root}]\nCommand (implement, test_ai, status, report, help, clear, exit): "
            )

            # Use shlex to handle quoted strings and flags correctly
            try:
                tokens = shlex.split(user_input)
            except ValueError as e:
                GLOBAL_CONSOLE.error(f"Failed to parse command: {e}")
                continue

            if not tokens:
                continue

            cmd = tokens[0].strip().lower()

            if cmd in ["exit", "quit"]:
                break

            elif cmd == "help":
                _print_help()

            elif cmd == "clear":
                os.system("clear")

            elif cmd == "status":
                _cmd_status()

            elif cmd == "report":
                _cmd_report()

            elif cmd == "test_ai":
                if not client:
                    client = AIClient()
                client.send_chat_request("You are helpful.", "Say Hello")

            elif cmd == "implement":
                if not client:
                    client = AIClient()

                # Parse ad-hoc file attachments from the original command line
                file_paths = _extract_attached_files(tokens[1:])
                injection_text, _attached, ok = _build_adhoc_file_injection(file_paths)
                if not ok:
                    GLOBAL_CONSOLE.print("❌ Action cancelled: one or more attached files could not be read.")
                    continue

                # Parse context scope
                scope = _extract_scope(tokens[1:])

                # 1. Saisie du besoin (multi-line via nano)
                instruction = get_input_from_editor("Describe the implementation task")

                # Strict Filtering (Zero Waste): do NOT build context or call API if empty
                if not instruction.strip():
                    GLOBAL_CONSOLE.print("❌ Action cancelled: Empty instruction.")
                    continue

                # Append transient context (ad-hoc files) for this request only
                if injection_text:
                    instruction = f"{instruction.rstrip()}\n\n{injection_text.lstrip()}"

                # Session/Step identity (for traceability)
                session_id = datetime.now().strftime("%Y-%m-%d")

                # 2. Construction du contexte (La Mémoire)
                GLOBAL_CONSOLE.print(f"Building project context (Scope: {scope})...")
                project_context = GLOBAL_CONTEXT.build_full_context(scope=scope)

                # 3. Assemblage du prompt User final
                full_user_prompt = f"{instruction}\n\n{project_context}"

                GLOBAL_CONSOLE.print("Requesting Architect AI (expecting JSON)...")

                # 4. Appel API
                json_response, usage_stats = client.send_chat_request(
                    system_prompt=SYSTEM_PROMPT_ARCHITECT,
                    user_prompt=full_user_prompt,
                )

                # 5. Écriture des artefacts
                step_id = f"step_{datetime.now().strftime('%H%M%S')}"
                files = GLOBAL_ARTIFACTS.process_response(
                    session_id="current",
                    step_name=step_id,
                    raw_text=json_response,
                )

                # REQ_DATA_030: generate session manifest after artifacts are processed
                # (even if zero artifacts were produced, we still write an empty manifest)
                try:
                    manifest_rel = GLOBAL_ARTIFACTS.generate_session_manifest(session_id=session_id)
                    GLOBAL_CONSOLE.print(f"📜 Manifest saved: {manifest_rel}")
                except Exception as e:
                    GLOBAL_CONSOLE.error(f"Manifest generation failed: {e}")

                if files:
                    artifact_folder = GLOBAL_CONFIG.project_root / "artifacts" / step_id
                    GLOBAL_CONSOLE.print(f"SUCCESS: Generated {len(files)} files in artifacts/{step_id}/")

                    # 6. Interactive Review & Auto-Merge Workflow
                    commit_message = instruction.strip()
                    should_apply = review_and_apply(artifact_folder=artifact_folder, commit_message=commit_message)

                    if should_apply:
                        # Merge Phase: copy all artifacts to real destinations
                        artifact_files = [p for p in Path(artifact_folder).rglob("*") if p.is_file()]
                        artifact_files.sort(key=lambda p: str(p))

                        for artifact_path in artifact_files:
                            rel = artifact_path.relative_to(artifact_folder)
                            dest_path = (GLOBAL_CONFIG.project_root / rel).resolve()
                            dest_path.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copyfile(artifact_path, dest_path)

                        # Git Phase
                        try:
                            # Use check=True to raise CalledProcessError on failure
                            subprocess.run(["git", "add", "."], check=True)
                            subprocess.run(["git", "commit", "-m", commit_message], check=True)
                            subprocess.run(["git", "push"], check=True)

                            # Audit Ledger transaction (after successful push)
                            GLOBAL_LEDGER.log_transaction(
                                session_id=session_id,
                                user_instruction=instruction.strip(),
                                step_id=step_id,
                                usage_stats=usage_stats,
                                status="success",
                            )

                            # Console: Token Usage + Estimated Cost
                            pt = int((usage_stats or {}).get("prompt_tokens", 0) or 0)
                            ct = int((usage_stats or {}).get("completion_tokens", 0) or 0)
                            tt = int((usage_stats or {}).get("total_tokens", 0) or 0)
                            in_cost, out_cost, total_cost = _estimate_cost_usd(usage_stats)

                            GLOBAL_CONSOLE.print("✅ Success: Changes applied and pushed.")
                            GLOBAL_CONSOLE.print(f"Token Usage: prompt={pt}, completion={ct}, total={tt}")
                            GLOBAL_CONSOLE.print(
                                f"Estimated Cost: input=${in_cost:.6f}, output=${out_cost:.6f}, total=${total_cost:.6f}"
                            )
                        except subprocess.CalledProcessError as e:
                            GLOBAL_CONSOLE.error(f"❌ Git Error: Command failed. {e}")
                            # Do not print Success.
                            # We do not abort the script, just report the error.
                    else:
                        GLOBAL_CONSOLE.print("Changes were not applied.")

                else:
                    GLOBAL_CONSOLE.error("No files generated.")

            else:
                GLOBAL_CONSOLE.error("Unknown command. Type 'help' to see available commands.")

    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
