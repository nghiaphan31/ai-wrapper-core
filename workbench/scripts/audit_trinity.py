import ast
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQ_ID_RE = re.compile(r"REQ_[A-Z]+_\d+")


EXCLUDED_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".idea",
    ".vscode",
}


def _should_skip_path(p: Path) -> bool:
    parts = set(p.parts)
    return any(x in parts for x in EXCLUDED_DIR_NAMES)


def _read_text_best_effort(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


@dataclass
class PySymbols:
    functions: list[str]
    classes: list[str]


def _extract_symbols_from_py(py_path: Path) -> PySymbols:
    text = _read_text_best_effort(py_path)
    if not text.strip():
        return PySymbols(functions=[], classes=[])

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return PySymbols(functions=[], classes=[])

    functions: list[str] = []
    classes: list[str] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)

    return PySymbols(functions=sorted(set(functions)), classes=sorted(set(classes)))


def _list_python_files(src_dir: Path) -> list[Path]:
    if not src_dir.exists():
        return []
    files: list[Path] = []
    for p in src_dir.rglob("*.py"):
        if _should_skip_path(p):
            continue
        files.append(p)
    return sorted(files, key=lambda x: str(x))


def _list_md_files(dir_path: Path) -> list[Path]:
    if not dir_path.exists():
        return []
    files: list[Path] = []
    for p in dir_path.rglob("*.md"):
        if _should_skip_path(p):
            continue
        files.append(p)
    return sorted(files, key=lambda x: str(x))


def _scan_req_ids_in_specs(specs_dir: Path) -> dict[str, list[str]]:
    """Return mapping: req_id -> list of spec files where it appears."""
    out: dict[str, list[str]] = {}
    for md in _list_md_files(specs_dir):
        text = _read_text_best_effort(md)
        for rid in sorted(set(REQ_ID_RE.findall(text))):
            out.setdefault(rid, []).append(str(md))
    # stable sort file lists
    for rid in list(out.keys()):
        out[rid] = sorted(set(out[rid]))
    return dict(sorted(out.items(), key=lambda kv: kv[0]))


def _scan_req_ids_in_code_comments(src_dir: Path) -> dict[str, list[str]]:
    """Best-effort: scan full text of .py files for REQ_... occurrences.

    Note: This does not strictly isolate comments/docstrings; it is a pragmatic
    signal for traceability mentions.

    Returns mapping: req_id -> list of src files where it appears.
    """
    out: dict[str, list[str]] = {}
    for py in _list_python_files(src_dir):
        text = _read_text_best_effort(py)
        if not text:
            continue
        for rid in sorted(set(REQ_ID_RE.findall(text))):
            out.setdefault(rid, []).append(str(py))
    for rid in list(out.keys()):
        out[rid] = sorted(set(out[rid]))
    return dict(sorted(out.items(), key=lambda kv: kv[0]))


def _build_src_inventory(project_root: Path) -> dict[str, Any]:
    src_dir = project_root / "src"
    py_files = _list_python_files(src_dir)

    inventory: dict[str, Any] = {
        "src_dir": str(src_dir),
        "python_files": [],
        "counts": {
            "python_files": len(py_files),
            "total_functions": 0,
            "total_classes": 0,
        },
    }

    total_functions = 0
    total_classes = 0

    for py in py_files:
        symbols = _extract_symbols_from_py(py)
        total_functions += len(symbols.functions)
        total_classes += len(symbols.classes)
        inventory["python_files"].append(
            {
                "path": str(py),
                "functions": symbols.functions,
                "classes": symbols.classes,
            }
        )

    inventory["counts"]["total_functions"] = total_functions
    inventory["counts"]["total_classes"] = total_classes

    return inventory


def _build_impl_docs_inventory(project_root: Path) -> dict[str, Any]:
    impl_dir = project_root / "impl-docs"
    md_files = _list_md_files(impl_dir)
    return {
        "impl_docs_dir": str(impl_dir),
        "markdown_files": [str(p) for p in md_files],
        "counts": {"markdown_files": len(md_files)},
    }


