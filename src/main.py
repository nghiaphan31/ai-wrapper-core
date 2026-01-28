import os
import sys
import argparse
import uuid
from datetime import datetime
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


def _print_help():
    GLOBAL_CONSOLE.print("Available commands:")
    GLOBAL_CONSOLE.print("  gen_code  - Generate/update code via AI (writes files into artifacts/<step_id>/)")
    GLOBAL_CONSOLE.print("  test_ai   - Send a minimal test request to the AI")
    GLOBAL_CONSOLE.print("  clear     - Clear the terminal screen")
    GLOBAL_CONSOLE.print("  help      - Show this help message")
    GLOBAL_CONSOLE.print("  exit      - Quit the CLI")


def main():
    project_name = GLOBAL_CONFIG.get_project_name()
    GLOBAL_CONSOLE.print(f"--- {project_name} CLI ---")
    GLOBAL_CONSOLE.print("System initialized. Ready for Phase A/B workflow.")

    parser = argparse.ArgumentParser()
    parser.add_argument("mode", nargs="?", default="interactive")
    args = parser.parse_args()

    client = None

    try:
        while True:
            user_input = GLOBAL_CONSOLE.input("Command (gen_code, test_ai, help, clear, exit): ")
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

            elif cmd == "gen_code":
                if not client:
                    client = AIClient()

                # 1. Saisie du besoin
                user_request = GLOBAL_CONSOLE.input("Instruction: ")

                # 2. Construction du contexte (La Mémoire)
                GLOBAL_CONSOLE.print("Building project context...")
                project_context = GLOBAL_CONTEXT.build_full_context()

                # 3. Assemblage du prompt User final
                full_user_prompt = f"{user_request}\n\n{project_context}"

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
                    GLOBAL_CONSOLE.print(f"SUCCESS: Generated {len(files)} files in artifacts/{step_id}/")
                    GLOBAL_CONSOLE.print("REVIEW THEM before merging to src/!")
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
