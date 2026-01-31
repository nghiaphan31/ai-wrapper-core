import ast
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".idea",
    ".vscode",
    "sessions",
    "artifacts",
    "outputs",
    "inputs",
    "secrets",
    "ledger",
    "manifests",
}

INCLUDE_EXTENSIONS = {".py"}


def _should_exclude_path(p: Path) -> bool:
    parts = set(p.parts)
    if parts & EXCLUDED_DIRS:
        return True
    # defensive exclusions
    if any(part.startswith(".") and part not in {".", ".."} for part in p.parts):
        # allow hidden only if explicitly included; here exclude to reduce noise
        return True
    return False


def _safe_get_docstring(node: ast.AST) -> str:
    try:
        return ast.get_docstring(node) or ""
    except Exception:
        return ""


def _node_span(node: ast.AST) -> dict[str, Any]:
    return {
        "lineno": getattr(node, "lineno", None),
        "end_lineno": getattr(node, "end_lineno", None),
        "col_offset": getattr(node, "col_offset", None),
        "end_col_offset": getattr(node, "end_col_offset", None),
    }


def _call_name(call: ast.Call) -> str:
    fn = call.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        # build dotted name best-effort
        parts = []
        cur = fn
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        parts.reverse()
        return ".".join(parts)
    return "<call>"


def _extract_imports(tree: ast.AST) -> list[str]:
    imports: list[str] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                imports.append(a.name)
        elif isinstance(n, ast.ImportFrom):
            mod = n.module or ""
            for a in n.names:
                if mod:
                    imports.append(f"{mod}.{a.name}")
                else:
                    imports.append(a.name)
    # stable unique
    out = sorted(set(imports))
    return out


def _extract_key_calls(body: list[ast.stmt]) -> dict[str, Any]:
    """Extract a compact semantic signature of logic inside a function/method.

    We avoid full AST dumps (too verbose) and instead capture:
      - called function names (top frequency)
      - attribute calls (e.g., GLOBAL_LEDGER.log_event)
      - presence of key constructs (try/except, with, for, while, if)
      - string literals that look like file paths or requirement-ish tokens

    This is intended for downstream cognitive mapping.
    """
    calls: list[str] = []
    constructs = {
        "has_try": False,
        "has_with": False,
        "has_for": False,
        "has_while": False,
        "has_if": False,
        "has_raise": False,
        "has_return": False,
        "has_subprocess": False,
    }
    string_hints: list[str] = []

    class _V(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call):
            name = _call_name(node)
            calls.append(name)
            if name.startswith("subprocess.") or name == "subprocess.run":
                constructs["has_subprocess"] = True
            self.generic_visit(node)

        def visit_Try(self, node: ast.Try):
            constructs["has_try"] = True
            self.generic_visit(node)

        def visit_With(self, node: ast.With):
            constructs["has_with"] = True
            self.generic_visit(node)

        def visit_For(self, node: ast.For):
            constructs["has_for"] = True
            self.generic_visit(node)

        def visit_While(self, node: ast.While):
            constructs["has_while"] = True
            self.generic_visit(node)

        def visit_If(self, node: ast.If):
            constructs["has_if"] = True
            self.generic_visit(node)

        def visit_Raise(self, node: ast.Raise):
            constructs["has_raise"] = True
            self.generic_visit(node)

        def visit_Return(self, node: ast.Return):
            constructs["has_return"] = True
            self.generic_visit(node)

        def visit_Constant(self, node: ast.Constant):
            if isinstance(node.value, str):
                s = node.value
                # heuristics: likely paths / folders / requirement IDs
                if (
                    "/" in s
                    or s.startswith("REQ_")
                    or "workbench/scripts" in s
                    or "ledger" in s
                    or "artifacts" in s
                    or "specs" in s
                    or "impl-docs" in s
                ):
                    # keep short hints only
                    s2 = s.strip()
                    if len(s2) > 200:
                        s2 = s2[:200] + "..."
                    string_hints.append(s2)
            self.generic_visit(node)

    _V().visit(ast.Module(body=body, type_ignores=[]))

    # frequency summary
    freq: dict[str, int] = {}
    for c in calls:
        freq[c] = freq.get(c, 0) + 1

    top_calls = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:25]

    return {
        "constructs": constructs,
        "top_calls": [{"name": n, "count": k} for n, k in top_calls],
        "string_hints": sorted(set(string_hints))[:50],
        "calls_count": len(calls),
    }


def _fingerprint_ast(node: ast.AST) -> str:
    """Compact AST fingerprint (structure only) for quick similarity grouping."""
    try:
        dumped = ast.dump(node, include_attributes=False, annotate_fields=True)
    except TypeError:
        dumped = ast.dump(node)
    # keep it compact
    if len(dumped) > 500:
        dumped = dumped[:500] + "..."
    return dumped


