import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from src.config import GLOBAL_CONFIG

class AuditLedger:
    def __init__(self):
        self.project_root = GLOBAL_CONFIG.project_root
        self.ledger_file = self.project_root / "ledger" / "events.jsonl"
        self._ensure_ledger_exists()

    def _ensure_ledger_exists(self):
        if not self.ledger_file.parent.exists():
            self.ledger_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.ledger_file.exists():
            self.ledger_file.touch()

    def log_event(self, actor: str, action_type: str, payload_ref: str = None, artifacts: list = None):
        """
        Enregistre un événement immuable conformément à la Section 10.2 de la spec.
        """
        event = {
            "event_uuid": str(uuid.uuid4()),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "actor": actor,          # "user", "wrapper", "ai_model"
            "action_type": action_type, # "api_request", "file_write", etc.
            "payload_ref": payload_ref, # Lien vers raw_exchanges (optionnel)
            "artifacts_links": artifacts or []
        }

        # Écriture Append-Only (Mode 'a')
        with open(self.ledger_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event) + "\n")
            
        return event["event_uuid"]

# Instance globale
GLOBAL_LEDGER = AuditLedger()
