# Documentation Implémentation : Context & Memory
**Version :** 0.1.0 (Itération 4)
**Date :** 2026-01-28

## 1. Vue d'ensemble
Ce module donne à l'IA la "vue" sur le projet. Il lit dynamiquement les fichiers locaux pour construire un prompt système riche, permettant à l'IA de modifier du code existant sans halluciner.

## 2. Module `ContextManager` (`src/context_manager.py`)
* **Dépendance :** Utilise la librairie `tiktoken` (OpenAI) pour estimer la charge du contexte.
* **Stratégie de lecture :**
    * Scanne récursivement `specs/` (Markdown).
    * Scanne récursivement `src/` (Python), en excluant les fichiers cachés/systèmes.
* **Formatage :** Encapsule chaque fichier dans des balises XML-like `<file path='...'>...</file>` pour aider l'IA à distinguer les sources.

## 3. Injection dans le Prompt
Lors d'une commande `implement`, le workflow est :
1.  L'utilisateur donne une instruction (souvent multi-ligne via l’éditeur).
2.  Le Wrapper compile le projet en un gros bloc texte ("Resume Pack").
3.  Le prompt final envoyé à l'IA est : `[INSTRUCTION UTILISATEUR] + [CONTEXTE PROJET]`.
4.  Le System Prompt ordonne à l'IA de renvoyer le **fichier complet** modifié, pas juste un diff (pour simplifier l'écriture disque).

## 4. Limites actuelles
* Pas de filtrage intelligent (envoie tout le projet). Risque de saturation context window sur de très gros projets (à améliorer en V2 avec RAG/Embeddings).
