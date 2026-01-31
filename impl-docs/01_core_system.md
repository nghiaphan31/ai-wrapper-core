# Project Albert — Documentation d'Implémentation : Core System
**Version :** 0.1.0 (Itération 1)
**Date :** 2026-01-28

## 1. Vue d'ensemble
**Project Albert** est un outil local-first qui agit comme un *steward* (intendant) rigoureux entre l’Utilisateur et le Modèle IA.

Albert n’est pas un simple "chat" : il orchestre le workflow, écrit les artefacts sur disque (zéro copy-paste), et impose une **traçabilité vérifiable** (transcript + ledger + payloads bruts). Son rôle central est de garantir qu’à tout moment on puisse répondre, preuves à l’appui :
* **qui** a demandé **quoi**, **quand**,
* **quel** modèle a répondu,
* **quels** fichiers ont été produits/modifiés,
* et **où** retrouver l’échange brut correspondant.

Le noyau (Core) gère l'initialisation, la configuration et, surtout, la traçabilité des opérations. Il fournit également une boucle CLI interactive et les points d’entrée de workflow (`test_ai`, `implement`).

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
* **Objectif :** lier explicitement une action utilisateur (`implement`) à un `step_id`, un `session_id`, des **token usage stats**, et un **status** (ex: `success`).
* **Affichage console :** après un `implement` réussi (commit + push), Albert affiche les tokens (prompt/completion/total) et une estimation de coût.

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
En complément, Albert effectue un contrôle **best-effort** au runtime dans le flux `implement`.

* **Où :** `src/main.py` (commande `implement`)
* **Logique :** après génération des artefacts, Albert scanne les chemins de fichiers générés.
  * si des changements `src/` sont détectés **sans** présence de `impl-docs/` et/ou `specs/` dans la même session, Albert affiche un bloc d’avertissement.

Ce mécanisme ne bloque pas l’exécution (pas de hard stop), car certaines sessions peuvent volontairement produire du code « en avance » avant retrofit. L’objectif est d’éviter les dérives silencieuses.

#### 1.5.4 Philosophie “Retrofit” (Reality → Theory)
Le protocole assume une philosophie explicite :

*La réalité (Code) doit alimenter la théorie (Specs).* 

Quand le code révèle un besoin non spécifié, on **retrofit** les specs : ajout/clarification d’exigences, mise à jour du registre, et mise à jour de la matrice de traçabilité.

> Corollaire : une doc d’implémentation fidèle (impl-docs) est le miroir nécessaire pour diagnostiquer et corriger tout écart Specs ↔ Code.

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
  * Objectif : empêcher l’injection shell, le piping vers des commandes non allowlistées, et les écritures via redirection.
* **Pas de `shell=True` :** exécution via `subprocess.run(tokens, capture_output=True, text=True)`.
* **Parsing robuste :** split via `shlex.split`.
* **Blocage implicite des commandes destructrices :** `rm`, `mv`, `chmod`, etc. ne sont pas allowlistées, donc refusées.

#### 1.6.4 Intégration dans le System Prompt
Le prompt système (dans `src/main.py`) informe explicitement le modèle :
> “You have access to a `run_safe_command` tool to inspect the file system (ls, tree) and git status. Use this to verify reality before making assumptions.”

**Remarque :** l’outillage SSI est un mécanisme de sécurité et d’observation. Il ne remplace pas la gouvernance (Trinity Protocol) ni la validation humaine pour les actions à impact.

### 1.7 Version Control — Git Tolerance / Soft Fail (REQ_CORE_080)
Albert applique une politique de **tolérance Git** pour éviter que le workflow ne casse sur un cas courant : `git commit` sans changements.

#### 1.7.1 Bug ciblé (CRITICAL FIX)
Dans certains environnements, `git commit` peut retourner :
* `returncode = 1`
* avec un message du type **"nothing to commit"** ou **"working tree clean"**.

Si ce code de retour est traité comme une erreur fatale (exception), la boucle d’exécution (notamment la Tool Execution Loop / audits) peut être interrompue prématurément.

