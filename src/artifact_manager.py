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
        self._session_artifacts: list[str] = []

    def _parse_ndjson(self, text: str) -> list[dict]:
        """Parseur robuste NDJSON."""
        results = []
        decoder = json.JSONDecoder()
        pos = 0
        length = len(text)

        while pos < length:
            while pos < length and text[pos].isspace():
                pos += 1
            if pos >= length:
                break
            try:
                obj, end = decoder.raw_decode(text, pos)
                results.append(obj)
                pos = end
            except json.JSONDecodeError:
                pos += 1
        return results

    def calculate_sha256(self, file_path: str | Path) -> str:
        """(CONSERVÉ) Calculate SHA-256 digest."""
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
        """(CONSERVÉ) Generates a JSON manifest."""
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

    def process_response(
        self, 
        session_id: str, 
        step_name: str, 
        raw_text: str, 
        enable_rebound: bool = False
    ) -> list[str] | tuple[list[str], dict | None]:
        """
        Parse la réponse IA, affiche la réflexion, et écrit les fichiers 
        EN RESPECTANT L'ARBORESCENCE (ex: artifacts/step_X/specs/doc.md).
        
        Args:
            enable_rebound (bool): Si True, retourne (files, next_action). 
                                   Si False (défaut), retourne files (compatibilité).
        """
        step_dir = self.artifacts_dir / step_name
        step_dir.mkdir(parents=True, exist_ok=True)
        generated_files = []
        next_action = None

        # 1. Sauvegarde Trace
        trace_path = step_dir / "raw_response_trace.jsonl"
        try:
            trace_path.write_text(raw_text, encoding="utf-8")
        except Exception as e:
            GLOBAL_CONSOLE.error(f"Failed to save raw trace: {e}")

        # 2. Parsing NDJSON
        json_objects = self._parse_ndjson(raw_text)
        
        if not json_objects:
            GLOBAL_CONSOLE.error("⚠️ No valid JSON block found in AI response.")
            return ([], None) if enable_rebound else []

        # 3. Traitement
        for obj in json_objects:
            if "thought_process" in obj:
                GLOBAL_CONSOLE.print(f"🧠 [Thought]: {obj['thought_process']}")
            if "tool" in obj:
                args = obj.get('args', {})
                GLOBAL_CONSOLE.print(f"🔧 [Tool Call]: {obj['tool']} {args}")
            if "message" in obj:
                GLOBAL_CONSOLE.print(f"\n🤖 [Message]: {obj['message']}\n")

            # --- NOUVEAU : Extraction Next Action (Rebound Protocol) ---
            if "next_action" in obj:
                cand = obj["next_action"]
                is_valid = True
                
                # Check Type
                if cand.get("type") != "exec_and_chain":
                    GLOBAL_CONSOLE.error(f"⚠️ Invalid next_action type: {cand.get('type')}")
                    is_valid = False
                
                # Check Target (Security)
                target = cand.get("target_script", "")
                if not target.startswith("workbench/scripts/"):
                    GLOBAL_CONSOLE.error(f"⛔ Security: next_action target must be in workbench/scripts/ (Got: {target})")
                    is_valid = False
                
                # Check Prompt
                if not cand.get("continuation_prompt"):
                    GLOBAL_CONSOLE.error("⚠️ Invalid next_action: missing continuation_prompt")
                    is_valid = False
                
                if is_valid:
                    next_action = cand
                    GLOBAL_CONSOLE.print(f"⚡ [Next Action]: {target}")

            # --- Traitement des Artifacts (Logic existante préservée) ---
            if "artifacts" in obj:
                for artifact in obj["artifacts"]:
                    path_str = artifact.get("path") # ex: "specs/10_auto.md"
                    content = artifact.get("content")
                    operation = artifact.get("operation", "create")

                    if not path_str or content is None:
                        continue

                    # --- CORRECTION PATH MANAGEMENT (CONSERVÉ) ---
                    # 1. On combine le dossier step avec le chemin demandé
                    # 2. On utilise .resolve() pour gérer les ../ éventuels
                    try:
                        safe_target = (step_dir / path_str).resolve()
                        step_dir_abs = step_dir.resolve()

                        # Sécurité : Vérifier que le fichier reste dans step_dir
                        if not str(safe_target).startswith(str(step_dir_abs)):
                            GLOBAL_CONSOLE.error(f"⛔ Security Alert: Path escape attempt blocked: {path_str}")
                            continue
                        
                        # Création des sous-dossiers (ex: artifacts/step_X/specs/)
                        safe_target.parent.mkdir(parents=True, exist_ok=True)

                        # Écriture
                        safe_target.write_text(content, encoding="utf-8")
                        
                        # Meta-data sidecar
                        meta = {
                            "original_path": path_str,
                            "operation": operation,
                            "local_path": str(safe_target)
                        }
                        safe_target.with_suffix(safe_target.suffix + ".meta.json").write_text(
                            json.dumps(meta, indent=2), encoding="utf-8"
                        )

                        generated_files.append(str(safe_target))
                        
                        GLOBAL_LEDGER.log_event(
                            actor="ai", 
                            action_type="artifact_generated", 
                            artifacts=[str(safe_target)]
                        )
                        
                        # Tracking
                        try:
                            rel = str(safe_target.relative_to(self.project_root))
                            self._session_artifacts.append(rel)
                        except ValueError:
                            self._session_artifacts.append(str(safe_target))
                            
                    except Exception as e:
                        GLOBAL_CONSOLE.error(f"Failed to write artifact {path_str}: {e}")

        # Retour conditionnel pour compatibilité
        if enable_rebound:
            return generated_files, next_action
        
        return generated_files

    def get_session_artifacts(self) -> list[str]:
        return self._session_artifacts


GLOBAL_ARTIFACTS = ArtifactManager()
