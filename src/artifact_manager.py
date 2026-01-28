import json
import re
import os
from pathlib import Path
from src.config import GLOBAL_CONFIG
from src.audit import GLOBAL_LEDGER
from src.console import GLOBAL_CONSOLE

class ArtifactManager:
    def __init__(self):
        self.project_root = GLOBAL_CONFIG.project_root
        self.artifacts_dir = self.project_root / "artifacts"

    def _clean_json_response(self, text: str) -> str:
        """Nettoie les balises Markdown code block si l'IA en ajoute."""
        text = text.strip()
        # Enlève ```json au début et ``` à la fin
        if text.startswith("```"):
            text = re.sub(r"^```(json)?", "", text) 
            text = re.sub(r"```$", "", text)
        return text.strip()

    def process_response(self, session_id: str, step_name: str, raw_text: str):
        """
        Transforme le texte brut de l'IA en fichiers physiques.
        Retourne la liste des chemins créés.
        """
        clean_text = self._clean_json_response(raw_text)
        
        try:
            data = json.loads(clean_text)
        except json.JSONDecodeError as e:
            GLOBAL_CONSOLE.error(f"Failed to parse AI JSON: {e}")
            # On pourrait sauvegarder le texte brut pour debug ici
            return []

        # Extraction des artefacts
        artifacts_list = data.get("artifacts", [])
        if not artifacts_list:
            GLOBAL_CONSOLE.print("No artifacts found in AI response.")
            return []

        # Préparation du dossier pour ce step (ex: artifacts/session_date/step_name)
        # Pour simplifier on met tout dans artifacts/<step_name> pour l'instant
        target_dir = self.artifacts_dir / step_name
        target_dir.mkdir(parents=True, exist_ok=True)

        created_files = []

        for item in artifacts_list:
            filepath = item.get("path")
            content = item.get("content")
            operation = item.get("operation", "create") # create, edit...

            if not filepath or content is None:
                continue

            # Sécurité : On écrit DANS artifacts/step_... pas ailleurs
            # On simule la structure du projet à l'intérieur du dossier artifact
            full_path = target_dir / filepath
            
            # Création des dossiers parents si nécessaire
            full_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                GLOBAL_CONSOLE.print(f"Artifact created: {filepath}")
                created_files.append(str(full_path))
                
                # Log Ledger (File Write)
                GLOBAL_LEDGER.log_event(
                    actor="wrapper", 
                    action_type="file_write", 
                    artifacts=[str(full_path)]
                )

            except Exception as e:
                GLOBAL_CONSOLE.error(f"Error writing artifact {filepath}: {e}")

        return created_files

# Instance globale
GLOBAL_ARTIFACTS = ArtifactManager()
