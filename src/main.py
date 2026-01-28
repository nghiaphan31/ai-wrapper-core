import sys
import argparse
from src.config import GLOBAL_CONFIG
from src.audit import GLOBAL_LEDGER
from src.console import GLOBAL_CONSOLE

def main():
    # 1. Initialisation
    project_name = GLOBAL_CONFIG.get_project_name()
    GLOBAL_CONSOLE.print(f"--- {project_name} CLI ---")
    GLOBAL_CONSOLE.print("System initialized. Ready for Phase A/B workflow.")

    # 2. Parsing des arguments
    parser = argparse.ArgumentParser(description="AI Wrapper Core Interface")
    parser.add_argument("mode", nargs="?", help="Mode d'interaction", default="interactive")
    args = parser.parse_args()

    # 3. Boucle interactive
    try:
        if args.mode == "interactive":
            while True: # Boucle continue
                user_input = GLOBAL_CONSOLE.input("Command (type 'exit' or 'test_ai'): ")
                
                if user_input.strip().lower() in ["exit", "quit"]:
                    GLOBAL_CONSOLE.print("Shutting down.")
                    break

                elif user_input.strip().lower() == "test_ai":
                    # Import à la demande pour initialiser le client seulement maintenant
                    from src.ai_client import AIClient
                    client = AIClient()
                    
                    GLOBAL_CONSOLE.print("Sending 'Hello World' to OpenAI...")
                    response = client.send_chat_request(
                        system_prompt="You are a helpful coding assistant.",
                        user_prompt="Say 'Hello, I am ready to code' and nothing else."
                    )
                    GLOBAL_CONSOLE.print(f"AI Response: {response}")

                else:
                    # Action standard loguée
                    event_id = GLOBAL_LEDGER.log_event("user", "cli_command", artifacts=[])
                    GLOBAL_CONSOLE.print(f"Command received (Ledger UUID: {event_id}) - Not implemented yet.")

    except KeyboardInterrupt:
        GLOBAL_CONSOLE.print("\nInterrupted by user.")
        sys.exit(0)
    except Exception as e:
        GLOBAL_CONSOLE.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
