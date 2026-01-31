import os
import sys
import argparse
import subprocess
import tempfile
import difflib
import shutil
import shlex
import uuid
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
from src.workbench_runner import WorkbenchRunner

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

AUTONOMOUS REBOUND PROTOCOL (specs/10_autonomous_rebound_protocol.md):
- You MAY request the wrapper to execute a workbench script (read-only inspection / audit / analysis) and then chain another AI call.
- To do so, include a top-level JSON field `next_action` in your response (separate from `artifacts`).
- This is the ONLY autonomous action supported in v1.

JSON Schema (v1) for `next_action`:
{
  "type": "exec_and_chain",
  "target_script": "workbench/scripts/<path>.py",
  "continuation_prompt": "Explain what to do next after seeing the system output"
}

Rules:
- `type` MUST be exactly: "exec_and_chain".
- `target_script` MUST be a project-root relative path and MUST start with: "workbench/scripts/".
- No shell commands. Only Python scripts under workbench/scripts/.
- The wrapper will execute the script, capture STDOUT/STDERR/returncode, and feed it back to you.

RESPONSE FORMAT:
{
  "thought_process": "Brief explanation...",
  "artifacts": [
    {
      "path": "src/filename.py",
      "operation": "create",
      "content": "FULL_PYTHON_CODE"
    }
  ],
  "next_action": {
    "type": "exec_and_chain",
    "target_script": "workbench/scripts/...",
    "continuation_prompt": "..."
  }
}

