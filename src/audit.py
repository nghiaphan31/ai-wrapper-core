import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from src.config import GLOBAL_CONFIG


class AuditLedger:
    def __init__(self):
        self.project_root = GLOBAL_CONFIG.project_root

        # Existing event ledger (spec Section 10.2)
        self.ledger_file = self.project_root / "ledger" / "events.jsonl"

        # New audit ledger for transactions & cost traceability (project root)
        self.audit_log_file = self.project_root / "audit_log.jsonl"

        self._ensure_ledger_exists()
        self._ensure_audit_log_exists()

    def _ensure_ledger_exists(self):
        if not self.ledger_file.parent.exists():
            self.ledger_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.ledger_file.exists():
            self.ledger_file.touch()

    def _ensure_audit_log_exists(self):
        if not self.audit_log_file.exists():
            self.audit_log_file.touch()

    def log_event(self, actor: str, action_type: str, payload_ref: str = None, artifacts: list = None):
        """Enregistre un événement immuable conformément à la Section 10.2 de la spec."""
        event = {
            "event_uuid": str(uuid.uuid4()),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "actor": actor,  # "user", "wrapper", "ai_model"
            "action_type": action_type,  # "api_request", "file_write", etc.
            "payload_ref": payload_ref,  # Lien vers raw_exchanges (optionnel)
            "artifacts_links": artifacts or [],
        }

        # Écriture Append-Only (Mode 'a')
        with open(self.ledger_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

        return event["event_uuid"]

    def log_transaction(
        self,
        session_id: str,
        user_instruction: str,
        step_id: str,
        usage_stats: dict,
        status: str,
    ) -> str:
        """Append a transaction record to audit_log.jsonl.

        This is a higher-level audit record focused on traceability of operations and costs.

        Each entry is a valid JSON line and includes an ISO8601 UTC timestamp.
        """
        entry_uuid = str(uuid.uuid4())
        entry = {
            "transaction_uuid": entry_uuid,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "step_id": step_id,
            "user_instruction": user_instruction,
            "usage_stats": {
                "prompt_tokens": int((usage_stats or {}).get("prompt_tokens", 0) or 0),
                "completion_tokens": int((usage_stats or {}).get("completion_tokens", 0) or 0),
                "total_tokens": int((usage_stats or {}).get("total_tokens", 0) or 0),
            },
            "status": status,
        }

        with open(self.audit_log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        return entry_uuid


# Instance globale
GLOBAL_LEDGER = AuditLedger()