#### 1.7.2 Règle implémentée (Soft Fail)
**REQ_CORE_080 :**
* Les commandes Git sont exécutées avec `check=False`.
* Si `returncode == 0` : succès.
* Si `returncode == 1` ET que `stdout` contient **"nothing to commit"** ou **"working tree clean"** :
  * Albert logue un message d’info/warning (ex: `Git: Nothing to commit. Proceeding...`),
  * et **force un succès** (soft success) pour ne pas casser le workflow.
* Sinon : erreur réelle → Albert logue une erreur et remonte l’échec.

#### 1.7.3 Module d’implémentation
* **Code :** `src/utils.py`
  * `run_git_command(...)` (tolerance centralisée)
  * `git_commit_resilient(...)`
  * `git_run_ok(...)`
  * `git_add_force_tracked_paths(...)`

## 2. Modules Principaux (`src/`)

### 2.1 Configuration (`config.py`)
* **Rôle :** Charge le fichier `project.json` depuis la racine.
* **Classe :** `ConfigLoader`
* **Instance Globale :** `GLOBAL_CONFIG`
* **Comportement :** Lève une erreur critique si le JSON est malformé ou absent.

#### 2.1.1 Centralisation du Pricing (PRICING_RATES)
La grille de pricing utilisée pour estimer les coûts est centralisée dans la configuration globale.

* **Emplacement :** `GLOBAL_CONFIG.PRICING_RATES`
* **Format :**
  ```python
  {
    "input_per_1m": 2.50,
    "output_per_1m": 10.00
  }
  ```
* **Interprétation :** USD par 1 million de tokens.
* **But :** supprimer tout hardcoding des prix dans la logique (calculs de coût cohérents dans tout le projet).

> Note : ce pricing est une **estimation locale** (non facturante), destinée au pilotage opérationnel.

### 2.2 Audit & Ledger (`audit.py`)
* **Rôle :** Journalisation structurée pour les machines (JSONL) + Audit transactionnel.

#### 2.2.1 Ledger événementiel
* **Fichier de sortie :** `ledger/events.jsonl` (Append-Only).
* **Champs clés :** `event_uuid`, `actor`, `action_type`, `artifacts_links`, `payload_ref`.
* **Méthode :** `log_event(...)`.

#### 2.2.2 Audit Ledger (transactions)
* **Fichier de sortie :** `audit_log.jsonl` (Append-Only).
* **Méthode :** `log_transaction(session_id, user_instruction, step_id, usage_stats, status)`.
* **Contenu :** timestamp ISO8601 UTC + tokens + statut.

* **Instance Globale :** `GLOBAL_LEDGER`.

#### 2.2.3 Reporting (agrégation)
* **Méthode :** `generate_report(timeframe='all')`
* **Timeframes supportés :**
  * `all` : toutes les transactions
  * `today` : transactions dont `session_id == YYYY-MM-DD` du jour
  * `session` : alias actuel de `today` (même logique)
* **Agrégats :**
  * total transactions
  * total prompt tokens (input)
  * total completion tokens (output)
  * coût estimé (via `GLOBAL_CONFIG.PRICING_RATES`)

### 2.3 Console & Transcript (`console.py`)
* **Rôle :** Interface Homme-Machine. Capture stdin/stdout.
* **Fichier de sortie :** `sessions/<YYYY-MM-DD>/transcript.log`.
* **Fonctionnement :**
    * Remplace `print()` par `GLOBAL_CONSOLE.print()` -> Écrit écran + log avec prefix `[WRAPPER]`.
    * Remplace `input()` par `GLOBAL_CONSOLE.input()` -> Capture saisie + log avec prefix `[USER]`.

### 2.4 Point d'Entrée / CLI (`main.py`)
* **Exécution :** `python3 -m src.main` (requis pour la résolution des packages).
* **Rôle :** Orchestre le démarrage et la boucle d'interaction.
* **Boucle interactive :** attend une commande utilisateur et route vers les actions.

