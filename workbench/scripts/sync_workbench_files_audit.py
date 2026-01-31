import os
import sys
import json
import hashlib
import pathlib
import subprocess
from dataclasses import dataclass
from typing import Iterable


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CmdResult:
    returncode: int
    stdout: str
    stderr: str


def run(cmd: list[str]) -> CmdResult:
    p = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=False)
    return CmdResult(int(p.returncode), p.stdout or "", p.stderr or "")


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def list_files(base: pathlib.Path, patterns: Iterable[str]) -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    if not base.exists():
        return out
    for pat in patterns:
        out.extend(base.rglob(pat))
    out = [p for p in out if p.is_file()]
    out.sort(key=lambda p: str(p))
    return out


def rel(p: pathlib.Path) -> str:
    try:
        return str(p.relative_to(PROJECT_ROOT))
    except Exception:
        return str(p)


def main() -> int:
    workbench_scripts = PROJECT_ROOT / "workbench" / "scripts"
    src_scripts = PROJECT_ROOT / "src" / "scripts"

    report: dict = {
        "project_root": str(PROJECT_ROOT),
        "paths": {
            "workbench/scripts": str(workbench_scripts),
            "src/scripts": str(src_scripts),
        },
        "git": {},
        "inventory": {
            "workbench_scripts": [],
            "src_scripts": [],
        },
        "duplicates_by_basename": {},
        "same_content_pairs": [],
        "diff_content_pairs": [],
        "suggested_actions": [],
    }

    # 1) Git status (ground truth)
    gs = run(["git", "status", "-s"])
    report["git"]["status_returncode"] = gs.returncode
    report["git"]["status_stdout"] = gs.stdout
    report["git"]["status_stderr"] = gs.stderr

    # 2) File inventories
    wb_files = list_files(workbench_scripts, ["*.py", "*.sh", "*.md", "README*", "*.txt"])
    ss_files = list_files(src_scripts, ["*.py", "*.sh", "*.md", "README*", "*.txt"])

    for p in wb_files:
        report["inventory"]["workbench_scripts"].append(
            {
                "path": rel(p),
                "size": p.stat().st_size,
                "sha256": sha256(p),
            }
        )

    for p in ss_files:
        report["inventory"]["src_scripts"].append(
            {
                "path": rel(p),
                "size": p.stat().st_size,
                "sha256": sha256(p),
            }
        )

    # 3) Detect duplicates by basename across locations
    by_name: dict[str, dict[str, dict]] = {}
    for entry in report["inventory"]["workbench_scripts"]:
        name = pathlib.Path(entry["path"]).name
        by_name.setdefault(name, {})["workbench"] = entry
    for entry in report["inventory"]["src_scripts"]:
        name = pathlib.Path(entry["path"]).name
        by_name.setdefault(name, {})["src"] = entry

    for name, locs in sorted(by_name.items(), key=lambda kv: kv[0]):
        if "workbench" in locs and "src" in locs:
            report["duplicates_by_basename"][name] = {
                "workbench": locs["workbench"],
                "src": locs["src"],
            }
            if locs["workbench"]["sha256"] == locs["src"]["sha256"]:
                report["same_content_pairs"].append({"name": name, "workbench": locs["workbench"]["path"], "src": locs["src"]["path"]})
            else:
                report["diff_content_pairs"].append({"name": name, "workbench": locs["workbench"]["path"], "src": locs["src"]["path"]})

    # 4) Suggested actions (non-destructive suggestions only)
    if ss_files and not wb_files:
        report["suggested_actions"].append(
            "Found files in src/scripts but none in workbench/scripts. Consider moving operational scripts to workbench/scripts (REQ_ARCH_020/021)."
        )
    if report["same_content_pairs"]:
        report["suggested_actions"].append(
            "Some scripts exist in both workbench/scripts and src/scripts with identical content. Consider keeping only the workbench copy and removing/relocating src/scripts duplicates to avoid confusion."
        )
    if report["diff_content_pairs"]:
        report["suggested_actions"].append(
            "Some scripts share the same basename across workbench/scripts and src/scripts but differ in content. Manual decision needed: which is authoritative, then sync accordingly."
        )

    # 5) Print JSON report
    print(json.dumps(report, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