def _build_specs_inventory(project_root: Path) -> dict[str, Any]:
    specs_dir = project_root / "specs"
    md_files = _list_md_files(specs_dir)
    req_map = _scan_req_ids_in_specs(specs_dir)
    return {
        "specs_dir": str(specs_dir),
        "markdown_files": [str(p) for p in md_files],
        "req_ids": req_map,
        "counts": {
            "markdown_files": len(md_files),
            "unique_req_ids": len(req_map),
        },
    }


def _infer_missing_docs(project_root: Path) -> list[dict[str, Any]]:
    """Heuristic: for each src/<name>.py expect impl-docs/<nn>_<name>.md OR impl-docs/**/<name>.md.

    This is intentionally heuristic; it flags likely gaps.
    """
    src_dir = project_root / "src"
    impl_dir = project_root / "impl-docs"

    impl_md = _list_md_files(impl_dir)
    impl_names = {p.name.lower(): str(p) for p in impl_md}

    missing: list[dict[str, Any]] = []

    for py in _list_python_files(src_dir):
        base = py.stem.lower()
        # Candidate direct match
        direct_name = f"{base}.md"
        if direct_name in impl_names:
            continue

        # Candidate prefixed match like 01_core_system.md
        prefixed_match = None
        for md in impl_md:
            n = md.name.lower()
            if n.endswith(f"_{base}.md"):
                prefixed_match = str(md)
                break

        if prefixed_match:
            continue

        missing.append(
            {
                "src_file": str(py),
                "expected_impl_doc_candidates": [
                    f"impl-docs/{base}.md",
                    f"impl-docs/*_{base}.md",
                ],
            }
        )

    return missing


def _compute_spec_gaps(project_root: Path) -> dict[str, Any]:
    specs_dir = project_root / "specs"
    src_dir = project_root / "src"

    spec_req_map = _scan_req_ids_in_specs(specs_dir)
    code_req_map = _scan_req_ids_in_code_comments(src_dir)

    spec_req_ids = set(spec_req_map.keys())
    code_req_ids = set(code_req_map.keys())

    unimplemented = sorted(spec_req_ids - code_req_ids)

    # "Orphaned Specs" is ambiguous in the task text; we interpret as:
    # - Req IDs present in specs but never mentioned in code comments/strings.
    orphaned = list(unimplemented)

    return {
        "spec_req_ids": spec_req_map,
        "code_req_ids": code_req_map,
        "unimplemented_specs": [
            {"req_id": rid, "spec_files": spec_req_map.get(rid, [])} for rid in unimplemented
        ],
        "orphaned_specs": [
            {"req_id": rid, "spec_files": spec_req_map.get(rid, [])} for rid in orphaned
        ],
        "counts": {
            "spec_unique_req_ids": len(spec_req_ids),
            "code_unique_req_ids": len(code_req_ids),
            "unimplemented_specs": len(unimplemented),
            "orphaned_specs": len(orphaned),
        },
    }


def main() -> int:
    project_root = Path(os.getcwd()).resolve()

    summary: dict[str, Any] = {
        "project_root": str(project_root),
        "inventories": {
            "src": _build_src_inventory(project_root),
            "specs": _build_specs_inventory(project_root),
            "impl_docs": _build_impl_docs_inventory(project_root),
        },
        "trinity_audit": {
            "missing_docs": _infer_missing_docs(project_root),
        },
    }

    spec_gaps = _compute_spec_gaps(project_root)
    summary["trinity_audit"].update(spec_gaps)

    # Convenience: top-level counts
    summary["counts"] = {
        "missing_docs": len(summary["trinity_audit"].get("missing_docs", []) or []),
        "unimplemented_specs": int(spec_gaps.get("counts", {}).get("unimplemented_specs", 0) or 0),
        "orphaned_specs": int(spec_gaps.get("counts", {}).get("orphaned_specs", 0) or 0),
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