#### 2.4.1 Commandes interactives
Commandes disponibles dans la CLI interactive :
* `implement` : exécute une tâche d’implémentation via l’IA et écrit les fichiers dans `artifacts/<step_id>/`.
  * Supporte **Ad-hoc File Injection** via `-f/--file` : `implement [-f file]`.
* `test_ai` : envoie une requête minimale à l’IA (sanity check de connectivité).
* `status` : affiche un état Git rapide du dépôt (changements en attente + dernier commit).
* `report` : affiche un rapport agrégé (transactions, tokens, coût estimé) basé sur `audit_log.jsonl`.
* `help` : affiche l’aide.
* `clear` : efface l’écran via `clear`.

> Note : `exit` / `quit` existent également pour quitter la CLI, mais ne font pas partie des commandes « cœur » du workflow.

#### 2.4.2 UX : Contexte critique toujours visible (Project Root)
Pour éviter toute confusion sur le projet actif (notamment quand plusieurs projets sont ouverts dans différents terminaux), Albert affiche **en permanence la racine projet** au moment où l’utilisateur doit saisir une commande.

**Prompt CLI (format) :**
```
[<project_root>]
Command (implement, test_ai, status, report, help, clear, exit):
```

Ainsi, le **Project Root** est toujours visible à côté du curseur au point de décision.

#### 2.4.3 Nano Integration (multi-line input)
La commande `implement` supporte une saisie multi-ligne via **Nano Integration**.

* **Fonction :** `get_input_from_editor(prompt_text: str) -> str`
* **Principe :** au lieu d’un `input()` mono-ligne, le wrapper ouvre l’éditeur `nano` sur un fichier temporaire, puis relit le contenu complet du fichier à la fermeture.
* **Objectif :** permettre des prompts longs/multi-lignes de façon plus sûre (notamment pour le copy-paste de gros blocs), en réduisant les erreurs de terminal et les troncatures.

> Prérequis : `nano` doit être disponible sur le système.

#### 2.4.4 Politique “Zero Waste” (annulation immédiate si entrée vide)
Le wrapper applique une politique **Zero Waste** sur `implement` :
* si l’instruction saisie est vide (ou uniquement des espaces), l’action est **annulée immédiatement**,
* le wrapper **ne construit pas** le contexte projet,
* le wrapper **n’appelle pas** l’API IA,
* aucun artefact n’est généré.

Cela évite de consommer des tokens et du temps sur des invocations accidentelles.

#### 2.4.5 Ad-hoc File Injection (Transient Context via `-f/--file`)
Albert supporte l’injection de fichiers locaux **à la volée** pour une requête `implement`, sans copier-coller dans le terminal.

**Syntaxe :**
* `implement -f path/to/file`
* `implement -f file1 -f file2`
* `implement --file path/to/file`

**Comportement :**
1. Le wrapper lit les fichiers attachés **au runtime** (au moment de l’exécution de la commande).
2. Le contenu est injecté dans l’instruction envoyée au modèle en tant que **Transient Context**.
3. Chaque fichier est encapsulé avec un délimiteur explicite :

```
--- ATTACHED FILE: <filename> ---
<content>
```

4. Le wrapper affiche une confirmation par fichier (ex: `📎 Attached: error.log`).

**Propriété clé (non-persistance) :**
* Ce mécanisme injecte du contexte **uniquement pour la requête courante**.
* Les fichiers attachés ne sont **pas** copiés automatiquement dans `specs/`, `impl-docs/`, `src/` ou `notes/`.

#### 2.4.6 Interactive Review Mode (Diff View + Validation Atomique)
La commande `implement` inclut désormais un **Interactive Review Mode** qui sert de garde-fou avant d’impacter le dépôt Git.

**Objectif :** transformer l’étape “validation humaine” en une validation **explicite, visuelle et atomique**, basée sur une vue diff.

