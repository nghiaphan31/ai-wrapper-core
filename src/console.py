import sys
import os
from datetime import datetime
from pathlib import Path
from src.config import GLOBAL_CONFIG

class ConsoleManager:
    def __init__(self):
        self.project_root = GLOBAL_CONFIG.project_root
        # Détermine la session du jour (YYYY-MM-DD)
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.session_dir = self.project_root / "sessions" / self.today
        self.transcript_file = self.session_dir / "transcript.log"
        
        self._ensure_session_ready()

    def _ensure_session_ready(self):
        """S'assure que le dossier de session du jour et le fichier log existent."""
        if not self.session_dir.exists():
            self.session_dir.mkdir(parents=True, exist_ok=True)
        
        if not self.transcript_file.exists():
            # En-tête de nouvelle session
            with open(self.transcript_file, 'w', encoding='utf-8') as f:
                f.write(f"=== SESSION STARTED: {self.today} ===\n")

    def _write_to_transcript(self, text: str, prefix: str = ""):
        """Écrit dans le fichier log sans perturber la console."""
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        try:
            with open(self.transcript_file, 'a', encoding='utf-8') as f:
                # Nettoyage basique des codes couleur ANSI si besoin (optionnel pour l'instant)
                f.write(f"{timestamp} {prefix}{text}\n")
        except Exception as e:
            # Fallback silencieux pour ne pas crasher l'app si le log échoue
            sys.stderr.write(f"[LOG ERROR] {e}\n")

    def print(self, message: str):
        """Remplace print() : Affiche à l'écran ET logue dans le transcript."""
        # Affichage écran standard
        print(message)
        # Enregistrement transcript (Sortie Wrapper)
        self._write_to_transcript(message, prefix="[WRAPPER] >> ")

    def input(self, prompt_text: str) -> str:
        """Remplace input() : Affiche le prompt, capture la saisie ET logue tout."""
        # 1. On logue la question du système
        self._write_to_transcript(prompt_text, prefix="[PROMPT]  >> ")
        
        # 2. Interaction réelle
        user_input = input(prompt_text)
        
        # 3. On logue la réponse de l'utilisateur
        self._write_to_transcript(user_input, prefix="[USER]    << ")
        return user_input

    def error(self, message: str):
        """Affiche une erreur en rouge (simulé) et logue."""
        print(f"ERROR: {message}", file=sys.stderr)
        self._write_to_transcript(message, prefix="[ERROR]   !! ")

# Instance globale
GLOBAL_CONSOLE = ConsoleManager()
