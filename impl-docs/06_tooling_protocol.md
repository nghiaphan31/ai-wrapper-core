# Documentation Implémentation : Tooling Protocol (Workbench Scripts + Exec)
**Version :** 0.2.2
**Date :** 2026-01-31

## 1. Objectif
Ce document décrit le protocole d’exécution d’outils locaux en mode **Glass Box** (transparence totale), conformément à :
- **REQ_AUDIT_060** (Transparent Tool Chain / Artifact-First Tool Execution)
- **REQ_CORE_055** (Workbench Execution Sandbox)
- **REQ_CORE_090** (Unified Generation Protocol — JSON, pas XML)
- **REQ_CORE_095** (Explicit Execution Request)

Le principe : **aucune exécution locale “outil” ne doit être opaque**. Toute logique exécutée doit être vérifiable a posteriori.

## 2. Dépréciation : XML Tooling (`<tool_code>`) — REMOVED
L’ancien mécanisme basé sur des balises XML (ex: `<tool_code>...</tool_code>`) est **déprécié** et **ne doit plus être utilisé**.

### 2.1 Pourquoi
- **REQ_CORE_090** impose un protocole unifié JSON (`{"artifacts": [...]}`) pour générer des outils.
- Les balises XML sont fragiles (parsing) et encouragent des workflows implicites.

### 2.2 Remplacement
Le protocole tooling est désormais : **Workbench Scripts + Exec**.

## 3. Protocole : Workbench Scripts + Exec
### 3.1 Génération (Step 1)
Quand un outil est nécessaire (audit, inspection, maintenance), il doit être **créé** comme un script versionné dans :
- `workbench/scripts/`

La génération doit se faire via le protocole JSON standard (REQ_CORE_090), par exemple :
```json
{
  "thought_process": "...",
  "artifacts": [
    {
      "path": "workbench/scripts/structural_audit.py",
      "operation": "create",
      "content": "# python code"
    }
  ]
}
```

### 3.2 Exécution explicite (Step 2)
La génération et l’exécution sont **deux étapes distinctes** (REQ_CORE_095).

L’exécution se fait via la commande CLI interactive :
- `exec <script.py> [args...]`

**Comportement effectif (implémentation actuelle, alignée UX) :**
- l’argument `<script.py>` est un chemin **relatif à `workbench/scripts/`** (et non plus un chemin relatif à la racine projet),
- les arguments suivants sont passés tels quels au script.

Exemples valides :
- `exec hello_world.py`
- `exec audits/scan_repo.py --flag value`

Exemples invalides (bloqués) :
- `exec /tmp/x.py` (chemin absolu)
- `exec ../src/main.py` (sort de `workbench/scripts/`)
- `exec workbench/scripts/hello_world.py` (désormais à éviter : le préfixe `workbench/scripts/` n’est plus attendu)

### 3.3 Sandbox d’exécution (REQ_CORE_055)
L’exécution est effectuée par `WorkbenchRunner` :
- **Restriction de chemin** : le script doit être situé **strictement** sous `workbench/scripts/`.
- **Interdictions** : exécuter un script depuis `src/`, `/tmp`, ou tout autre chemin via ce runner est **FORBIDDEN**.
- **Timeout** : `subprocess.run(..., timeout=60)`.
- **Capture** : `stdout` et `stderr` sont capturés et affichés clairement.

## 4. Transparence & preuves (Artifact-First)
Le protocole Workbench Scripts + Exec garantit :
- le script est **versionné** (Git) et inspectable (`workbench/scripts/...`),
- l’exécution est **explicite** (commande `exec`),
- la sortie est affichée en console de manière claire (Return code + STDOUT/STDERR).

> Note : la sauvegarde systématique de la preuve d’exécution (`stdout/stderr`) comme artefact `.txt` peut être ajoutée en extension, mais le présent état documente le protocole effectif actuel.

## 5. Références
- **Specs :** `specs/01_architecture_baseline.md` → REQ_AUDIT_060, REQ_CORE_055, REQ_CORE_090, REQ_CORE_095
- **Code :**
  - `src/workbench_runner.py` (sandbox runner)
  - `src/main.py` (commande `exec`)
- **Traçabilité :** `traceability_matrix.md`