##### A) Diff View (validation par comparaison)
Après génération des fichiers par l’IA dans `artifacts/<step_id>/`, Albert :
1. parcourt tous les fichiers générés dans ce dossier,
2. calcule pour chacun la **destination réelle** dans le projet en retirant le préfixe `artifacts/<step_id>/` (ex: `artifacts/step_123/src/x.py` -> `src/x.py`),
3. affiche un **unified diff** entre :
   * l’état actuel du fichier destination (si existant), et
   * le nouveau contenu produit dans l’artefact.

##### B) UX : Contexte critique toujours visible (Filename)
Lors de la confirmation, Albert affiche **le chemin du fichier destination (relatif au Project Root)** directement dans le prompt.

**Prompt de confirmation (format) :**
```
[<relative_destination_path>] Apply this change? [y/n/abort]:
```

##### C) Validation atomique (Accept-All / Abort-All)
La validation est **atomique** :
* l’utilisateur doit accepter **tous** les changements proposés (fichier par fichier),
* si l’utilisateur refuse un seul fichier (`n` / `abort`), alors **aucun fichier n’est copié** vers les destinations finales.

##### D) Auto-merge + Auto-commit + Auto-push (en cas de succès)
Si (et seulement si) la revue interactive est validée pour **tous** les fichiers :
1. Albert **copie** l’ensemble des fichiers depuis `artifacts/<step_id>/...` vers leurs chemins cibles dans le projet (merge local).
2. Albert exécute ensuite la séquence Git suivante :
   * `git add -f -- project.json src specs impl-docs notes`
   * `git commit -m <message>`
     * si Git répond “nothing to commit / working tree clean”, Albert loggue un warning et continue (REQ_CORE_080)
   * `git push`

3. Albert écrit une entrée dans `audit_log.jsonl` (transaction `success`) incluant les tokens.
4. Albert affiche en console : **Token Usage** et **Estimated Cost**.

**Résultat :** une exécution `implement` validée aboutit à une modification **appliquée**, **commitée** et **poussée** automatiquement.

> Note importante : l’affichage diff et la validation atomique constituent la barrière de sécurité qui autorise ensuite l’auto-merge/auto-push.

#### 2.4.7 Commande `status` (état Git rapide)
La commande `status` fournit une vue concise de l'état du dépôt.

**Comportement :**
1. affiche l’en-tête : `--- Repository Status ---`,
2. exécute `git status -s` pour lister les changements en attente,
3. exécute `git log -1 --format="%h - %s (%cr)"` pour afficher le dernier commit,
4. si Git n’est pas disponible (ex: binaire absent) ou si la commande échoue (ex: dossier non-initialisé), Albert affiche un message d'erreur **amical** (avec détails techniques optionnels).

#### 2.4.8 Commande `report` (dashboard)
La commande `report` affiche un tableau de bord agrégé basé sur `audit_log.jsonl`.

**Format (exemple) :**
```
--- 📊 Project Report ---
Total Transactions: X
Tokens: In: X,xxx / Out: Y,yyy
Estimated Cost: $Z.ZZZZ
Ledger File: [path]
```

## 2.5 The 'albert' Launcher
Le projet fournit un script Bash portable `albert` à la racine du dépôt, conçu comme **launcher universel** pour exécuter la CLI sans dépendre du répertoire courant.

* **Portabilité & “symlink-proof” :** le script résout son propre chemin réel via `realpath`, ce qui garantit un comportement correct même si `albert` est appelé via un lien symbolique.
* **Résolution automatique de la racine :** à partir de ce chemin résolu, il déduit la racine du projet.
* **Auto-venv :** le launcher active automatiquement l’environnement virtuel `.venv` (si présent / attendu) avant de lancer la CLI.
* **Lancement standard :** exécute la CLI via `python -m src.main`.
* **Appel global possible :** si `albert` est lié dans le `PATH` (par exemple via un symlink vers `/usr/local/bin/albert`), la commande `albert` devient utilisable globalement, tout en pointant toujours vers la bonne racine projet.

## 3. Structure des Données
Les sessions sont isolées par date. Le Ledger est global au projet.