NOTE: If updating an existing file found in context, provide the FULL new content of the file, not just a diff.
"""


def _echo_external_editor_input_to_console_and_transcript(content: str) -> None:
    """Echo external editor input into the normal console/log stream.

    REQ_AUDIT_031 (External Input Echo): Any input captured via an external editor
    MUST be explicitly echoed to the console transcript immediately upon capture.

    Output format:
      [USER_INPUT_ECHO]
      > line 1
      > line 2
      [END_INPUT]
    """
    text = content if content is not None else ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    GLOBAL_CONSOLE.print("[USER_INPUT_ECHO]")

    if text == "":
        GLOBAL_CONSOLE.print(">")
    else:
        for line in text.split("\n"):
            GLOBAL_CONSOLE.print(f"> {line}")

    GLOBAL_CONSOLE.print("[END_INPUT]")


def get_input_from_editor(prompt_text: str) -> str:
    """Collect multi-line user input by opening nano on a temporary file."""
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

    all_files = [p for p in artifact_folder.rglob("*") if p.is_file()]

    # On exclut les fichiers .meta.json et les traces brutes
    artifact_files = [
        p for p in all_files
        if not p.name.endswith(".meta.json")
        and p.name != "raw_response_trace.jsonl"
    ]
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


def _normalize_exec_script_arg(raw: str) -> str:
    """Normalize the user-provided exec script argument."""
    s = (raw or "").strip()
    if not s:
        return s

    s_norm = s.replace("\\", "/")

    prefixes = [
        "workbench/scripts/",
        "./workbench/scripts/",
        "./workbench/./scripts/",
    ]

    for pref in prefixes:
        if s_norm.startswith(pref):
            s_norm = s_norm[len(pref) :]
            break

    return s_norm


def _cmd_exec(tokens: list[str]) -> None:
    """Execute a workbench script via WorkbenchRunner."""
    if len(tokens) < 2:
        GLOBAL_CONSOLE.error(
            "Usage: exec <script.py> [args...] (script must be located in workbench/scripts/)"
        )
        return

    rel_script = _normalize_exec_script_arg(tokens[1])
    script_args = tokens[2:]

    runner = WorkbenchRunner(project_root=GLOBAL_CONFIG.project_root, timeout_s=60)

    try:
        rc, out, err = runner.run_script(rel_script, script_args=script_args)
    except Exception as e:
        GLOBAL_CONSOLE.error(f"Workbench exec blocked/failed: {e}")
        return

    GLOBAL_CONSOLE.print("--- Workbench Exec ---")
    GLOBAL_CONSOLE.print(f"Script: workbench/scripts/{rel_script}")
    if script_args:
        GLOBAL_CONSOLE.print(f"Args: {' '.join(script_args)}")
    GLOBAL_CONSOLE.print(f"Return code: {rc}")

    if (out or "").strip():
        GLOBAL_CONSOLE.print("[STDOUT]")
        GLOBAL_CONSOLE.print(out.rstrip("\n"))
    else:
        GLOBAL_CONSOLE.print("[STDOUT] (empty)")

    if (err or "").strip():
        GLOBAL_CONSOLE.print("[STDERR]")
        GLOBAL_CONSOLE.print(err.rstrip("\n"))
    else:
        GLOBAL_CONSOLE.print("[STDERR] (empty)")


def _print_help():
    GLOBAL_CONSOLE.print("Available Albert commands:")
    GLOBAL_CONSOLE.print(
        "  prompt [-f file] [--scope {full,code,specs,minimal}] - Send a prompt/task to Albert's AI brain (generates JSON artifacts)"
    )
    GLOBAL_CONSOLE.print(
        "  implement [-f file] [--scope {full,code,specs,minimal}] - Backward-compatible alias for 'prompt'"
    )
    GLOBAL_CONSOLE.print(
        "  exec <script.py> [args...] - Execute a Python script located in workbench/scripts/ (restricted sandbox)"
    )
    GLOBAL_CONSOLE.print("  test_ai              - Send a minimal test request to the AI")
    GLOBAL_CONSOLE.print("  status               - Show git working tree status and last commit")
    GLOBAL_CONSOLE.print("  report               - Show aggregated tokens and estimated cost (from audit_log.jsonl)")
    GLOBAL_CONSOLE.print("  clear                - Clear the terminal screen")
    GLOBAL_CONSOLE.print("  help                 - Show this help message")
    GLOBAL_CONSOLE.print("  exit                 - Quit the CLI")

    GLOBAL_CONSOLE.print("\nOptions for prompt/implement:")
    GLOBAL_CONSOLE.print("  -f, --file   Attach a local file (transient context for this request)")
    GLOBAL_CONSOLE.print("  --scope      Context scope to reduce tokens: full (default), code, specs, minimal")

    GLOBAL_CONSOLE.print("\nOptions for exec:")
    GLOBAL_CONSOLE.print("  exec <script.py> [args...]")
    GLOBAL_CONSOLE.print("    - The script MUST exist under: workbench/scripts/")
    GLOBAL_CONSOLE.print("    - Provide the path relative to workbench/scripts/ (recommended):")
    GLOBAL_CONSOLE.print("        exec hello_world.py")
    GLOBAL_CONSOLE.print("        exec audits/scan_repo.py --flag value")
    GLOBAL_CONSOLE.print("    - For backward-compatibility, these are also accepted:")
    GLOBAL_CONSOLE.print("        exec workbench/scripts/hello_world.py")
    GLOBAL_CONSOLE.print("    - Only .py allowed; timeout=60s")


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


def _get_head_commit_sha(cwd: str) -> str | None:
    """Return current HEAD commit SHA (full) or None if unavailable."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            cwd=cwd,
        )
    except FileNotFoundError:
        return None
    except Exception:
        return None

    if proc.returncode != 0:
        return None

    sha = (proc.stdout or "").strip()
    return sha or None


