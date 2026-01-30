import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from openai import OpenAI
from src.config import GLOBAL_CONFIG
from src.audit import GLOBAL_LEDGER
from src.console import GLOBAL_CONSOLE


class AIClient:
    def __init__(self):
        self.project_root = GLOBAL_CONFIG.project_root
        self.api_key = self._load_api_key()

        # Récupération du modèle défini dans la policy du projet
        self.model_name = GLOBAL_CONFIG.config.get("policy", {}).get("model_alias", "gpt-4o")  # Fallback safe

        # Initialisation du client officiel
        self.client = OpenAI(api_key=self.api_key)

    def _load_api_key(self) -> str:
        """Lit la clé API depuis le fichier secret non-versionné."""
        key_file = self.project_root / "secrets" / "openai_key"
        if not key_file.exists():
            raise FileNotFoundError(f"CRITICAL: API Key not found at {key_file}")

        with open(key_file, "r", encoding="utf-8") as f:
            key = f.read().strip()

        if not key.startswith("sk-"):
            raise ValueError("CRITICAL: Invalid API Key format (must start with sk-)")
        return key

    def _extract_usage_stats(self, response) -> dict:
        """Extract token usage stats from the API response.

        Returns a dict with keys: prompt_tokens, completion_tokens, total_tokens.
        Missing fields are defaulted to 0 for robustness.
        """
        usage = getattr(response, "usage", None)

        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        # The OpenAI SDK returns a typed object; be tolerant to dict-like shapes.
        if usage is not None:
            try:
                prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
                total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
            except Exception:
                # Fallback for dict-like usage
                try:
                    prompt_tokens = int((usage.get("prompt_tokens") or 0))
                    completion_tokens = int((usage.get("completion_tokens") or 0))
                    total_tokens = int((usage.get("total_tokens") or 0))
                except Exception:
                    prompt_tokens, completion_tokens, total_tokens = 0, 0, 0

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

    def _log_raw_exchange(self, request_id: str, raw_data: dict) -> tuple[Path, str] | tuple[None, None]:
        """Persist the raw request/response exchange to the date-scoped session path.

        Enforces structure:
          sessions/<YYYY-MM-DD>/raw_exchanges/<uuid>.json

        Returns:
          (raw_path, payload_ref)

        Safety:
          - Ensures the date folder exists.
          - Handles permission errors gracefully (returns (None, None)).
        """
        session_date = datetime.now().strftime("%Y-%m-%d")
        raw_filename = f"{request_id}.json"
        raw_path = self.project_root / "sessions" / session_date / "raw_exchanges" / raw_filename

        # Safety: create directory even if sessions/ is empty / missing
        try:
            raw_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            GLOBAL_CONSOLE.error(f"Permission error creating raw exchange directory {raw_path.parent}: {e}")
            return None, None
        except Exception as e:
            GLOBAL_CONSOLE.error(f"Failed to create raw exchange directory {raw_path.parent}: {e}")
            return None, None

        try:
            with open(raw_path, "w", encoding="utf-8") as f:
                json.dump(raw_data, f, indent=2)
        except PermissionError as e:
            GLOBAL_CONSOLE.error(f"Permission error writing raw exchange {raw_path}: {e}")
            return None, None
        except Exception as e:
            GLOBAL_CONSOLE.error(f"Failed to write raw exchange {raw_path}: {e}")
            return None, None

        payload_ref = f"sessions/{session_date}/raw_exchanges/{raw_filename}"
        return raw_path, payload_ref

    def build_system_prompt(self, base_system_prompt: str) -> str:
        """Build the final system prompt with mandatory governance instructions.

        REQ_CORE_060 (The Trinity Protocol) is enforced here by injecting a mandatory
        instruction block into the system message.

        Note:
          - This does not replace the existing rules; it appends a strict governance layer.
          - The runtime side (src/main.py) also performs a best-effort warning check.
        """
        base = (base_system_prompt or "").rstrip()

        trinity_block = (
            "\n\n"
            "TRINITY PROTOCOL ENABLED: You manage a strict ecosystem of Specs, Code, and Docs.\n"
            "1. NEVER output Code without checking if `impl-docs/` needs an update.\n"
            "2. NEVER implement a feature without checking if `specs/` needs a retrofit.\n"
            "3. If you change one, you must evaluate the others.\n"
            "Failure to align all three layers is a critical error.\n"
        )

        return f"{base}{trinity_block}"

    def send_chat_request(self, system_prompt: str, user_prompt: str) -> tuple[str, dict]:
        """Envoie une requête à l'IA, logue tout (Raw + Ledger), et retourne (content, usage_stats)."""
        request_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        # REQ_CORE_060: ensure the final system prompt includes Trinity Protocol block.
        system_prompt = self.build_system_prompt(system_prompt)

        # 1. Préparation de la payload
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        GLOBAL_CONSOLE.print(f"Connecting to AI ({self.model_name})...")

        try:
            # 2. Appel API réel
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.7,
            )

            # 3. Extraction de la réponse
            content = response.choices[0].message.content

            # 3b. Extraction usage stats (tokens)
            usage_stats = self._extract_usage_stats(response)

            # 4. Sauvegarde des échanges bruts (Raw Exchange)
            raw_data = {
                "request_id": request_id,
                "timestamp": timestamp,
                "model_used": self.model_name,
                "input_messages": messages,
                "usage_stats": usage_stats,
                "raw_response": response.model_dump(),  # Sérialise l'objet réponse complet
            }

            _raw_path, payload_ref = self._log_raw_exchange(request_id=request_id, raw_data=raw_data)

            # 5. Enregistrement dans le Ledger (Référence vers le fichier raw)
            # If raw logging failed, still log the event without payload_ref.
            GLOBAL_LEDGER.log_event(
                actor="ai_model",
                action_type="api_response",
                payload_ref=payload_ref,
                artifacts=[],
            )

            return content, usage_stats

        except Exception as e:
            GLOBAL_CONSOLE.error(f"API Call Failed: {e}")
            raise e


# Instance globale (Lazy loading pourrait être mieux, mais simple pour l'instant)
# On ne l'instancie pas tout de suite pour éviter de crasher si la clé manque au chargement du module
# On l'instanciera à la demande.