@dataclass
class FunctionInfo:
    name: str
    qualname: str
    kind: str  # function | method
    args: list[str]
    docstring: str
    span: dict[str, Any]
    decorators: list[str]
    returns_annotation: str
    logic: dict[str, Any]
    ast_fingerprint: str


def _decorator_names(node: ast.AST) -> list[str]:
    decs = getattr(node, "decorator_list", []) or []
    out: list[str] = []
    for d in decs:
        if isinstance(d, ast.Name):
            out.append(d.id)
        elif isinstance(d, ast.Attribute):
            # best-effort dotted
            parts = []
            cur = d
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
            parts.reverse()
            out.append(".".join(parts))
        else:
            out.append(type(d).__name__)
    return out


def _annotation_to_str(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return type(node).__name__


def _args_list(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    out: list[str] = []
    a = fn.args
    for arg in getattr(a, "posonlyargs", []) or []:
        out.append(arg.arg)
    for arg in getattr(a, "args", []) or []:
        out.append(arg.arg)
    if getattr(a, "vararg", None) is not None:
        out.append("*" + a.vararg.arg)
    for arg in getattr(a, "kwonlyargs", []) or []:
        out.append(arg.arg)
    if getattr(a, "kwarg", None) is not None:
        out.append("**" + a.kwarg.arg)
    return out


def _extract_functions_and_classes(tree: ast.AST) -> dict[str, Any]:
    classes: list[dict[str, Any]] = []
    functions: list[FunctionInfo] = []

    for node in getattr(tree, "body", []) or []:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fi = FunctionInfo(
                name=node.name,
                qualname=node.name,
                kind="function",
                args=_args_list(node),
                docstring=_safe_get_docstring(node),
                span=_node_span(node),
                decorators=_decorator_names(node),
                returns_annotation=_annotation_to_str(getattr(node, "returns", None)),
                logic=_extract_key_calls(getattr(node, "body", []) or []),
                ast_fingerprint=_fingerprint_ast(node),
            )
            functions.append(fi)

        elif isinstance(node, ast.ClassDef):
            cls_doc = _safe_get_docstring(node)
            bases: list[str] = []
            for b in node.bases:
                try:
                    bases.append(ast.unparse(b))
                except Exception:
                    bases.append(type(b).__name__)

            methods: list[FunctionInfo] = []
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qual = f"{node.name}.{sub.name}"
                    mi = FunctionInfo(
                        name=sub.name,
                        qualname=qual,
                        kind="method",
                        args=_args_list(sub),
                        docstring=_safe_get_docstring(sub),
                        span=_node_span(sub),
                        decorators=_decorator_names(sub),
                        returns_annotation=_annotation_to_str(getattr(sub, "returns", None)),
                        logic=_extract_key_calls(getattr(sub, "body", []) or []),
                        ast_fingerprint=_fingerprint_ast(sub),
                    )
                    methods.append(mi)

            classes.append(
                {
                    "name": node.name,
                    "bases": bases,
                    "docstring": cls_doc,
                    "span": _node_span(node),
                    "methods": [m.__dict__ for m in methods],
                }
            )

    return {
        "classes": classes,
        "functions": [f.__dict__ for f in functions],
    }


def _iter_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # prune excluded dirs
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith(".")]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() not in INCLUDE_EXTENSIONS:
                continue
            if _should_exclude_path(p):
                continue
            files.append(p)
    files.sort(key=lambda x: str(x))
    return files


def analyze_repo(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()

    targets = []
    # Analyze only versioned code areas by default
    for sub in ["src", "workbench/scripts"]:
        p = project_root / sub
        if p.exists() and p.is_dir():
            targets.append(p)

    results: dict[str, Any] = {
        "project_root": str(project_root),
        "analyzed_roots": [str(p) for p in targets],
        "files": [],
        "errors": [],
    }

    for root in targets:
        for py_file in _iter_python_files(root):
            rel = None
            try:
                rel = str(py_file.relative_to(project_root))
            except Exception:
                rel = str(py_file)

            try:
                text = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                results["errors"].append({"file": rel, "error": f"read_failed: {e}"})
                continue

            try:
                tree = ast.parse(text, filename=rel)
            except SyntaxError as e:
                results["errors"].append(
                    {
                        "file": rel,
                        "error": f"syntax_error: {e.msg}",
                        "lineno": getattr(e, "lineno", None),
                        "offset": getattr(e, "offset", None),
                    }
                )
                continue
            except Exception as e:
                results["errors"].append({"file": rel, "error": f"parse_failed: {e}"})
                continue

            mod_doc = _safe_get_docstring(tree)
            imports = _extract_imports(tree)
            defs = _extract_functions_and_classes(tree)

            results["files"].append(
                {
                    "path": rel,
                    "module_docstring": mod_doc,
                    "imports": imports,
                    "definitions": defs,
                }
            )

    return results


def main() -> int:
    project_root = Path(os.getcwd()).resolve()
    data = analyze_repo(project_root)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
