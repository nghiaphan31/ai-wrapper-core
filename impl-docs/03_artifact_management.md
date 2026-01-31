# Documentation Implémentation : Artifact Management
**Version :** 0.1.4
**Date :** 2026-01-31

## 1. Vue d'ensemble
Ce module implémente le principe "Zéro Copy-Paste". Il transforme les réponses JSON structurées de l'IA en fichiers physiques sur le disque local.

En plus de l’écriture des artefacts, Albert génère un **manifest d’intégrité de session** (REQ_DATA_030) listant les fichiers produits et leurs empreintes SHA-256.

## 2. Protocole d'Échange (JSON Protocol)
L'IA ne doit pas répondre en texte libre pour la génération de code. Elle doit suivre ce schéma strict :
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

### 3.1.1 Artifact Storage Structure (naming convention)
**Convention (alignée Specs / baseline) :** les dossiers d’artefacts suivent le pattern :

`step_YYYYMMDD_HHMMSS_<short_id>`

Exemple :
* `artifacts/step_20260130_120500_a1b2/src/main.py`

### 3.2 Tracking de session (REQ_DATA_030)
`ArtifactManager` maintient une liste interne :
* `self._session_artifacts` : liste des **chemins relatifs à la racine projet** des fichiers écrits pendant l’exécution courante.

### 3.3 Hashing SHA-256
Méthode :
* `calculate_sha256(file_path)`

### 3.4 Manifest d’intégrité de session (REQ_DATA_030)
Méthode :
* `generate_session_manifest(session_id)`

Sortie :
* `manifests/session_<session_id>_manifest.json`

## 4. Workflow Utilisateur
1. **Commande `prompt`** : l’utilisateur décrit la tâche/prompt (multi-ligne possible via Nano Integration).
2. Albert appelle l’IA et écrit les fichiers dans `artifacts/<step_id>/...`.
3. Albert lance la revue interactive (diff + validation atomique) puis applique/commit/push si validé.
4. **En fin de commande**, Albert génère le manifest de session et affiche :
   * `📜  Session Manifest saved: manifests/session_<session_id>_manifest.json`

### 4.1 Traceabilité renforcée : réponse IA affichée
Pour améliorer la traçabilité des interactions, `prompt` affiche la **réponse brute** de l’IA (JSON) directement à l’écran, encadrée par des délimiteurs stables :

```text
[AI_RESPONSE_BEGIN]
{...json...}
[AI_RESPONSE_END]
```

Comme l’écran est capturé dans `sessions/<YYYY-MM-DD>/transcript.log`, cette réponse est donc également présente dans le transcript.

> Important : cela n’annule pas le principe Zéro Copy-Paste, car l’écriture des fichiers reste automatisée via parsing JSON → `artifacts/`.
