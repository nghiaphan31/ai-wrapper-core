import json
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from src.config import GLOBAL_CONFIG
from src.audit import GLOBAL_LEDGER
from src.console import GLOBAL_CONSOLE


class ArtifactManager:
    def __init__(self):
        self.project_root = GLOBAL_CONFIG.project_root
        self.artifacts_dir = self.project_root / "artifacts"

        # REQ_DATA_030: Track artifacts written during the current wrapper execution.
        self._session_artifacts: list[str] = []

    def _parse_ndjson(self, text: str) -> list[dict]:
        """
        NOUVEAU: Parseur robuste pour gérer les flux JSON multiples (NDJSON).
        Gère le cas où l'IA envoie plusieurs blocs JSON à la suite.
        """
        results = []
        decoder = json.JSONDecoder()
        pos = 0
        length = len(text)

        while pos < length:
            # Ignorer les espaces blancs
            while pos < length and text[pos].isspace():
                pos += 1
            if pos >= length:
                break
            
            try:
                # Tente de décoder un objet JSON à partir de la position actuelle
                obj, end = decoder.raw_decode(text, pos)
                results.append(obj)
                pos = end
            except json.JSONDecodeError:
                # Si échec (ex: texte brut ou préambule), on avance d'un caractère
                pos += 1
        
        return results

    def calculate_sha256(self, file_path: str | Path) -> str:
        """(CONSERVÉ) Calculate SHA-256 digest for a file."""
        p = Path(file_path)
        h = hashlib.sha256()
        try:
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            return h.hexdigest()
        except FileNotFoundError:
            return ""

    def generate_session_manifest(self, session_id: str) -> Path:
        """(CONSERVÉ) Generates a JSON manifest listing all artifacts created."""
        manifest_dir = self.project_root / "manifests"
        manifest_dir.mkdir(exist_ok=True)
        
        manifest_path = manifest_dir / f"session_{session_id}_manifest.json"
        
        entries = []
        for rel_path in self._session_artifacts:
            full_path = self.project_root / rel_path
            entries.append({
                "path": rel_path,
                "sha256": self.calculate_sha256(full_path),
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            })

        data = {
            "session_id": session_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "artifacts_count": len(entries),
            "artifacts": entries
        }
        
        manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return manifest_path

    def process_response(self, session_id: str, step_name: str, raw_text: str) -> list[str]:
        """
        (MODIFIÉ) Parse la réponse IA (support NDJSON), affiche TOUTES les pensées/messages,
        sauvegarde la trace brute, et extrait les 'artifacts'.
        Retourne la liste des fichiers générés.
        """
        step_dir = self.artifacts_dir / step_name
        step_dir.mkdir(parents=True, exist_ok=True)
        generated_files = []

        # 1. Sauvegarde de la Trace Brute
        trace_path = step_dir / "raw_response_trace.jsonl"
        try:
            trace_path.write_text(raw_text, encoding="utf-8")
        except Exception as e:
            GLOBAL_CONSOLE.error(f"Failed to save raw trace: {e}")

        # 2. Parsing NDJSON
        json_objects = self._parse_ndjson(raw_text)
        
        if not json_objects:
            GLOBAL_CONSOLE.error("⚠️ No valid JSON block found in AI response.")
            return []

        # 3. Traitement du flux
        for obj in json_objects:
            
            # Affichage Pensées
            if "thought_process" in obj:
                GLOBAL_CONSOLE.print(f"🧠 [Thought]: {obj['thought_process']}")

            # Affichage Outils
            if "tool" in obj:
                args = obj.get('args', {})
                GLOBAL_CONSOLE.print(f"🔧 [Tool Call]: {obj['tool']} {args}")

            # Affichage Message Final
            if "message" in obj:
                GLOBAL_CONSOLE.print(f"\n🤖 [Message]: {obj['message']}\n")

            # Traitement Artifacts
            if "artifacts" in obj:
                for artifact in obj["artifacts"]:
                    path_str = artifact.get("path")
                    content = artifact.get("content")
                    operation = artifact.get("operation", "create")

                    if not path_str or content is None:
                        continue

                    # Écriture dans le dossier STEP (Quarantaine)
                    safe_path = step_dir / Path(path_str).name
                    
                    try:
                        safe_path.write_text(content, encoding="utf-8")
                        
                        # Meta-data sidecar
                        meta = {
                            "original_path": path_str,
                            "operation": operation,
                            "local_path": str(safe_path)
                        }
                        safe_path.with_suffix(safe_path.suffix + ".meta.json").write_text(
                            json.dumps(meta, indent=2), encoding="utf-8"
                        )

                        generated_files.append(str(safe_path))
                        
                        # Logging Audit (SANS l'argument 'details')
                        GLOBAL_LEDGER.log_event(
                            actor="ai", 
                            action_type="artifact_generated", 
                            artifacts=[str(safe_path)]
                        )
                        
                        # Tracking
                        try:
                            rel = str(safe_path.relative_to(self.project_root))
                            self._session_artifacts.append(rel)
                        except ValueError:
                            self._session_artifacts.append(str(safe_path))
                        
                    except Exception as e:
                        GLOBAL_CONSOLE.error(f"Failed to write artifact {path_str}: {e}")

        return generated_files

    def get_session_artifacts(self) -> list[str]:
        return self._session_artifacts


GLOBAL_ARTIFACTS = ArtifactManager()
