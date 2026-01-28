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

    # 2. Parsing des arguments (Squelette basique pour l'instant)
    parser = argparse.ArgumentParser(description="AI Wrapper Core Interface")
    parser.add_argument("mode", nargs="?", help="Mode d'interaction (interactive par défaut)", default="interactive")
    args = parser.parse_args()

    # 3. Simulation d'une boucle interactive simple (Placeholder pour Itération 2)
    try:
        if args.mode == "interactive":
            user_input = GLOBAL_CONSOLE.input("Waiting for command (type 'exit' to quit): ")
            
            if user_input.strip().lower() in ["exit", "quit"]:
                GLOBAL_CONSOLE.print("Shutting down.")
                return

            # Simulation d'action loguée
            event_id = GLOBAL_LEDGER.log_event("user", "cli_command", artifacts=[])
            GLOBAL_CONSOLE.print(f"Command received (Ledger UUID: {event_id})")
            GLOBAL_CONSOLE.print("No AI backend connected yet (Iteration 2).")

    except KeyboardInterrupt:
        GLOBAL_CONSOLE.print("\nInterrupted by user.")
        sys.exit(0)
    except Exception as e:
        GLOBAL_CONSOLE.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
