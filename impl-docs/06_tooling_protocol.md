# Documentation Implémentation : Tooling Protocol (Artifact-First)
**Version :** 0.1.0
**Date :** 2026-01-30

## 1. Objectif
Ce document décrit le protocole d’exécution d’outils locaux en mode **Glass Box** (transparence totale), conformément à **REQ_AUDIT_060 (Transparent Tool Chain / Artifact-First Tool Execution)**.

Le principe : **aucune exécution locale “outil” ne doit être opaque**. Toute logique exécutée doit être vérifiable a posteriori via des artefacts persistants.

## 2. Déclenchement : balises `<tool_code>`
Quand le modèle a besoin d’inspecter l’environnement (audit, ground truth), il ne doit pas répondre directement. Il doit produire un script Python encapsulé strictement dans :

```text
<tool_code>
# python code
</tool_code>
```

Ce mécanisme est imposé via le **System Prompt** (voir `src/ai_client.py`).

## 3. Workflow d’exécution (Artifact-First)
L’exécution d’un tool script suit une boucle automatique dans `src/main.py` :

### 3.1 Détection
Le wrapper scanne la réponse IA. Si elle contient `<tool_code>...</tool_code>`, il déclenche le flux outil.

### 3.2 Étape d’artefacts
Le wrapper crée un dossier :

* `artifacts/step_YYYYMMDD_HHMMSS_tool_request/`

Dans ce dossier, il écrit **avant exécution** :

* `tool_script.py` (artefact 1)

### 3.3 Exécution contrôlée
Le wrapper exécute ensuite :

* `python tool_script.py`

**Garde-fous :**
* pas de `shell=True`,
* `cwd` fixé à la racine projet,
* timeout (par défaut: 20s).

### 3.4 Preuve d’exécution
Après exécution, le wrapper écrit **dans le même dossier** :

* `tool_output.txt` (artefact 2)

Contenu :
* `returncode`,
* bloc `[STDOUT]`,
* bloc `[STDERR]`.

### 3.5 Boucle de feedback automatique (sans input utilisateur)
Le wrapper renvoie immédiatement au modèle un message système :

```text
System: Tool executed. Artifacts saved. Output:
<content of tool_output.txt>
```

Ce message est également logué dans le transcript (`sessions/<date>/transcript.log`) via la console.

Le wrapper répète la boucle si la réponse suivante contient encore `<tool_code>` (avec un maximum d’itérations pour éviter les boucles infinies).

## 4. Vérification utilisateur (Proof-First)
L’utilisateur peut vérifier exactement ce qui a été exécuté en ouvrant :

* `artifacts/.../tool_script.py` : la logique exacte exécutée localement
* `artifacts/.../tool_output.txt` : la preuve (stdout/stderr)

Ce protocole fournit une transparence “Glass Box” : aucune inspection locale n’est implicite ou non traçable.

## 5. Intégration avec le manifest de session
Les fichiers :
* `tool_script.py`
* `tool_output.txt`

sont **trackés comme artefacts** et inclus dans le manifest d’intégrité de session (voir `src/artifact_manager.py` et `manifests/session_<session_id>_manifest.json`).

## 6. Références
* **Specs :** `specs/01_architecture_baseline.md` → REQ_AUDIT_060
* **Code :**
  * `src/ai_client.py` (System Prompt : instructions `<tool_code>`)
  * `src/main.py` (boucle d’exécution Artifact-First)
* **Traçabilité :** `traceability_matrix.md`
