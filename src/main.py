import os
import sys
import argparse
import subprocess
import tempfile
import difflib
import shutil
import shlex
import uuid
import re
from datetime import datetime
from pathlib import Path
from src.config import GLOBAL_CONFIG
from src.audit import GLOBAL_LEDGER
from src.console import GLOBAL_CONSOLE
from src.ai_client import AIClient
from src.artifact_manager import GLOBAL_ARTIFACTS
from src.context_manager import GLOBAL_CONTEXT
from src.system_tools import SafeCommandRunner
from src.utils import git_add_force_tracked_paths, git_commit_resilient, git_run_ok

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

TOOLS / GROUND TRUTH INSPECTION (REQ_CORE_050):
You have access to a `run_safe_command` tool to inspect the file system (ls, tree) and git status.
Use this to verify reality before making assumptions.

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


def _echo_external_editor_input_to_console_and_transcript(content: str) -> None:
    """Echo external editor input into the normal console/log stream.

    REQ_AUDIT_031 (External Input Echo): Any input captured via an external editor
    MUST be explicitly echoed to the console transcript immediately upon capture,
    so transcript reconstruction does not require guessing what was typed in Nano.

    Output format:
      [USER_INPUT_ECHO]
      > line 1
      > line 2
      [END_INPUT]

    Notes:
      - Uses GLOBAL_CONSOLE.print so it is guaranteed to land in sessions/<date>/transcript.log.
      - Preserves empty input as an explicit empty block.
    """
    text = content if content is not None else ""
    # Normalize line endings for stable transcript rendering
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    GLOBAL_CONSOLE.print("[USER_INPUT_ECHO]")

    if text == "":
        # Explicitly record emptiness (still reconstructable)
        GLOBAL_CONSOLE.print(">")
    else:
        for line in text.split("\n"):
            GLOBAL_CONSOLE.print(f"> {line}")

    GLOBAL_CONSOLE.print("[END_INPUT]")


