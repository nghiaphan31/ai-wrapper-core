import json
import os
from pathlib import Path


class ConfigLoader:
    def __init__(self, project_root: str = None):
        # Détection automatique de la racine si non fournie
        # On suppose que ce script est dans src/config.py, donc racine = ../
        if project_root is None:
            self.project_root = Path(__file__).parent.parent.resolve()
        else:
            self.project_root = Path(project_root).resolve()

        self.project_file = self.project_root / "project.json"
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """Charge le fichier project.json strict."""
        if not self.project_file.exists():
            raise FileNotFoundError(f"CRITICAL: project.json not found at {self.project_file}")

        try:
            with open(self.project_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"CRITICAL: project.json is invalid JSON: {e}")

    def get_project_name(self):
        return self.config.get("project_name", "Unknown Project")

    def get_slug(self):
        return self.config.get("slug", "unknown-slug")

    def get_version(self) -> str:
        """Retourne la version du projet depuis project.json.

        Convention attendue : champ racine `version` (ex: "0.1.0").
        Fallback : "0.0.0" si absent.
        """
        return str(self.config.get("version", "0.0.0"))


# Instance globale simple pour usage rapide
try:
    GLOBAL_CONFIG = ConfigLoader()
except Exception as e:
    print(f"Boot Error: {e}")
    GLOBAL_CONFIG = None
