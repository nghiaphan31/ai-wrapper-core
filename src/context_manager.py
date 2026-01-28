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

    def build_full_context(self) -> str:
        """
        Scan specs/, impl-docs/ et src/ pour construire le 'Resume Pack' complet.
        C'est ce que l'IA va 'voir' du projet.

        Ordre d'inclusion (priorité) :
          1) specs/ (référence)
          2) impl-docs/ (doc vivante)
          3) src/ (code)
        """
        context_parts = []
        context_parts.append("=== PROJECT CONTEXT (READ-ONLY) ===")

        # 1. Ajouter les spécifications (Priorité haute)
        specs_dir = self.project_root / "specs"
        if specs_dir.exists():
            for f in sorted(specs_dir.glob("*.md")):
                if self._should_skip_path(f):
                    continue
                rel_path = f.relative_to(self.project_root)
                context_parts.append(self.get_file_content(str(rel_path)))

        # 2. Ajouter la documentation d'implémentation (impl-docs/)
        impl_docs_dir = self.project_root / "impl-docs"
        if impl_docs_dir.exists():
            for f in sorted(impl_docs_dir.rglob("*.md")):
                if self._should_skip_path(f):
                    continue
                rel_path = f.relative_to(self.project_root)
                context_parts.append(self.get_file_content(str(rel_path)))

        # 3. Ajouter le code source (src/)
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
        GLOBAL_CONSOLE.print(f"Context loaded: {len(context_parts) - 1} files (~{token_count} tokens)")

        return full_text


# Instance globale
GLOBAL_CONTEXT = ContextManager()
