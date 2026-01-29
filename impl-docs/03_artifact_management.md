# Documentation Implémentation : Artifact Management
**Version :** 0.1.1
**Date :** 2026-01-29

## 1. Vue d'ensemble
Ce module implémente le principe "Zéro Copy-Paste". Il transforme les réponses JSON structurées de l'IA en fichiers physiques sur le disque local.

En plus de l’écriture des artefacts, Albert génère désormais un **manifest d’intégrité de session** (REQ_DATA_030) listant les fichiers produits et leurs empreintes SHA-256.

## 2. Protocole d'Échange (JSON Protocol)
L'IA ne doit plus répondre en texte libre pour la génération de code. Elle doit suivre ce schéma strict :
```json
{
  "thought_process": "Explication...",
  "artifacts": [
    {
      "path": "src/mon_script.py",
      "operation": "create",
      "content": "print('code')"
    }
  ]
}
```

## 3. Module `ArtifactManager` (`src/artifact_manager.py`)

### 3.1 Écriture des artefacts
* Les fichiers sont écrits sous :
  * `artifacts/<step_id>/<path>`
* Exemple :
  * `artifacts/step_153012/src/main.py`

Chaque écriture déclenche :
* un log console `Artifact created: ...`
* un événement ledger `file_write` avec `artifacts_links=[<path absolu>]`

### 3.2 Tracking de session (REQ_DATA_030)
`ArtifactManager` maintient une liste interne :
* `self.session_artifacts` : liste des chemins de fichiers écrits pendant l’exécution courante.

Cette liste sert de source pour générer le manifest en fin de workflow.

### 3.3 Hashing SHA-256
Méthode :
* `calculate_sha256(file_path)`

Rôle :
* calculer l’empreinte SHA-256 (hex) d’un fichier existant.

### 3.4 Manifest d’intégrité de session (REQ_DATA_030)
Méthode :
* `generate_session_manifest(session_id)`

Sortie :
* `manifests/session_<session_id>_manifest.json`

Structure JSON :
```json
{
  "session_id": "...",
  "timestamp": "...",
  "artifacts": [
    {"path": "artifacts/step_X/file.py", "sha256": "..."}
  ]
}
```

Comportement :
* Le dossier `manifests/` est créé automatiquement si absent.
* Si **aucun** artefact n’a été produit, le manifest est tout de même écrit avec :
  * `"artifacts": []`
* Si un fichier tracké n’existe plus au moment de la génération, il est ignoré (pas de crash).

## 4. Workflow Utilisateur
1. **Commande `implement`** : l’utilisateur décrit la tâche (multi-ligne possible via Nano Integration).
2. Albert appelle l’IA et écrit les fichiers dans `artifacts/<step_id>/...`.
3. Albert génère un manifest de session et affiche :
   * `📜 Manifest saved: manifests/session_<session_id>_manifest.json`
4. Albert lance la revue interactive (diff + validation atomique) puis applique/commit/push si validé.
