# Documentation Implémentation : Context & Memory
**Version :** 0.1.1 (Itération 4)
**Date :** 2026-01-29

## 1. Vue d'ensemble
Ce module donne à l'IA la "vue" sur le projet. Il lit dynamiquement les fichiers locaux pour construire un prompt système riche, permettant à l'IA de modifier du code existant sans halluciner.

## 2. Module `ContextManager` (`src/context_manager.py`)
* **Dépendance :** Utilise la librairie `tiktoken` (OpenAI) pour estimer la charge du contexte.
* **Formatage :** Encapsule chaque fichier dans des balises XML-like `<file path='...'>...</file>` pour aider l'IA à distinguer les sources.

### 2.1 Context Scoping (optimisation tokens)
Pour réduire la consommation de tokens et focaliser l'IA, Albert supporte désormais des **scopes** de contexte.

Le scope contrôle **quels dossiers versionnés** sont chargés dans le Project Context.

#### Scopes disponibles
* **`full` (défaut)** : charge **tout**
  * `specs/` + `impl-docs/` + `src/`
  * À utiliser quand on a besoin d'une vue complète (requirements + doc vivante + code).

* **`code`** : charge **code + doc vivante**
  * `src/` + `impl-docs/` (ignore `specs/`)
  * À utiliser quand on implémente/débugge des détails techniques et qu'on veut économiser les tokens des specs.

* **`specs`** : charge **requirements + doc vivante**
  * `specs/` + `impl-docs/` (ignore `src/`)
  * À utiliser quand on raffine les exigences, l'architecture, ou des décisions produit, sans exposer le code.

* **`minimal`** : charge **uniquement la doc d'implémentation**
  * `impl-docs/` uniquement
  * À utiliser pour des questions rapides, des petits ajustements, ou quand on veut un contexte très léger.

#### Invariant UX / Sécurité
Quel que soit le scope, le contexte inclut toujours un en-tête contenant la **racine du projet** (Project Root). Cela évite toute confusion sur le projet actif.

## 3. Injection dans le Prompt
Lors d'une commande `implement`, le workflow est :
1.  L'utilisateur donne une instruction (souvent multi-ligne via l’éditeur).
2.  Le Wrapper compile le projet en un gros bloc texte (Project Context), selon le **scope** demandé.
3.  Le prompt final envoyé à l'IA est : `[INSTRUCTION UTILISATEUR] + [CONTEXTE PROJET]`.
4.  Le System Prompt ordonne à l'IA de renvoyer le **fichier complet** modifié, pas juste un diff (pour simplifier l'écriture disque).

### 3.1 CLI (`implement --scope ...`)
La commande `implement` accepte l'option :
* `--scope {full,code,specs,minimal}` (défaut: `full`)

Exemples :
* `implement --scope code`
* `implement --scope minimal`

## 4. Limites actuelles
* Pas de filtrage intelligent par pertinence (RAG) : le scope est un **filtre par dossiers**, pas une sélection sémantique.
* Sur de très gros projets, même `code` peut être volumineux ; une V2 pourra ajouter du RAG/embeddings et/ou des règles d'inclusion/exclusion plus fines.
