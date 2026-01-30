import os
import pathlib
import sys


EXCLUDED_DIR_NAMES = {".git", "__pycache__", "venv", "node_modules", ".idea", ".vscode"}


def _is_excluded_dir(dir_name: str) -> bool:
    return dir_name in EXCLUDED_DIR_NAMES


def _walk_filtered(root: pathlib.Path):
    """Yield (dirpath, dirnames, filenames) like os.walk, but prunes excluded dirs."""
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune in-place so os.walk does not descend into excluded directories
        dirnames[:] = [d for d in dirnames if not _is_excluded_dir(d)]
        yield pathlib.Path(dirpath), list(dirnames), list(filenames)


def _build_tree_index(root: pathlib.Path):
    """Build a mapping of directory -> (subdirs, files) with exclusions applied."""
    index: dict[pathlib.Path, dict[str, list[pathlib.Path] | list[str]]] = {}

    for dirpath, dirnames, filenames in _walk_filtered(root):
        # Normalize to Path objects
        subdirs = [dirpath / d for d in sorted(dirnames)]
        files = sorted(filenames)
        index[dirpath] = {"subdirs": subdirs, "files": files}

    # Ensure root exists in index even if os.walk yields nothing (e.g., permission issues)
    index.setdefault(root, {"subdirs": [], "files": []})
    return index


def _print_tree(root: pathlib.Path, index) -> None:
    """Print an ASCII tree for the directory structure."""
    print(str(root))

    def recurse(dirpath: pathlib.Path, prefix: str) -> None:
        children_dirs: list[pathlib.Path] = list(index.get(dirpath, {}).get("subdirs", []))
        children_files: list[str] = list(index.get(dirpath, {}).get("files", []))

        # Combine children in a stable order: dirs first, then files
        children = [("dir", p) for p in children_dirs] + [("file", dirpath / f) for f in children_files]

        for i, (kind, child) in enumerate(children):
            is_last = i == (len(children) - 1)
            branch = "└── " if is_last else "├── "
            next_prefix = prefix + ("    " if is_last else "│   ")

            if kind == "dir":
                print(f"{prefix}{branch}{child.name}/")
                recurse(child, next_prefix)
            else:
                print(f"{prefix}{branch}{child.name}")

    recurse(root, "")


def _dir_has_any_file_recursively(dirpath: pathlib.Path, index) -> bool:
    """Return True if dirpath contains at least one file in its subtree (excluding pruned dirs)."""
    entry = index.get(dirpath)
    if not entry:
        return False

    files: list[str] = list(entry.get("files", []))
    if files:
        return True

    for subdir in entry.get("subdirs", []):
        if _dir_has_any_file_recursively(subdir, index):
            return True

    return False


def _find_effectively_empty_dirs(root: pathlib.Path, index) -> list[pathlib.Path]:
    """Directories that contain no files anywhere under them (recursively), considering exclusions."""
    empties: list[pathlib.Path] = []

    # Evaluate all directories discovered by the filtered walk
    for dirpath in sorted(index.keys(), key=lambda p: str(p)):
        # Skip excluded dirs defensively (should already be pruned)
        if _is_excluded_dir(dirpath.name):
            continue

        if not _dir_has_any_file_recursively(dirpath, index):
            empties.append(dirpath)

    # Prefer not to label the root as "empty" if it contains subdirs but no files;
    # but requirement says "directories effectively empty"; keep root included if applicable.
    return empties


def main() -> int:
    root = pathlib.Path(os.getcwd()).resolve()

    # Basic sanity: ensure we can at least stat the root
    try:
        if not root.exists() or not root.is_dir():
            print(f"ERROR: Root path is not a directory: {root}", file=sys.stderr)
            return 2
    except Exception as e:
        print(f"ERROR: Cannot access root path {root}: {e}", file=sys.stderr)
        return 2

    index = _build_tree_index(root)

    print("=== DIRECTORY TREE (excluded: .git, __pycache__, venv, node_modules, .idea, .vscode) ===")
    _print_tree(root, index)

    empties = _find_effectively_empty_dirs(root, index)

    print("\n=== EFFECTIVELY EMPTY DIRECTORIES (no files recursively) ===")
    if not empties:
        print("(none)")
        return 0

    for p in empties:
        try:
            rel = p.relative_to(root)
            rel_str = "." if str(rel) == "." else str(rel)
        except Exception:
            rel_str = str(p)
        print(rel_str)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
