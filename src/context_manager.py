import os
import tiktoken
from pathlib import Path
from src.config import GLOBAL_CONFIG
from src.console import GLOBAL_CONSOLE


class ContextManager:
    def __init__(self):
        self.project_root = GLOBAL_CONFIG.project_root
        # Initialisation du tokenizer (cl100k_base est utilisé par GPT-4/GPT-3.5/GPT-5)
        try:
            self.encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            # Fallback si tiktoken a un souci (rare)
            self.encoder = None

    def count_tokens(self, text: str) -> int:
        """Estime le nombre de tokens d'un texte."""
        if not self.encoder or not text:
            return 0
        return len(self.encoder.encode(text))

    def get_file_content(self, relative_path: str) -> str:
        """Lit un fichier et le retourne formaté avec des balises XML."""
        file_path = self.project_root / relative_path
        if not file_path.exists():
            return f"<file path='{relative_path}'>[FILE NOT FOUND]</file>"

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return f"<file path='{relative_path}'>\n{content}\n</file>"
        except Exception as e:
            return f"<file path='{relative_path}'>[ERROR READING FILE: {e}]</file>"

    def _should_skip_path(self, path: Path) -> bool:
        """Filtre simple pour éviter fichiers/dossiers non pertinents."""
        s = str(path)
        # Ignore dossiers cachés et caches python
        if "/." in s or "__pycache__" in s:
            return True
        return False

    def build_full_context(self, scope: str = "full") -> str:
        """Build the project context with a configurable scope.

        Scopes:
          - "full"    : specs/ + impl-docs/ + src/
          - "code"    : impl-docs/ + src/        (ignore specs/)
          - "specs"   : specs/ + impl-docs/      (ignore src/)
          - "minimal" : impl-docs/ only          (project structure map)

        The "Project Root" header must always be present regardless of scope.

        Ordering (when included):
          1) specs/ (reference)
          2) impl-docs/ (living docs)
          3) src/ (code)
        """
        scope = (scope or "full").strip().lower()
        allowed = {"full", "code", "specs", "minimal"}
        if scope not in allowed:
            scope = "full"

        include_specs = scope in {"full", "specs"}
        include_impl_docs = True  # always included for all scopes
        include_src = scope in {"full", "code"}

        context_parts: list[str] = []
        context_parts.append("=== PROJECT CONTEXT (READ-ONLY) ===")
        # Always show project root (critical context)
        context_parts.append(f"Project Root: {self.project_root}")

        # 1) specs/
        if include_specs:
            specs_dir = self.project_root / "specs"
            if specs_dir.exists():
                for f in sorted(specs_dir.glob("*.md")):
                    if self._should_skip_path(f):
                        continue
                    rel_path = f.relative_to(self.project_root)
                    context_parts.append(self.get_file_content(str(rel_path)))

        # 2) impl-docs/
        if include_impl_docs:
            impl_docs_dir = self.project_root / "impl-docs"
            if impl_docs_dir.exists():
                for f in sorted(impl_docs_dir.rglob("*.md")):
                    if self._should_skip_path(f):
                        continue
                    rel_path = f.relative_to(self.project_root)
                    context_parts.append(self.get_file_content(str(rel_path)))

        # 3) src/
        if include_src:
            src_dir = self.project_root / "src"
            if src_dir.exists():
                for f in sorted(src_dir.rglob("*.py")):
                    if self._should_skip_path(f):
                        continue
                    # Comportement historique: éviter les chemins contenant "__"
                    if "__" in str(f):
                        continue
                    rel_path = f.relative_to(self.project_root)
                    context_parts.append(self.get_file_content(str(rel_path)))

        full_text = "\n\n".join(context_parts)

        # Log info tokens
        token_count = self.count_tokens(full_text)
        # -2 because we add two headers: context marker + Project Root line
        file_count = max(0, len(context_parts) - 2)
        GLOBAL_CONSOLE.print(
            f"Context loaded (scope={scope}): {file_count} files (~{token_count} tokens)"
        )

        return full_text


# Instance globale
GLOBAL_CONTEXT = ContextManager()
