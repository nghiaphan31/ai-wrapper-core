import os
import sys
import argparse
import uuid
import subprocess
import tempfile
import difflib
import shutil
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


def show_diff(target_path: str | Path, new_content: str) -> bool:
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
            tofile=str(target_path),
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

        try:
            new_content = artifact_path.read_text(encoding="utf-8")
        except Exception as e:
            GLOBAL_CONSOLE.error(f"Cannot read artifact file {artifact_path}: {e}")
            return False

        has_changes = show_diff(dest_path, new_content)
        if not has_changes:
            # Still ask? spec says prompts for each file; but no changes should be safe to auto-accept.
            # We'll still prompt to keep behavior consistent.
            pass

        while True:
            ans = GLOBAL_CONSOLE.input("Apply this change? [y/n/abort]: ").strip().lower()
            if ans in {"y", "yes"}:
                break
            if ans in {"n", "no", "abort"}:
                GLOBAL_CONSOLE.print("Aborted: No changes were applied.")
                return False
            GLOBAL_CONSOLE.print("Please answer with 'y', 'n', or 'abort'.")

    # All accepted
    return True


def _print_help():
    GLOBAL_CONSOLE.print("Available Albert commands:")
    GLOBAL_CONSOLE.print("  implement - Execute an implementation task based on instructions")
    GLOBAL_CONSOLE.print("  test_ai   - Send a minimal test request to the AI")
    GLOBAL_CONSOLE.print("  clear     - Clear the terminal screen")
    GLOBAL_CONSOLE.print("  help      - Show this help message")
    GLOBAL_CONSOLE.print("  exit      - Quit the CLI")


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
            user_input = GLOBAL_CONSOLE.input("Command (implement, test_ai, help, clear, exit): ")
            cmd = user_input.strip().lower()

            if cmd in ["exit", "quit"]:
                break

            elif cmd == "help":
                _print_help()

            elif cmd == "clear":
                os.system("clear")

            elif cmd == "test_ai":
                if not client:
                    client = AIClient()
                client.send_chat_request("You are helpful.", "Say Hello")

            elif cmd == "implement":
                if not client:
                    client = AIClient()

                # 1. Saisie du besoin (multi-line via nano)
                instruction = get_input_from_editor("Describe the implementation task")

                # Strict Filtering (Zero Waste): do NOT build context or call API if empty
                if not instruction.strip():
                    GLOBAL_CONSOLE.print("❌ Action cancelled: Empty instruction.")
                    continue

                # 2. Construction du contexte (La Mémoire)
                GLOBAL_CONSOLE.print("Building project context...")
                project_context = GLOBAL_CONTEXT.build_full_context()

                # 3. Assemblage du prompt User final
                full_user_prompt = f"{instruction}\n\n{project_context}"

                GLOBAL_CONSOLE.print("Requesting Architect AI (expecting JSON)...")

                # 4. Appel API
                json_response = client.send_chat_request(
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
                        subprocess.run(["git", "add", "."], check=False)
                        subprocess.run(["git", "commit", "-m", commit_message], check=False)
                        subprocess.run(["git", "push"], check=False)

                        GLOBAL_CONSOLE.print("✅ Success: Changes applied and pushed.")
                    else:
                        GLOBAL_CONSOLE.print("Changes were not applied.")

                else:
                    GLOBAL_CONSOLE.error("No files generated.")

            elif cmd == "":
                # Ignore empty input
                continue

            else:
                GLOBAL_CONSOLE.error("Unknown command. Type 'help' to see available commands.")

    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