def get_input_from_editor(prompt_text: str) -> str:
    """Collect multi-line user input by opening nano on a temporary file.

    Flow:
      1) Create a NamedTemporaryFile
      2) Open nano so the user can type freely
      3) Read back the file content
      4) Echo content into transcript immediately (REQ_AUDIT_031)
      5) Delete the temp file

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

        subprocess.run(["nano", tf_path], check=False)

        with open(tf_path, "r", encoding="utf-8") as f:
            content = f.read()

        _echo_external_editor_input_to_console_and_transcript(content)

        return content

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
    """Interactive review of artifacts with atomic accept-all rule."""
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

        try:
            rel_dest_path = str(dest_path.relative_to(project_root))
        except Exception:
            rel_dest_path = str(dest_path)

        try:
            new_content = artifact_path.read_text(encoding="utf-8")
        except Exception as e:
            GLOBAL_CONSOLE.error(f"Cannot read artifact file {artifact_path}: {e}")
            return False

        _ = show_diff(dest_path, new_content, title_new="Artifact (New)")

        while True:
            ans = GLOBAL_CONSOLE.input(f"[{rel_dest_path}] Apply this change? [y/n/abort]: ").strip().lower()
            if ans in {"y", "yes"}:
                break
            if ans in {"n", "no", "abort"}:
                GLOBAL_CONSOLE.print("Aborted: No changes were applied.")
                return False
            GLOBAL_CONSOLE.print("Please answer with 'y', 'n', or 'abort'.")

    return True


def _cmd_status() -> None:
    """Print repository status information using git."""
    GLOBAL_CONSOLE.print("--- Repository Status ---")

    try:
        proc1 = subprocess.run(["git", "status", "-s"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        GLOBAL_CONSOLE.error("Git status is unavailable. Ensure 'git' is installed and you are inside a git repository.")
        return

    if proc1.returncode != 0:
        GLOBAL_CONSOLE.error("Git status is unavailable. Ensure 'git' is installed and you are inside a git repository.")
        if (proc1.stderr or "").strip():
            GLOBAL_CONSOLE.error(f"Details: {(proc1.stderr or '').strip()}")
        return

    out1 = (proc1.stdout or "").rstrip("\n")
    if out1.strip():
        GLOBAL_CONSOLE.print(out1)
    else:
        GLOBAL_CONSOLE.print("Working tree clean.")

    proc2 = subprocess.run(
        ["git", "log", "-1", "--format=%h - %s (%cr)"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc2.returncode != 0:
        GLOBAL_CONSOLE.error("Git log is unavailable. Ensure this repository has commits and git is working correctly.")
        if (proc2.stderr or "").strip():
            GLOBAL_CONSOLE.error(f"Details: {(proc2.stderr or '').strip()}")
        return

    out2 = (proc2.stdout or "").strip()
    if out2:
        GLOBAL_CONSOLE.print(out2)


def _estimate_cost_usd(usage_stats: dict) -> tuple[float, float, float]:
    """Estimate USD cost based on token usage using centralized pricing."""
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
    GLOBAL_CONSOLE.print("  --scope      Context scope to reduce tokens: full (default), code, specs, minimal")


def _extract_attached_files(tokens: list[str]) -> list[str]:
    attached: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in {"-f", "--file"}:
            if i + 1 < len(tokens):
                attached.append(tokens[i + 1])
                i += 2
                continue
            attached.append("")
            i += 1
            continue
        i += 1
    return [p for p in attached if p]


def _extract_scope(tokens: list[str]) -> str:
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
        except PermissionError as e:
            GLOBAL_CONSOLE.error(f"Permission error reading attached file '{fp}': {e}")
            return "", attached_names, False
        except Exception as e:
            GLOBAL_CONSOLE.error(f"Failed to read attached file '{fp}': {e}")
            return "", attached_names, False

        attached_names.append(str(fp))
        GLOBAL_CONSOLE.print(f"📎 Attached: {p.name}")

        injection_parts.append(f"\n\n--- ATTACHED FILE: {fp} ---\n{content}\n")

    return "".join(injection_parts), attached_names, True


def _generate_step_id(now: datetime | None = None) -> str:
    dt = now or datetime.now()
    timestamp = dt.strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:4]
    return f"step_{timestamp}_{short_id}"


def _trinity_protocol_consistency_check(generated_artifacts: list[str]) -> None:
    if not generated_artifacts:
        return

    norm = []
    for p in generated_artifacts:
        if not p:
            continue
        s = str(p).replace("\\", "/")
        norm.append(s)

    has_src = any("/src/" in p or p.startswith("src/") for p in norm)
    if not has_src:
        return

    has_impl_docs = any("/impl-docs/" in p or p.startswith("impl-docs/") for p in norm)
    has_specs = any("/specs/" in p or p.startswith("specs/") for p in norm)

    if has_src and (not has_impl_docs or not has_specs):
        print("⚠️  TRINITY PROTOCOL WARNING")
        print("--------------------------")
        print("Code changes detected, but Specs/Docs were not updated in this session.")
        print("Please verify alignment manually or ask for a retrofit.")


def _run_tool_script_and_capture(project_root: Path, script_path: Path, timeout_s: int = 20) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(project_root),
            timeout=timeout_s,
        )
        return int(proc.returncode), (proc.stdout or ""), (proc.stderr or "")
    except subprocess.TimeoutExpired as e:
        out = (getattr(e, "stdout", None) or "")
        err = (getattr(e, "stderr", None) or "")
        err = (err + "\n" if err else "") + f"[WRAPPER] Tool script timed out after {timeout_s}s"
        return 124, out, err
    except Exception as e:
        return 1, "", f"[WRAPPER] Tool script execution failed: {e}"


def _append_system_message_to_transcript(text: str) -> None:
    GLOBAL_CONSOLE.print(text)


def main():
    GLOBAL_CONSOLE.print("--- ALBERT (Your Personal AI Steward) ---")

    project_name = GLOBAL_CONFIG.get_project_name()
    GLOBAL_CONSOLE.print(f"Project: {project_name}")
    GLOBAL_CONSOLE.print("System initialized. Ready for Phase A/B workflow.")

    parser = argparse.ArgumentParser()
    parser.add_argument("mode", nargs="?", default="interactive")
    _args = parser.parse_args()

    client = None

    _safe_runner = SafeCommandRunner(cwd=str(GLOBAL_CONFIG.project_root))
    _ = _safe_runner  # reserved for future CLI exposure

    try:
        while True:
            user_input = GLOBAL_CONSOLE.input(
                f"[{GLOBAL_CONFIG.project_root}]\nCommand (implement, test_ai, status, report, help, clear, exit): "
            )

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

            if cmd == "help":
                _print_help()
                continue

            if cmd == "clear":
                os.system("clear")
                continue

            if cmd == "status":
                _cmd_status()
                continue

            if cmd == "report":
                _cmd_report()
                continue

            if cmd == "test_ai":
                if not client:
                    client = AIClient()
                client.send_chat_request("You are helpful.", "Say Hello")
                continue

            if cmd == "implement":
                if not client:
                    client = AIClient()

                session_id = datetime.now().strftime("%Y-%m-%d")

                file_paths = _extract_attached_files(tokens[1:])
                injection_text, _attached, ok = _build_adhoc_file_injection(file_paths)
                if not ok:
                    GLOBAL_CONSOLE.print("❌ Action cancelled: one or more attached files could not be read.")
                    continue

                scope = _extract_scope(tokens[1:])

                # TOOL EXECUTION / AI LOOP (isolated from Git). Even if Git later warns/fails,
                # tool execution has already happened and must not be blocked.
                try:
                    instruction = get_input_from_editor("Describe the implementation task")

                    if not instruction.strip():
                        GLOBAL_CONSOLE.print("❌ Action cancelled: Empty instruction.")
                        continue

                    if injection_text:
                        instruction = f"{instruction.rstrip()}\n\n{injection_text.lstrip()}"

                    GLOBAL_CONSOLE.print(f"Building project context (Scope: {scope})...")
                    project_context = GLOBAL_CONTEXT.build_full_context(scope=scope)

                    full_user_prompt = f"{instruction}\n\n{project_context}"

                    GLOBAL_CONSOLE.print("Requesting Architect AI (expecting JSON)...")

                    json_response, usage_stats = client.send_chat_request(
                        system_prompt=SYSTEM_PROMPT_ARCHITECT,
                        user_prompt=full_user_prompt,
                    )

                    step_id = _generate_step_id()
                    files = GLOBAL_ARTIFACTS.process_response(
                        session_id="current",
                        step_name=step_id,
                        raw_text=json_response,
                    )

                except Exception as e:
                    GLOBAL_CONSOLE.error(f"❌ Tool/AI execution failed: {e}")
                    files = []
                    usage_stats = {}
                    step_id = _generate_step_id()
                    instruction = ""

                if files:
                    artifact_folder = GLOBAL_CONFIG.project_root / "artifacts" / step_id
                    GLOBAL_CONSOLE.print(f"SUCCESS: Generated {len(files)} files in artifacts/{step_id}/")

                    commit_message = (instruction or "").strip() or f"Implement changes ({step_id})"
                    should_apply = review_and_apply(artifact_folder=artifact_folder, commit_message=commit_message)

                    if should_apply:
                        artifact_files = [p for p in Path(artifact_folder).rglob("*") if p.is_file()]
                        artifact_files.sort(key=lambda p: str(p))

                        for artifact_path in artifact_files:
                            rel = artifact_path.relative_to(artifact_folder)
                            dest_path = (GLOBAL_CONFIG.project_root / rel).resolve()
                            dest_path.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copyfile(artifact_path, dest_path)

                        # GIT PHASE (separate from tool execution)
                        git_ok = True
                        try:
                            paths = ["project.json", "src", "specs", "impl-docs", "notes", "workbench"]
                            git_ok = git_add_force_tracked_paths(paths, cwd=str(GLOBAL_CONFIG.project_root))

                            if git_ok:
                                # REQ_CORE_080: empty commit must be treated as SUCCESS (Warning)
                                git_ok = git_commit_resilient(commit_message, cwd=str(GLOBAL_CONFIG.project_root))

                            if git_ok:
                                git_ok = git_run_ok(["push"], cwd=str(GLOBAL_CONFIG.project_root))

                        except Exception as e:
                            git_ok = False
                            GLOBAL_CONSOLE.error(f"❌ Git Error: unexpected failure: {e}")

                        if git_ok:
                            GLOBAL_LEDGER.log_transaction(
                                session_id=session_id,
                                user_instruction=(instruction or "").strip(),
                                step_id=step_id,
                                usage_stats=usage_stats,
                                status="success",
                            )

                            pt = int((usage_stats or {}).get("prompt_tokens", 0) or 0)
                            ct = int((usage_stats or {}).get("completion_tokens", 0) or 0)
                            tt = int((usage_stats or {}).get("total_tokens", 0) or 0)
                            in_cost, out_cost, total_cost = _estimate_cost_usd(usage_stats)

                            GLOBAL_CONSOLE.print("✅ Success: Changes applied and pushed.")
                            GLOBAL_CONSOLE.print(f"Token Usage: prompt={pt}, completion={ct}, total={tt}")
                            GLOBAL_CONSOLE.print(
                                f"Estimated Cost: input=${in_cost:.6f}, output=${out_cost:.6f}, total=${total_cost:.6f}"
                            )
                        else:
                            # Must not crash; tool execution already completed.
                            GLOBAL_CONSOLE.error(
                                "Git workflow did not complete successfully. Your changes may be applied locally but not committed/pushed."
                            )

                    else:
                        GLOBAL_CONSOLE.print("Changes were not applied.")

                    try:
                        rel_artifacts = []
                        for abs_path in files:
                            try:
                                p = Path(abs_path)
                                rel = p.relative_to(artifact_folder)
                                rel_artifacts.append(str(rel))
                            except Exception:
                                rel_artifacts.append(str(abs_path))
                        _trinity_protocol_consistency_check(rel_artifacts)
                    except Exception:
                        pass

                else:
                    GLOBAL_CONSOLE.error("No files generated.")

                try:
                    manifest_rel = GLOBAL_ARTIFACTS.generate_session_manifest(session_id=session_id)
                    if manifest_rel:
                        GLOBAL_CONSOLE.print(f"📜  Session Manifest saved: {manifest_rel}")
                    else:
                        GLOBAL_CONSOLE.error("Manifest was not saved (see earlier errors).")
                except Exception as e:
                    GLOBAL_CONSOLE.error(f"Manifest generation failed: {e}")

                continue

            GLOBAL_CONSOLE.error("Unknown command. Type 'help' to see available commands.")

    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
