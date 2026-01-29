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
        # Store project-root relative paths (strings) to make manifests portable.
        self._session_artifacts: list[str] = []

    def _clean_json_response(self, text: str) -> str:
        """Nettoie les balises Markdown code block si l'IA en ajoute."""
        text = text.strip()
        # Enlève ```json au début et ``` à la fin
        if text.startswith("```"):
            text = re.sub(r"^```(json)?", "", text)
            text = re.sub(r"```$", "", text)
        return text.strip()

    def calculate_sha256(self, file_path: str | Path) -> str:
        """Calculate SHA-256 digest for a file (hex string)."""
        p = Path(file_path)
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def generate_session_manifest(self, session_id: str) -> str | None:
        """Generate a session integrity manifest for artifacts created in this session.

        Output path (project-root relative):
          manifests/session_<session_id>_manifest.json

        JSON structure:
        {
          "session_id": "...",
          "timestamp": "...",
          "artifacts": [
            {"path": "artifacts/step_X/file.py", "sha256": "..."}
          ]
        }

        Safety:
          - Handles empty artifact list (writes artifacts=[]).
          - Skips entries whose files no longer exist.
          - Handles permission errors gracefully.

        Behavior:
          - Clears internal tracking list after writing to avoid duplication.

        Returns:
          - Manifest path as project-root relative string, or None if manifest could not be written.
        """
        session_id = str(session_id or "").strip() or "unknown"

        manifests_dir = self.project_root / "manifests"
        try:
            manifests_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            GLOBAL_CONSOLE.error(f"Permission error creating manifests directory: {e}")
            return None
        except Exception as e:
            GLOBAL_CONSOLE.error(f"Failed to create manifests directory: {e}")
            return None

        manifest_filename = f"session_{session_id}_manifest.json"
        manifest_path = manifests_dir / manifest_filename

        artifacts_out: list[dict] = []

        # de-dup while preserving order
        seen: set[str] = set()
        for rel_path in list(self._session_artifacts):
            if not rel_path:
                continue
            if rel_path in seen:
                continue
            seen.add(rel_path)

            p = (self.project_root / rel_path).resolve()
            if not p.exists() or not p.is_file():
                continue

            try:
                sha = self.calculate_sha256(p)
            except PermissionError as e:
                GLOBAL_CONSOLE.error(f"Permission error hashing file for manifest {p}: {e}")
                continue
            except Exception as e:
                GLOBAL_CONSOLE.error(f"Manifest hashing failed for {p}: {e}")
                continue

            artifacts_out.append({"path": rel_path, "sha256": sha})

        manifest = {
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "artifacts": artifacts_out,
        }

        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
        except PermissionError as e:
            GLOBAL_CONSOLE.error(f"Permission error writing manifest {manifest_path}: {e}")
            return None
        except Exception as e:
            GLOBAL_CONSOLE.error(f"Failed to write manifest {manifest_path}: {e}")
            return None
        finally:
            # Clear after attempt to avoid duplication if called multiple times.
            # (Even if write failed, keeping the list can cause repeated failures/spam.)
            self._session_artifacts = []

        try:
            return str(manifest_path.relative_to(self.project_root))
        except Exception:
            return str(manifest_path)

    def process_response(self, session_id: str, step_name: str, raw_text: str):
        """Transforme le texte brut de l'IA en fichiers physiques.
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
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            GLOBAL_CONSOLE.error(f"Permission error creating artifact directory {target_dir}: {e}")
            return []
        except Exception as e:
            GLOBAL_CONSOLE.error(f"Failed to create artifact directory {target_dir}: {e}")
            return []

        created_files = []

        for item in artifacts_list:
            filepath = item.get("path")
            content = item.get("content")
            operation = item.get("operation", "create")  # create, edit...

            if not filepath or content is None:
                continue

            # Sécurité : On écrit DANS artifacts/step_... pas ailleurs
            # On simule la structure du projet à l'intérieur du dossier artifact
            full_path = (target_dir / filepath).resolve()

            # Basic safety: ensure we are still under target_dir
            try:
                full_path.relative_to(target_dir.resolve())
            except Exception:
                GLOBAL_CONSOLE.error(f"Blocked unsafe artifact path outside target dir: {filepath}")
                continue

            # Création des dossiers parents si nécessaire
            try:
                full_path.parent.mkdir(parents=True, exist_ok=True)
            except PermissionError as e:
                GLOBAL_CONSOLE.error(f"Permission error creating parent directories for {full_path}: {e}")
                continue
            except Exception as e:
                GLOBAL_CONSOLE.error(f"Failed to create parent directories for {full_path}: {e}")
                continue

            try:
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)

                GLOBAL_CONSOLE.print(f"Artifact created: {filepath}")
                created_files.append(str(full_path))

                # Track for session manifest (REQ_DATA_030) as project-root relative path
                try:
                    rel = str(full_path.relative_to(self.project_root))
                    self._session_artifacts.append(rel)
                except Exception:
                    # Fallback: store absolute path if relative conversion fails
                    self._session_artifacts.append(str(full_path))

                # Log Ledger (File Write)
                GLOBAL_LEDGER.log_event(
                    actor="wrapper",
                    action_type="file_write",
                    artifacts=[str(full_path)],
                )

            except PermissionError as e:
                GLOBAL_CONSOLE.error(f"Permission error writing artifact {filepath}: {e}")
            except Exception as e:
                GLOBAL_CONSOLE.error(f"Error writing artifact {filepath}: {e}")

        return created_files


# Instance globale
GLOBAL_ARTIFACTS = ArtifactManager()