def _validate_next_action_target(target_script: str) -> tuple[bool, str, str]:
    """Validate next_action target_script.

    Returns:
      (ok, normalized_rel_to_workbench, error_message)

    Security constraints (REQ_AUTO_040):
      - must be project-root relative and strictly under workbench/scripts/
      - must not be absolute and must not contain path traversal

    Note:
      WorkbenchRunner expects a path relative to workbench/scripts/.
    """
    t = (target_script or "").strip().replace("\\", "/")
    if not t:
        return False, "", "next_action.target_script is empty"

    if t.startswith("/"):
        return False, "", "next_action.target_script must be project-root relative (absolute path forbidden)"

    if not t.startswith("workbench/scripts/"):
        return False, "", "next_action.target_script must start with 'workbench/scripts/'"

    rel = t[len("workbench/scripts/") :]
    if not rel:
        return False, "", "next_action.target_script missing script name after workbench/scripts/"

    # Basic traversal hard-stop (WorkbenchRunner also validates after resolve)
    if ".." in Path(rel).parts:
        return False, "", "next_action.target_script contains path traversal ('..')"

    return True, rel, ""


def _run_prompt_flow(tokens: list[str], client: AIClient) -> None:
    """Run the main AI prompt -> artifacts -> (optional rebound loop) -> review/apply -> git -> audit flow.

    Implements specs/10_autonomous_rebound_protocol.md (REQ_AUTO_010..050).

    Traceability:
      - Every AI response is printed to console/transcript.
      - Every rebound exec output is printed to console/transcript.
      - Intermediate exec steps are logged to GLOBAL_LEDGER.

    Safety:
      - Rebound loop is bounded by MAX_LOOPS.
      - Execution is restricted to workbench/scripts/ via WorkbenchRunner.
      - No git commit/push until the final response (i.e., when next_action is None).
    """
    session_id = datetime.now().strftime("%Y-%m-%d")

    file_paths = _extract_attached_files(tokens[1:])
    injection_text, _attached, ok = _build_adhoc_file_injection(file_paths)
    if not ok:
        GLOBAL_CONSOLE.print("❌ Action cancelled: one or more attached files could not be read.")
        return

    scope = _extract_scope(tokens[1:])

    instruction = ""
    usage_stats: dict = {}

    # Rebound loop state
    MAX_LOOPS = 5
    loop_idx = 0

    # Track ALL artifacts generated across rebound turns (for Trinity warnings + final review)
    all_generated_files: list[str] = []
    final_step_id: str | None = None

    try:
        instruction = get_input_from_editor("Describe the prompt/task for Albert's AI brain")

        if not instruction.strip():
            GLOBAL_CONSOLE.print("❌ Action cancelled: Empty instruction.")
            return

        if injection_text:
            instruction = f"{instruction.rstrip()}\n\n{injection_text.lstrip()}"

        GLOBAL_CONSOLE.print(f"Building project context (Scope: {scope})...")
        project_context = GLOBAL_CONTEXT.build_full_context(scope=scope)

        # Initial user prompt (turn 0)
        current_user_prompt = f"{instruction}\n\n{project_context}"

        runner = WorkbenchRunner(project_root=GLOBAL_CONFIG.project_root, timeout_s=60)

        while True:
            loop_idx += 1
            if loop_idx > MAX_LOOPS:
                GLOBAL_CONSOLE.error(f"⛔ Rebound safety break: exceeded MAX_LOOPS={MAX_LOOPS}")
                break

            GLOBAL_CONSOLE.print(f"Requesting Architect AI (expecting JSON)... [turn {loop_idx}/{MAX_LOOPS}]")

            json_response, usage_stats = client.send_chat_request(
                system_prompt=SYSTEM_PROMPT_ARCHITECT,
                user_prompt=current_user_prompt,
            )

            # Traceability: print AI brain response to screen + transcript.
            GLOBAL_CONSOLE.print("[AI_RESPONSE_BEGIN]")
            GLOBAL_CONSOLE.print(json_response or "")
            GLOBAL_CONSOLE.print("[AI_RESPONSE_END]")

            step_id = _generate_step_id()
            final_step_id = step_id

            files, next_action = GLOBAL_ARTIFACTS.process_response(
                session_id="current",
                step_name=step_id,
                raw_text=json_response,
                enable_rebound=True,
            )
            all_generated_files.extend(list(files or []))

            if files:
                GLOBAL_CONSOLE.print(f"SUCCESS: Generated {len(files)} files in artifacts/{step_id}/")
            else:
                GLOBAL_CONSOLE.print(f"No artifact files generated in artifacts/{step_id}/")

            # REQ_AUTO_030: if next_action present, execute and chain
            if next_action:
                na_type = (next_action.get("type") or "").strip()
                target_script = (next_action.get("target_script") or "").strip()
                continuation_prompt = (next_action.get("continuation_prompt") or "").strip()

                if na_type != "exec_and_chain":
                    GLOBAL_CONSOLE.error(f"⚠️ Invalid next_action.type: {na_type}")
                    # Treat as terminal (do not loop) to avoid arbitrary behaviors
                    break

                ok_target, rel_to_workbench, err_msg = _validate_next_action_target(target_script)
                if not ok_target:
                    GLOBAL_CONSOLE.error(f"⛔ Security: blocked next_action target_script. Reason: {err_msg}")
                    # Feed diagnostic back to AI for correction
                    system_output_block = (
                        "System Output:\n"
                        f"[STDOUT]\n\n"
                        f"[STDERR]\n{err_msg}\n\n"
                        f"[RETURN_CODE]\n1\n"
                    )
                    current_user_prompt = f"{system_output_block}\n\n{continuation_prompt}".strip()

                    GLOBAL_LEDGER.log_event(
                        actor="wrapper",
                        action_type="rebound_exec_blocked",
                        payload_ref=None,
                        artifacts=[
                            f"artifacts/{step_id}/raw_response_trace.jsonl",
                        ],
                    )
                    continue

                # Execute script (sandboxed)
                GLOBAL_CONSOLE.print("--- REBOUND EXECUTION (autonomous) ---")
                GLOBAL_CONSOLE.print(f"Next Action Type: {na_type}")
                GLOBAL_CONSOLE.print(f"Target Script: {target_script}")

                rc, out, err = runner.run_script(rel_to_workbench, script_args=[])

                # Print intermediate outputs to console/transcript
                GLOBAL_CONSOLE.print(f"Return code: {rc}")
                GLOBAL_CONSOLE.print("[STDOUT]")
                GLOBAL_CONSOLE.print((out or "").rstrip("\n") if (out or "").strip() else "(empty)")
                GLOBAL_CONSOLE.print("[STDERR]")
                GLOBAL_CONSOLE.print((err or "").rstrip("\n") if (err or "").strip() else "(empty)")

                # Ledger log intermediate step
                GLOBAL_LEDGER.log_event(
                    actor="wrapper",
                    action_type="rebound_exec",
                    payload_ref=None,
                    artifacts=[
                        f"workbench/scripts/{rel_to_workbench}",
                        f"artifacts/{step_id}/raw_response_trace.jsonl",
                    ],
                )

                # Construct chaining prompt
                system_output_block = (
                    "System Output:\n"
                    f"[STDOUT]\n{out or ''}\n\n"
                    f"[STDERR]\n{err or ''}\n\n"
                    f"[RETURN_CODE]\n{rc}\n"
                )

                # Requirement text: "System Output:\n[STDOUT]...\n\n[Continuation Prompt]..."
                current_user_prompt = f"{system_output_block}\n\n{continuation_prompt}".strip()

                # Loop again
                continue

            # No next_action: final response reached
            break

    except Exception as e:
        GLOBAL_CONSOLE.error(f"❌ Tool/AI execution failed: {e}")
        all_generated_files = []
        usage_stats = {}
        final_step_id = final_step_id or _generate_step_id()

    # Final step: review/apply only if we have a final step folder and any generated files
    if final_step_id and all_generated_files:
        artifact_folder = GLOBAL_CONFIG.project_root / "artifacts" / final_step_id

        commit_message = (instruction or "").strip() or f"Prompt changes ({final_step_id})"
        should_apply = review_and_apply(artifact_folder=artifact_folder, commit_message=commit_message)

        if should_apply:
            artifact_files = [p for p in Path(artifact_folder).rglob("*") if p.is_file()]
            artifact_files.sort(key=lambda p: str(p))

            for artifact_path in artifact_files:
                rel = artifact_path.relative_to(artifact_folder)
                dest_path = (GLOBAL_CONFIG.project_root / rel).resolve()
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(artifact_path, dest_path)

            git_ok = True
            head_sha: str | None = None
            try:
                paths = ["project.json", "src", "specs", "impl-docs", "notes", "workbench"]
                git_ok = git_add_force_tracked_paths(paths, cwd=str(GLOBAL_CONFIG.project_root))

                if git_ok:
                    git_ok = git_commit_resilient(commit_message, cwd=str(GLOBAL_CONFIG.project_root))

                if git_ok:
                    git_ok = git_run_ok(["push"], cwd=str(GLOBAL_CONFIG.project_root))

                if git_ok:
                    head_sha = _get_head_commit_sha(cwd=str(GLOBAL_CONFIG.project_root))

            except Exception as e:
                git_ok = False
                GLOBAL_CONSOLE.error(f"❌ Git Error: unexpected failure: {e}")

            if git_ok:
                GLOBAL_LEDGER.log_transaction(
                    session_id=session_id,
                    user_instruction=(instruction or "").strip(),
                    step_id=final_step_id,
                    usage_stats=usage_stats,
                    status="success",
                )

                pt = int((usage_stats or {}).get("prompt_tokens", 0) or 0)
                ct = int((usage_stats or {}).get("completion_tokens", 0) or 0)
                tt = int((usage_stats or {}).get("total_tokens", 0) or 0)
                in_cost, out_cost, total_cost = _estimate_cost_usd(usage_stats)

                if head_sha:
                    GLOBAL_CONSOLE.print(f"✅ Success: Changes applied and pushed. (commit: {head_sha})")
                else:
                    GLOBAL_CONSOLE.print("✅ Success: Changes applied and pushed.")

                GLOBAL_CONSOLE.print(f"Token Usage: prompt={pt}, completion={ct}, total={tt}")
                GLOBAL_CONSOLE.print(
                    f"Estimated Cost: input=${in_cost:.6f}, output=${out_cost:.6f}, total=${total_cost:.6f}"
                )
            else:
                GLOBAL_CONSOLE.error(
                    "Git workflow did not complete successfully. Your changes may be applied locally but not committed/pushed."
                )

        else:
            GLOBAL_CONSOLE.print("Changes were not applied.")

        # Trinity warning check (best-effort)
        try:
            rel_artifacts = []
            for abs_path in all_generated_files:
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
                f"[{GLOBAL_CONFIG.project_root}]\nCommand (prompt, implement, exec, test_ai, status, report, help, clear, exit): "
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

            if cmd == "exec":
                _cmd_exec(tokens)
                continue

            if cmd == "test_ai":
                if not client:
                    client = AIClient()

                GLOBAL_CONSOLE.print("Waiting for AI...")
                response_text, _stats = client.send_chat_request("You are helpful.", "Say Hello")
                GLOBAL_CONSOLE.print(f"\n🤖 AI Response:\n{response_text}\n")
                continue

            # New canonical command
            if cmd == "prompt":
                if not client:
                    client = AIClient()
                _run_prompt_flow(tokens=tokens, client=client)
                continue

            # Backward-compatible alias
            if cmd == "implement":
                if not client:
                    client = AIClient()
                GLOBAL_CONSOLE.print("ℹ️  'implement' is deprecated; use 'prompt' instead.")
                _run_prompt_flow(tokens=tokens, client=client)
                continue

            GLOBAL_CONSOLE.error("Unknown command. Type 'help' to see available commands.")

    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
