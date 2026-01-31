# Project Albert — Documentation d'Implémentation : Core System
**Version :** 0.1.2 (Itération 1)
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

Exemple :
* `workbench/scripts/structural_audit.py` : script exécutable manuellement pour imprimer l’arborescence et lister les dossiers vides.

### 1.2 Audit Ledger System (Traceabilité + Coûts)
En plus du ledger événementiel (machine-level), Albert maintient désormais un **Audit Ledger** orienté "transactions" pour assurer une traçabilité directe des opérations et des coûts.

* **Fichier :** `audit_log.jsonl` à la racine du projet (append-only)
* **Objectif :** lier explicitement une action utilisateur (`prompt`) à un `step_id`, un `session_id`, des **token usage stats**, et un **status** (ex: `success`).
* **Affichage console :** après un `prompt` réussi (commit + push), Albert affiche les tokens (prompt/completion/total) et une estimation de coût.

> Le ledger événementiel (`ledger/events.jsonl`) reste la source de vérité pour les événements fins (api_response, file_write, etc.). L'audit ledger (`audit_log.jsonl`) est un résumé transactionnel orienté comptabilité.

### 1.3 Financial & Operational Reporting (Visibility Gap Closure)
Albert inclut désormais une capacité de **reporting agrégé** pour combler le manque de visibilité sur les tokens et les coûts.

* **Commande CLI :** `report`
* **Source de données :** `audit_log.jsonl`
* **Sortie console :** un tableau de bord concis (transactions, tokens in/out, coût estimé, chemin du ledger)
* **Tolérance :** si le ledger est absent ou vide, le rapport affiche des zéros (pas de crash).

### 1.4 Traceability Management
Albert applique une gouvernance stricte d’alignement entre trois couches :

1) **Specs (Requirements)** — `specs/`
   * source des exigences (Req_ID)
   * définit le *quoi/pourquoi* (baseline)

2) **Code (Implementation)** — `src/`
   * implémente le *comment*
   * chaque fonctionnalité significative doit pouvoir être reliée à un ou plusieurs Req_ID

3) **Impl-Docs (Living Documentation)** — `impl-docs/`
   * décrit l’état réel du code (ce qui est effectivement codé)
   * sert de “carte” opérationnelle : modules, flux, formats de logs, localisation des artefacts

#### 1.4.1 Matrice de Traçabilité = Source de Vérité
Le fichier **`traceability_matrix.md`** (à la racine du projet) est la **Source of Truth** qui relie explicitement :
- un **Req_ID** (Specs),
- les **modules `src/`** concernés,
- la **documentation `impl-docs/`** correspondante,
- et un **statut** (Implemented / Partial / Planned).

#### 1.4.2 Règle de maintenance (cycle de vie)
À chaque changement significatif :
- si du code est modifié/ajouté dans `src/`, la doc correspondante **doit** être mise à jour dans `impl-docs/` (Definition of Done),
- et la **ligne correspondante** dans `traceability_matrix.md` **doit** être mise à jour (statut + liens).

#### 1.4.3 Gestion des écarts
- Si une fonctionnalité est implémentée mais **sans Req_ID**, il faut **mettre à jour les Specs d’abord** (ajout au registre d’exigences) avant de considérer la feature « conforme ». Cela maintient l’alignement *Specs ↔ Code ↔ Impl-Docs*.

### 1.5 Governance: The Trinity Protocol (REQ_CORE_060)
Albert institutionnalise une gouvernance stricte appelée **The Trinity Protocol** : l’alignement permanent entre **Specs**, **Code**, et **Docs**.

#### 1.5.1 Principe
Toute modification d’une couche (**Specs**, **Code**, ou **Docs**) DOIT déclencher une évaluation des deux autres.

