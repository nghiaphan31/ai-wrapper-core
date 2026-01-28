import sys
import argparse
import uuid
from datetime import datetime
from src.config import GLOBAL_CONFIG
from src.audit import GLOBAL_LEDGER
from src.console import GLOBAL_CONSOLE

# Imports lazy pour éviter les dépendances circulaires ou erreurs au boot
from src.ai_client import AIClient 
from src.artifact_manager import GLOBAL_ARTIFACTS

SYSTEM_PROMPT_ARCHITECT = """
You are a Senior Python Architect.
You DO NOT chat. You ONLY output JSON.
Your goal is to generate code based on user requests.

RESPONSE FORMAT:
{
  "thought_process": "Brief explanation of architectural choices...",
  "artifacts": [
    {
      "path": "src/filename.py",
      "operation": "create",
      "content": "FULL_PYTHON_CODE_HERE"
    }
  ]
}
"""

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
            user_input = GLOBAL_CONSOLE.input("Command (exit, test_ai, gen_code): ")
            cmd = user_input.strip().lower()

            if cmd in ["exit", "quit"]:
                break

            elif cmd == "test_ai":
                if not client: client = AIClient()
                client.send_chat_request("You are helpful.", "Say Hello")

            elif cmd == "gen_code":
                if not client: client = AIClient()
                
                # Demande à l'utilisateur ce qu'il veut coder
                user_request = GLOBAL_CONSOLE.input("What code do you want to generate? ")
                
                GLOBAL_CONSOLE.print("Requesting Architect AI (expecting JSON)...")
                
                # Appel API avec le System Prompt strict
                json_response = client.send_chat_request(
                    system_prompt=SYSTEM_PROMPT_ARCHITECT,
                    user_prompt=user_request
                )

                # Traitement par Artifact Manager
                step_id = f"step_{datetime.now().strftime('%H%M%S')}"
                files = GLOBAL_ARTIFACTS.process_response(
                    session_id="current", 
                    step_name=step_id, 
                    raw_text=json_response
                )
                
                if files:
                    GLOBAL_CONSOLE.print(f"SUCCESS: Generated {len(files)} files in artifacts/{step_id}/")
                else:
                    GLOBAL_CONSOLE.error("No files generated (check logs or JSON parsing).")

    except KeyboardInterrupt:
        sys.exit(0)

if __name__ == "__main__":
    main()
