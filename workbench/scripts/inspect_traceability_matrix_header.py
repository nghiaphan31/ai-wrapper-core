from __future__ import annotations

from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[2]

    tm = root / "traceability_matrix.md"
    print("=== TRACEABILITY_MATRIX_EXISTS ===")
    print(str(tm.exists()))
    print("=== TRACEABILITY_MATRIX_PATH ===")
    print(str(tm))

    if tm.exists():
        content = tm.read_text(encoding="utf-8", errors="replace")
        print("=== TRACEABILITY_MATRIX_BEGIN ===")
        print(content)
        print("=== TRACEABILITY_MATRIX_END ===")

    candidates = [
        "workbench/scripts/update_matrix_from_audit.py",
        "workbench/scripts/deep_semantic_audit.py",
        "workbench/scripts/code_logic_extractor.py",
        "workbench/scripts/inspect_traceability_matrix_header.py",
    ]

    print("=== SCRIPT_EXISTENCE ===")
    for rel in candidates:
        p = root / rel
        print(f"{rel}: {p.exists()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
