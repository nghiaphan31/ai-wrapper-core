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
                # pour chercher le prochain début de JSON valide '{'
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

        # 1. Sauvegarde de la Trace Brute (Requirement #2)
        # Indispensable pour debugger si l'IA envoie un format bizarre
        trace_path = step_dir / "raw_response_trace.jsonl"
        try:
            trace_path.write_text(raw_text, encoding="utf-8")
        except Exception as e:
            GLOBAL_CONSOLE.error(f"Failed to save raw trace: {e}")

        # 2. Parsing NDJSON (Requirement #1)
        # On utilise le nouveau parseur au lieu de json.loads() simple
        json_objects = self._parse_ndjson(raw_text)
        
        if not json_objects:
            # Fallback : si aucun JSON n'est trouvé, c'est peut-être du texte brut.
            # On ne plante pas, mais on ne génère pas de fichiers.
            GLOBAL_CONSOLE.error("⚠️ No valid JSON block found in AI response.")
            # Optionnel : afficher le texte brut si ce n'est pas trop long ?
            # GLOBAL_CONSOLE.print(raw_text[:500] + "...")
            return []

        # 3. Traitement du flux (Requirement #3 & #4)
        # On itère sur chaque objet reçu pour afficher le "film" de la réflexion
        
        for obj in json_objects:
            
            # Affichage des Pensées (Brain)
            if "thought_process" in obj:
                GLOBAL_CONSOLE.print(f"🧠 [Thought]: {obj['thought_process']}")

            # Affichage des Outils (Pour info, même si exécutés ailleurs ou simulés)
            if "tool" in obj:
                args = obj.get('args', {})
                GLOBAL_CONSOLE.print(f"🔧 [Tool Call]: {obj['tool']} {args}")

            # Affichage du Message Final (Communication)
            if "message" in obj:
                GLOBAL_CONSOLE.print(f"\n🤖 [Message]: {obj['message']}\n")

            # Traitement des Artifacts (Livrables - Requirement #5)
            if "artifacts" in obj:
                for artifact in obj["artifacts"]:
                    path_str = artifact.get("path")
                    content = artifact.get("content")
                    operation = artifact.get("operation", "create")

                    if not path_str or content is None:
                        continue

                    # Sécurisation du chemin (nom de fichier uniquement dans le dossier step)
                    # NOTE: Dans l'architecture Workbench, on pourrait vouloir écrire directement
                    # dans workbench/, mais pour l'instant on reste safe dans artifacts/step_ID/
                    safe_path = step_dir / Path(path_str).name
                    
                    try:
                        # Écriture du fichier
                        safe_path.write_text(content, encoding="utf-8")
                        
                        # Création du fichier métadonnées (.meta.json) pour le Reviewer
                        meta = {
                            "original_path": path_str,
                            "operation": operation,
                            "local_path": str(safe_path)
                        }
                        safe_path.with_suffix(safe_path.suffix + ".meta.json").write_text(
                            json.dumps(meta, indent=2), encoding="utf-8"
                        )

                        generated_files.append(str(safe_path))
                        
                        # Logging Audit
                        GLOBAL_LEDGER.log_event(
                            actor="ai", 
                            action_type="artifact_generated", 
                            artifacts=[str(safe_path)],
                        )
                        
                        # Tracking session (chemin relatif depuis root pour le manifest)
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


# Instance globale
GLOBAL_ARTIFACTS = ArtifactManager()
