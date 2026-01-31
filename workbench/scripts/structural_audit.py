import os
import sys
from pathlib import Path


EXCLUDED_DIR_NAMES = {".git", "__pycache__", "venv", "node_modules"}


def _is_excluded_dir(name: str) -> bool:
    return name in EXCLUDED_DIR_NAMES


def _walk_filtered(root: Path):
    """Yield (dirpath, dirnames, filenames) like os.walk, pruning excluded dirs."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _is_excluded_dir(d)]
        yield Path(dirpath), list(dirnames), list(filenames)


def _build_index(root: Path) -> dict[Path, dict[str, object]]:
    index: dict[Path, dict[str, object]] = {}
    for dirpath, dirnames, filenames in _walk_filtered(root):
        index[dirpath] = {
            "subdirs": [dirpath / d for d in sorted(dirnames)],
            "files": sorted(filenames),
        }
    index.setdefault(root, {"subdirs": [], "files": []})
    return index


def _print_tree(root: Path, index: dict[Path, dict[str, object]]) -> None:
    print(str(root))

    def recurse(dirpath: Path, prefix: str) -> None:
        entry = index.get(dirpath, {})
        subdirs = list(entry.get("subdirs", []))
        files = list(entry.get("files", []))

        children: list[tuple[str, object]] = [("dir", p) for p in subdirs] + [("file", dirpath / f) for f in files]

        for i, (kind, child) in enumerate(children):
            is_last = i == (len(children) - 1)
            branch = "└── " if is_last else "├── "
            next_prefix = prefix + ("    " if is_last else "│   ")

            if kind == "dir":
                child_path: Path = child  # type: ignore[assignment]
                print(f"{prefix}{branch}{child_path.name}/")
                recurse(child_path, next_prefix)
            else:
                child_path: Path = child  # type: ignore[assignment]
                print(f"{prefix}{branch}{child_path.name}")

    recurse(root, "")


def _dir_has_any_file_recursively(dirpath: Path, index: dict[Path, dict[str, object]]) -> bool:
    entry = index.get(dirpath)
    if not entry:
        return False

    files = list(entry.get("files", []))
    if files:
        return True

    for subdir in entry.get("subdirs", []):
        if _dir_has_any_file_recursively(subdir, index):
            return True

    return False


def _find_empty_directories(root: Path, index: dict[Path, dict[str, object]]) -> list[Path]:
    """Return directories that contain no files in their subtree (with exclusions applied)."""
    empties: list[Path] = []

    for dirpath in sorted(index.keys(), key=lambda p: str(p)):
        if _is_excluded_dir(dirpath.name):
            continue
        if not _dir_has_any_file_recursively(dirpath, index):
            empties.append(dirpath)

    return empties


def main() -> int:
    # Run from project root regardless of current working directory.
    # Script location: <project_root>/workbench/scripts/structural_audit.py
    project_root = Path(__file__).resolve().parents[2]

    try:
        if not project_root.exists() or not project_root.is_dir():
            print(f"ERROR: Project root is not a directory: {project_root}", file=sys.stderr)
            return 2
    except Exception as e:
        print(f"ERROR: Cannot access project root {project_root}: {e}", file=sys.stderr)
        return 2

    index = _build_index(project_root)

    print("=== DIRECTORY TREE (excluded: .git, __pycache__, venv, node_modules) ===")
    _print_tree(project_root, index)

    empties = _find_empty_directories(project_root, index)

    print("\n=== EMPTY DIRECTORIES (no files recursively) ===")
    if not empties:
        print("(none)")
        return 0

    for p in empties:
        try:
            rel = p.relative_to(project_root)
            rel_str = "." if str(rel) == "." else str(rel)
        except Exception:
            rel_str = str(p)
        print(rel_str)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
