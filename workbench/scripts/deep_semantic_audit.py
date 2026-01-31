from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REQ_ID_RE = re.compile(r"\bREQ_[A-Z0-9]+_[0-9]{3}\b")


@dataclass(frozen=True)
class Requirement:
    req_id: str
    title: str
    source_file: str


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _load_repo_analysis(project_root: Path) -> dict[str, Any]:
    """Load code structure mapping.

    Prefers outputs from prior runs if present; otherwise re-runs the extractor.

    Expected output schema is whatever workbench/scripts/code_logic_extractor.py prints.
    """
    # Common places where users may have saved the extractor output.
    candidates = [
        project_root / "outputs" / "code_logic_extractor.json",
        project_root / "outputs" / "code_logic_extractor_output.json",
        project_root / "outputs" / "repo_analysis.json",
        project_root / "workbench" / "data" / "code_logic_extractor.json",
        project_root / "workbench" / "data" / "repo_analysis.json",
    ]

    for c in candidates:
        if c.exists() and c.is_file():
            txt = _read_text(c).strip()
            if txt:
                try:
                    return json.loads(txt)
                except Exception:
                    pass

    # Fallback: run extractor in-process (no subprocess to keep this script simple/portable).
    # Importing is safe: it's a local workbench script.
    try:
        import importlib.util

        extractor_path = project_root / "workbench" / "scripts" / "code_logic_extractor.py"
        spec = importlib.util.spec_from_file_location("code_logic_extractor", extractor_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Failed to load extractor module")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
        data = mod.analyze_repo(project_root)  # type: ignore[attr-defined]
        return data
    except Exception as e:
        raise RuntimeError(f"Unable to load or generate repo analysis: {e}")


def _extract_requirements_from_md_table(md_text: str, source_file: str) -> list[Requirement]:
    """Best-effort parse of requirement registry tables.

    We intentionally do not hardcode a specific table format; instead:
      - find all REQ_* tokens
      - attempt to infer a nearby title from the same line (pipe table) or heading.

    This is conservative and may produce generic titles when the table cannot be parsed.
    """
    reqs: list[Requirement] = []
    seen: set[str] = set()

    lines = md_text.splitlines()
    for ln in lines:
        ids = REQ_ID_RE.findall(ln)
        if not ids:
            continue

        # Try to infer title from pipe table row: | REQ_X | Title | ...
        title_guess = ""
        if "|" in ln:
            parts = [p.strip() for p in ln.strip().strip("|").split("|")]
            # Find first REQ cell and take next cell as title if present
            for i, p in enumerate(parts):
                if REQ_ID_RE.fullmatch(p):
                    if i + 1 < len(parts):
                        title_guess = parts[i + 1]
                    break

        for rid in ids:
            if rid in seen:
                continue
            seen.add(rid)
            reqs.append(
                Requirement(
                    req_id=rid,
                    title=title_guess or "(title not parsed)",
                    source_file=source_file,
                )
            )

    return reqs


def _load_requirements(project_root: Path) -> dict[str, Requirement]:
    """Load requirements from the specified spec files.

    Required by user request:
      - specs/01_architecture_baseline.md (Req registry table)
      - specs/10_autonomous_rebound_protocol.md

    Returns mapping req_id -> Requirement.
    """
    req_map: dict[str, Requirement] = {}

    spec_files = [
        project_root / "specs" / "01_architecture_baseline.md",
        project_root / "specs" / "10_autonomous_rebound_protocol.md",
    ]

    for p in spec_files:
        txt = _read_text(p)
        if not txt.strip():
            continue
        for r in _extract_requirements_from_md_table(txt, str(p.relative_to(project_root))):
            # Keep first title/source if duplicated
            req_map.setdefault(r.req_id, r)

    return req_map


def _load_traceability_matrix(project_root: Path) -> str:
    p = project_root / "traceability_matrix.md"
    return _read_text(p)


def _matrix_req_ids(matrix_text: str) -> set[str]:
    return set(REQ_ID_RE.findall(matrix_text or ""))


def _iter_functions(repo_analysis: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Yield flattened function/method records from extractor output."""
    for f in repo_analysis.get("files", []) or []:
        file_path = f.get("path")
        defs = (f.get("definitions") or {})
        for fn in defs.get("functions", []) or []:
            yield {
                "file": file_path,
                "kind": "function",
                **fn,
            }
        for cls in defs.get("classes", []) or []:
            for m in cls.get("methods", []) or []:
                yield {
                    "file": file_path,
                    "kind": "method",
                    "class": cls.get("name"),
                    **m,
                }


def _logic_text(fn: dict[str, Any]) -> str:
    """Build a compact text blob from logic summaries for heuristic matching."""
    logic = fn.get("logic") or {}
    constructs = logic.get("constructs") or {}
    top_calls = logic.get("top_calls") or []
    string_hints = logic.get("string_hints") or []

    calls_join = " ".join([str(c.get("name")) for c in top_calls if c.get("name")])
    hints_join = " ".join([str(s) for s in string_hints if s])
    constructs_join = " ".join([k for k, v in constructs.items() if v])

    parts = [
        str(fn.get("name") or ""),
        str(fn.get("qualname") or ""),
        constructs_join,
        calls_join,
        hints_join,
        str(fn.get("docstring") or ""),
    ]
    return "\n".join([p for p in parts if p]).lower()


def _score_req_to_function(req_id: str, req: Requirement, fn: dict[str, Any]) -> float:
    """Heuristic semantic scoring based on logic (not REQ comments).

    IMPORTANT: We do not use explicit REQ_* mentions in code as evidence.

    This is a best-effort mapping:
      - match on key domain terms inferred from requirement id family
      - match on known anchor terms for this repo (workbench/scripts, trinity, audit, etc.)

    Output is a score in [0, 1].
    """
    txt = _logic_text(fn)

    # Family inference from req_id prefix.
    family = ""
    if req_id.startswith("REQ_CORE_"):
        family = "core"
    elif req_id.startswith("REQ_AUDIT_"):
        family = "audit"
    elif req_id.startswith("REQ_AUTO_"):
        family = "auto"
    elif req_id.startswith("REQ_ARCH_"):
        family = "arch"

    score = 0.0

    # Generic anchors by family
    anchors: list[str] = []
    if family == "core":
        anchors = ["safe", "sandbox", "allowlist", "git", "context", "token", "pricing"]
    elif family == "audit":
        anchors = ["ledger", "audit", "log_event", "log_transaction", "manifest", "transcript", "raw_exchanges"]
    elif family == "auto":
        anchors = ["next_action", "rebound", "loop", "workbench/scripts", "runner", "validate"]
    elif family == "arch":
        anchors = ["workbench", "src/scripts", "structure", "layout", "project_root"]

    hit = 0
    for a in anchors:
        if a in txt:
            hit += 1
    if anchors:
        score += min(0.6, 0.6 * (hit / max(1, len(anchors))))

    # Strong signals
    strong = [
        ("workbench/scripts" in txt and family in ("auto", "core", "arch"), 0.25),
        ("log_transaction" in txt and family == "audit", 0.25),
        ("log_event" in txt and family == "audit", 0.2),
        ("generate_report" in txt and family == "audit", 0.2),
        ("_trinity_protocol_consistency_check" in txt and family in ("core", "audit"), 0.2),
    ]
    for cond, w in strong:
        if cond:
            score += w

    return max(0.0, min(1.0, score))


def _map_requirements_to_functions(
    reqs: dict[str, Requirement], repo_analysis: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    """Return mapping req_id -> list of candidate function records with scores."""
    fns = list(_iter_functions(repo_analysis))

    out: dict[str, list[dict[str, Any]]] = {}
    for rid, req in sorted(reqs.items(), key=lambda x: x[0]):
        scored: list[dict[str, Any]] = []
        for fn in fns:
            s = _score_req_to_function(rid, req, fn)
            if s <= 0:
                continue
            scored.append(
                {
                    "score": round(float(s), 3),
                    "file": fn.get("file"),
                    "name": fn.get("name"),
                    "qualname": fn.get("qualname"),
                    "kind": fn.get("kind"),
                    "class": fn.get("class"),
                    "docstring": fn.get("docstring"),
                }
            )
        scored.sort(key=lambda x: x["score"], reverse=True)
        out[rid] = scored[:5]

    return out


def _completeness_from_candidates(cands: list[dict[str, Any]]) -> str:
    """Derive completeness label from heuristic scores."""
    if not cands:
        return "Not"
    top = float(cands[0].get("score") or 0.0)
    if top >= 0.75:
        return "Fully"
    if top >= 0.35:
        return "Partial"
    return "Not"


def _render_md_report(
    project_root: Path,
    reqs: dict[str, Requirement],
    mapping: dict[str, list[dict[str, Any]]],
    matrix_missing: set[str],
) -> str:
    lines: list[str] = []
    lines.append("# Deep Semantic Audit")
    lines.append("")
    lines.append("This report maps requirements to code *based on extracted logic signals* (calls, constructs, string hints), not on REQ_* comments.")
    lines.append("")
    lines.append("## Inputs")
    lines.append("")
    lines.append("- specs/01_architecture_baseline.md")
    lines.append("- specs/10_autonomous_rebound_protocol.md")
    lines.append("- src/ (semantic signals via workbench/scripts/code_logic_extractor.py)")
    lines.append("- traceability_matrix.md")
    lines.append("")

    if matrix_missing:
        lines.append("## Traceability Matrix Gaps (MUST FIX)")
        lines.append("")
        lines.append("The following requirements were found in specs but have **no corresponding entry** in traceability_matrix.md:")
        lines.append("")
        for rid in sorted(matrix_missing):
            r = reqs.get(rid)
            src = r.source_file if r else "(unknown)"
            lines.append(f"- {rid} (source: {src})")
        lines.append("")

    lines.append("## Requirement-to-Code Semantic Mapping")
    lines.append("")
    lines.append("Legend for completeness: **Fully** (strong match), **Partial** (some evidence), **Not** (no credible match).")
    lines.append("")
    lines.append("| Req_ID | Title (best-effort) | Spec Source | Completeness | Top Candidates (score → symbol) |")
    lines.append("|---|---|---|---|---|")

    for rid in sorted(reqs.keys()):
        r = reqs[rid]
        cands = mapping.get(rid, [])
        comp = _completeness_from_candidates(cands)
        cand_txt = "<br/>".join(
            [
                f"{c.get('score')} → `{c.get('file')}:{c.get('qualname') or c.get('name')}`"
                for c in cands
            ]
        )
        if not cand_txt:
            cand_txt = "(none)"
        title = r.title.replace("|", "\\|") if r.title else ""
        lines.append(f"| {rid} | {title} | {r.source_file} | {comp} | {cand_txt} |")

    lines.append("")
    lines.append("## Recommendations")
    lines.append("")
    lines.append("1. For each **Partial** requirement, confirm intended implementing function(s) and add explicit traceability links in traceability_matrix.md.")
    lines.append("2. For each **Not** requirement, decide whether to implement or to amend specs (de-scope / mark N/A) and update the matrix accordingly.")
    lines.append("3. If the spec registry table format changes, update this audit script parser to extract accurate titles.")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    project_root = Path(os.getcwd()).resolve()

    repo_analysis = _load_repo_analysis(project_root)
    reqs = _load_requirements(project_root)

    matrix_text = _load_traceability_matrix(project_root)
    matrix_ids = _matrix_req_ids(matrix_text)

    # Requirements in specs that are missing in the matrix
    matrix_missing = set(reqs.keys()) - set(matrix_ids)

    mapping = _map_requirements_to_functions(reqs, repo_analysis)

    report_text = _render_md_report(project_root, reqs, mapping, matrix_missing)

    out_dir = project_root / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "deep_semantic_audit.md"
    out_path.write_text(report_text, encoding="utf-8")

    # Also emit a machine-readable JSON for downstream updates.
    json_path = out_dir / "deep_semantic_audit.json"
    json_payload = {
        "project_root": str(project_root),
        "requirements_count": len(reqs),
        "requirements": {rid: r.__dict__ for rid, r in reqs.items()},
        "matrix_req_ids_count": len(matrix_ids),
        "matrix_missing_req_ids": sorted(matrix_missing),
        "mapping_top5": mapping,
        "completeness": {rid: _completeness_from_candidates(mapping.get(rid, [])) for rid in reqs.keys()},
    }
    json_path.write_text(json.dumps(json_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "report": str(out_path.relative_to(project_root)),
                "report_json": str(json_path.relative_to(project_root)),
                "requirements_count": len(reqs),
                "matrix_missing_req_ids": sorted(matrix_missing),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
