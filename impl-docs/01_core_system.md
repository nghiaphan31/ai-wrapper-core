# Project Albert — Documentation d'Implémentation : Core System
**Version :** 0.1.3
**Date :** 2026-01-31

## 1. Vue d'ensemble
**Project Albert** est un outil local-first qui agit comme un *steward* (intendant) rigoureux entre l’Utilisateur et le Modèle IA.

Albert n’est pas un simple "chat" : il orchestre le workflow, écrit les artefacts sur disque (zéro copy-paste), et impose une **traçabilité vérifiable** (transcript + ledger + payloads bruts). Son rôle central est de garantir qu’à tout moment on puisse répondre, preuves à l’appui :
* **qui** a demandé **quoi**, **quand**,
* **quel** modèle a répondu,
* **quels** fichiers ont été produits/modifiés,
* et **où** retrouver l’échange brut correspondant.

Le noyau (Core) gère l'initialisation, la configuration et, surtout, la traçabilité des opérations. Il fournit également une boucle CLI interactive et les points d’entrée de workflow (`test_ai`, `prompt`).

> Note : l’ancienne commande `implement` existe encore comme **alias rétro-compatible**, mais est désormais **dépréciée** au profit de `prompt`.

### 1.1 Workbench (Stewardship Tooling) — REQ_ARCH_020
Le dépôt inclut un dossier **`workbench/`** destiné aux outils d’intendance (*stewardship tools*) : scripts d’audit, maintenance, inspection structurelle, etc.

**Principe (REQ_ARCH_020) :**
* Les scripts opérationnels MUST être stockés dans `workbench/scripts/`.
* Ils sont **versionnés** (Git) mais **distincts** du livrable applicatif dans `src/`.

**Objectif :** fournir un “home” permanent pour l’outillage opérationnel afin d’éviter la confusion entre :
* code produit/livrable (`src/`),
* scripts d’audit/maintenance (workbench),
* scripts temporaires générés pour exécution Artifact-First (`artifacts/.../tool_script.py`).

### 1.2 Audit Ledger System (Traceabilité + Coûts)
En plus du ledger événementiel (machine-level), Albert maintient désormais un **Audit Ledger** orienté "transactions" pour assurer une traçabilité directe des opérations et des coûts.

* **Fichier :** `ledger/audit_log.jsonl` (append-only)
* **Objectif :** lier explicitement une action utilisateur (`prompt`) à un `step_id`, un `session_id`, des **token usage stats**, et un **status** (ex: `success`).
* **Affichage console :** après un `prompt` réussi (commit + push), Albert affiche les tokens (prompt/completion/total) et une estimation de coût.

> Le ledger événementiel (`ledger/events.jsonl`) reste la source de vérité pour les événements fins (api_response, file_write, etc.). L'audit ledger (`ledger/audit_log.jsonl`) est un résumé transactionnel orienté comptabilité.

### 1.3 Financial & Operational Reporting (Visibility Gap Closure)
Albert inclut désormais une capacité de **reporting agrégé** pour combler le manque de visibilité sur les tokens et les coûts.

* **Commande CLI :** `report`
* **Source de données :** `ledger/audit_log.jsonl`
* **Sortie console :** un tableau de bord concis (transactions, tokens in/out, coût estimé, chemin du ledger)
* **Tolérance :** si le ledger est absent ou vide, le rapport affiche des zéros (pas de crash).

### 1.4 Traceability Management
Albert applique une gouvernance stricte d’alignement entre trois couches :

1) **Specs (Requirements)** — `specs/`
2) **Code (Implementation)** — `src/`
3) **Impl-Docs (Living Documentation)** — `impl-docs/`

#### 1.4.1 Matrice de Traçabilité = Source de Vérité
Le fichier **`traceability_matrix.md`** (à la racine du projet) est la **Source of Truth** qui relie explicitement :
- un **Req_ID** (Specs),
- les **modules `src/`** concernés,
- la **documentation `impl-docs/`** correspondante,
- et un **statut** (Implemented / Partial / Planned).

### 1.5 Governance: The Trinity Protocol (REQ_CORE_060)
(Section inchangée; voir versions précédentes.)

### 1.6 Safe System Inspection (SSI) — REQ_CORE_050
(Section inchangée; voir versions précédentes.)

### 1.7 Version Control — Git Tolerance / Soft Fail (REQ_CORE_080)
(Section inchangée; voir versions précédentes.)

### 1.8 Autonomous Rebound Protocol (Agent Loop) — REQ_AUTO_010..REQ_AUTO_050
Albert supporte désormais un mode **agent autonome** ("Rebound") permettant au modèle d’enchaîner :

`User → AI → artifacts + next_action → Wrapper executes script → Wrapper feeds output → AI → ... → final response`