* **Code Change (`src/`)** → nécessite une mise à jour correspondante dans `impl-docs/` et peut nécessiter un retrofit dans `specs/`.
* **Spec Change (`specs/`)** → nécessite une implémentation dans `src/` et une mise à jour dans `impl-docs/`.
* **Doc Change (`impl-docs/`)** → DOIT refléter le comportement réel du code et les exigences des specs.

#### 1.5.2 Mécanisme 1 : Enforcement via System Prompt
Le système renforce ce protocole au niveau du modèle via le **System Prompt**.

* **Où :** `src/ai_client.py`
* **Mécanisme :** le client construit le prompt système final en **appendant** un bloc obligatoire :
  * “TRINITY PROTOCOL ENABLED …”
  * règles : ne jamais produire du code sans évaluer `impl-docs/`, ne jamais implémenter une feature sans évaluer `specs/`, et obligation d’évaluer les trois couches.

Objectif : rendre l’IA *steward* de l’écosystème, pas seulement générateur de fichiers.

#### 1.5.3 Mécanisme 2 : Runtime Warnings (best-effort)
En complément, Albert effectue un contrôle **best-effort** au runtime dans le flux `prompt`.

* **Où :** `src/main.py` (commande `prompt`)
* **Logique :** après génération des artefacts, Albert scanne les chemins de fichiers générés.
  * si des changements `src/` sont détectés **sans** présence de `impl-docs/` et/ou `specs/` dans la même session, Albert affiche un bloc d’avertissement.

Ce mécanisme ne bloque pas l’exécution (pas de hard stop), car certaines sessions peuvent volontairement produire du code « en avance » avant retrofit. L’objectif est d’éviter les dérives silencieuses.

### 1.6 Safe System Inspection (SSI) — REQ_CORE_050
Albert inclut un mécanisme de **Safe System Inspection (SSI)** permettant au système (et donc à l’IA via le wrapper) d’effectuer des **observations empiriques** de l’environnement local (Ground Truth) sans mettre en danger la stabilité du système.

**But :** autoriser des commandes **read-only** (inspection) afin de vérifier la réalité (structure de projet, état git, lecture de fichiers) avant de faire des hypothèses.

#### 1.6.1 Module
* **Code :** `src/system_tools.py`
* **Classe :** `SafeCommandRunner`
* **Méthode :** `run_safe_command(command_str)`

#### 1.6.2 Allowlist (commandes autorisées)
Allowlist stricte (préfixes exacts) :
* `tree`
* `ls`
* `dir`
* `git status`
* `git log`
* `git diff`
* `find`
* `grep`
* `cat`

> Les entrées multi-mots (ex: `git status`) doivent matcher le **préfixe exact** des tokens (`["git","status", ...]`).

#### 1.6.3 Contraintes de sécurité
SSI applique des garde-fous conservateurs :
* **Interdiction des opérateurs de chaînage / redirection :** rejet si la commande contient `&&`, `;`, `|`, `>`.
* **Pas de `shell=True` :** exécution via `subprocess.run(tokens, capture_output=True, text=True)`.
* **Parsing robuste :** split via `shlex.split`.
* **Blocage implicite des commandes destructrices :** `rm`, `mv`, `chmod`, etc. ne sont pas allowlistées, donc refusées.

### 1.7 Version Control — Git Tolerance / Soft Fail (REQ_CORE_080)
Albert applique une politique de **tolérance Git** pour éviter que le workflow ne casse sur un cas courant : `git commit` sans changements.

(Section inchangée; voir `impl-docs/01_core_system.md` version précédente.)

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
  * **Traceabilité renforcée :** la réponse brute de l’IA est affichée à l’écran et donc capturée dans `sessions/.../transcript.log`.
* `implement` : alias rétro-compatible de `prompt` (déprécié; affiche un message invitant à utiliser `prompt`).
* `test_ai` : envoie une requête minimale à l’IA (sanity check de connectivité).
* `status` : affiche un état Git rapide du dépôt.
* `report` : affiche un rapport agrégé basé sur `audit_log.jsonl`.
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
