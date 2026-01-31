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

        # New audit ledger for transactions & cost traceability
        self.audit_log_file = self.project_root / "ledger" / "audit_log.jsonl"

        self._ensure_ledger_exists()
        self._ensure_audit_log_exists()

    def _ensure_ledger_exists(self):
        if not self.ledger_file.parent.exists():
            self.ledger_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.ledger_file.exists():
            self.ledger_file.touch()

    def _ensure_audit_log_exists(self):
        # Keep behavior: ensure file exists for append-only usage.
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

    def generate_report(self, timeframe: str = "all") -> dict:
        """Generate an aggregated financial & operational report from audit_log.jsonl.

        Timeframes:
          - 'session': current session (YYYY-MM-DD) entries
          - 'today'  : same as session (today's date) for now
          - 'all'    : all entries

        Aggregates:
          - total_requests (transactions)
          - total_input_tokens  (sum of prompt_tokens)
          - total_output_tokens (sum of completion_tokens)
          - estimated_cost_usd (computed from GLOBAL_CONFIG.PRICING_RATES)

        Must handle missing/empty ledger files gracefully (returns zeros).
        """
        tf = (timeframe or "all").strip().lower()
        if tf not in {"session", "today", "all"}:
            tf = "all"

        # Determine filter date for 'session'/'today'
        today = datetime.now().strftime("%Y-%m-%d")

        totals = {
            "timeframe": tf,
            "total_requests": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "estimated_cost_usd": 0.0,
            "pricing_rates": dict(getattr(GLOBAL_CONFIG, "PRICING_RATES", {}) or {}),
            "ledger_file": str(self.audit_log_file),
        }

        # If file missing, return zeros
        try:
            if not self.audit_log_file.exists():
                return totals
        except Exception:
            return totals

        # Read JSONL lines
        try:
            with open(self.audit_log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            return totals

        if not lines:
            return totals

        input_rate = float(totals["pricing_rates"].get("input_per_1m", 0.0) or 0.0)
        output_rate = float(totals["pricing_rates"].get("output_per_1m", 0.0) or 0.0)

        for line in lines:
            line = (line or "").strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                # Skip malformed lines rather than crashing reporting
                continue

            # Timeframe filter
            if tf in {"session", "today"}:
                session_id = str(entry.get("session_id", "") or "")
                if session_id != today:
                    continue

            usage = entry.get("usage_stats") or {}
            pt = int(usage.get("prompt_tokens", 0) or 0)
            ct = int(usage.get("completion_tokens", 0) or 0)

            totals["total_requests"] += 1
            totals["total_input_tokens"] += pt
            totals["total_output_tokens"] += ct

        # Cost computation
        in_cost = (totals["total_input_tokens"] / 1_000_000.0) * input_rate
        out_cost = (totals["total_output_tokens"] / 1_000_000.0) * output_rate
        totals["estimated_cost_usd"] = float(in_cost + out_cost)

        return totals


# Instance globale
GLOBAL_LEDGER = AuditLedger()