#### 1.8.1 Où c’est implémenté
* **Code :** `src/main.py` (fonction `_run_prompt_flow`)
* **Parsing :** `src/artifact_manager.py` via `process_response(..., enable_rebound=True)` qui retourne `(files, next_action)`
* **Exécution sandboxée :** `src/workbench_runner.py` (`WorkbenchRunner`) — strictement limité à `workbench/scripts/`.

#### 1.8.2 next_action (v1)
Le modèle peut inclure un objet JSON `next_action` dans la réponse structurée.

Schéma v1 :
```json
{
  "type": "exec_and_chain",
  "target_script": "workbench/scripts/...",
  "continuation_prompt": "..."
}
```

Règles de sécurité (v1) :
* `type` doit être exactement `exec_and_chain`.
* `target_script` doit être **relatif racine projet** et pointer **strictement** sous `workbench/scripts/`.
* Pas d’exécution shell. Uniquement un script Python via `WorkbenchRunner`.
* Timeout obligatoire (runner).

#### 1.8.3 Boucle Rebound (state machine)
La commande `prompt` exécute maintenant une boucle bornée :
* **MAX_LOOPS = 5** (garde-fou)
* à chaque tour :
  1) appel IA,
  2) écriture artefacts dans `artifacts/<step_id>/...`,
  3) si `next_action` présent : exécution du script demandé (sandbox), capture `stdout/stderr/returncode`,
  4) construction d’un nouveau prompt utilisateur :
     - bloc `System Output` (stdout/stderr/returncode)
     - + `continuation_prompt` fourni par l’IA
  5) nouvel appel IA.

La boucle s’arrête quand `next_action` est absent (réponse finale).

#### 1.8.4 Traceabilité (console + ledger)
* Chaque réponse IA est affichée entre délimiteurs :
  * `[AI_RESPONSE_BEGIN]` ... `[AI_RESPONSE_END]`
  (donc capturée dans `sessions/<date>/transcript.log`).
* Chaque exécution Rebound imprime `STDOUT/STDERR/returncode` en console/transcript.
* Les exécutions intermédiaires sont journalisées dans `ledger/events.jsonl` (action_type: `rebound_exec`, ou `rebound_exec_blocked` en cas de blocage sécurité).

#### 1.8.5 Git (pas de commit prématuré)
Le workflow Git (review/apply → commit → push) reste **uniquement** à la fin, après la réponse finale (quand `next_action` est absent). Les tours intermédiaires Rebound ne déclenchent aucun commit/push.

## 2. Modules Principaux (`src/`)

### 2.1 Configuration (`config.py`)
* **Rôle :** Charge le fichier `project.json` depuis la racine.
* **Classe :** `ConfigLoader`
* **Instance Globale :** `GLOBAL_CONFIG`

### 2.2 Audit & Ledger (`audit.py`)
* **Rôle :** Journalisation structurée pour les machines (JSONL) + Audit transactionnel.

### 2.3 Console & Transcript (`console.py`)
* **Rôle :** Interface Homme-Machine. Capture stdin/stdout.
* **Fichier de sortie :** `sessions/<YYYY-MM-DD>/transcript.log`.

### 2.4 Point d'Entrée / CLI (`main.py`)
* **Exécution :** `python3 -m src.main`
* **Rôle :** Orchestre le démarrage et la boucle d'interaction.

#### 2.4.1 Commandes interactives
Commandes disponibles dans la CLI interactive :
* `prompt` : envoie un prompt/tâche au “cerveau IA” d’Albert et écrit les fichiers dans `artifacts/<step_id>/`.
  * Supporte **Ad-hoc File Injection** via `-f/--file` : `prompt [-f file]`.
  * Supporte `--scope {full,code,specs,minimal}`.
  * **Rebound Protocol :** si l’IA renvoie `next_action`, Albert exécute automatiquement le script demandé (sandbox) et relance l’IA jusqu’à obtention d’une réponse finale.
  * **Traceabilité renforcée :** chaque réponse brute de l’IA est affichée à l’écran.
* `implement` : alias rétro-compatible de `prompt` (déprécié; affiche un message invitant à utiliser `prompt`).
* `test_ai` : envoie une requête minimale à l’IA (sanity check de connectivité).
* `status` : affiche un état Git rapide du dépôt.
* `report` : affiche un rapport agrégé basé sur `ledger/audit_log.jsonl`.
* `help` : affiche l’aide.
* `clear` : efface l’écran via `clear`.

> Note : `exit` / `quit` existent également pour quitter la CLI.

#### 2.4.2 UX : Contexte critique toujours visible (Project Root)
Le prompt CLI affiche en permanence la racine projet.

**Prompt CLI (format) :**
```
[<project_root>]
Command (prompt, implement, exec, test_ai, status, report, help, clear, exit):
```

## 3. Structure des Données
Les sessions sont isolées par date. Le Ledger est global au projet.
