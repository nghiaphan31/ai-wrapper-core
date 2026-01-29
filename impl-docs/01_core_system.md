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

### 1.1 Audit Ledger System (Traceabilité + Coûts)
En plus du ledger événementiel (machine-level), Albert maintient désormais un **Audit Ledger** orienté "transactions" pour assurer une traçabilité directe des opérations et des coûts.

* **Fichier :** `audit_log.jsonl` à la racine du projet (append-only)
* **Objectif :** lier explicitement une action utilisateur (`implement`) à un `step_id`, un `session_id`, des **token usage stats**, et un **status** (ex: `success`).
* **Affichage console :** après un `implement` réussi (commit + push), Albert affiche les tokens (prompt/completion/total) et une estimation de coût.

> Le ledger événementiel (`ledger/events.jsonl`) reste la source de vérité pour les événements fins (api_response, file_write, etc.). L'audit ledger (`audit_log.jsonl`) est un résumé transactionnel orienté comptabilité.

## 2. Modules Principaux (`src/`)

### 2.1 Configuration (`config.py`)
* **Rôle :** Charge le fichier `project.json` depuis la racine.
* **Classe :** `ConfigLoader`
* **Instance Globale :** `GLOBAL_CONFIG`
* **Comportement :** Lève une erreur critique si le JSON est malformé ou absent.

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

* **Instance Globale :** `GLOBAL_LEDGER`

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
* `test_ai` : envoie une requête minimale à l’IA (sanity check de connectivité).
* `status` : affiche un état Git rapide du dépôt (changements en attente + dernier commit).
* `help` : affiche l’aide.
* `clear` : efface l’écran via `clear`.

> Note : `exit` / `quit` existent également pour quitter la CLI, mais ne font pas partie des commandes « cœur » du workflow.

#### 2.4.2 Nano Integration (multi-line input)
La commande `implement` supporte une saisie multi-ligne via **Nano Integration**.

* **Fonction :** `get_input_from_editor(prompt_text: str) -> str`
* **Principe :** au lieu d’un `input()` mono-ligne, le wrapper ouvre l’éditeur `nano` sur un fichier temporaire, puis relit le contenu complet du fichier à la fermeture.
* **Objectif :** permettre des prompts longs/multi-lignes de façon plus sûre (notamment pour le copy-paste de gros blocs), en réduisant les erreurs de terminal et les troncatures.
* **Flux :**
  1) création d’un fichier temporaire (`tempfile.NamedTemporaryFile(..., delete=False)`),
  2) ouverture de `nano` (`subprocess.run(["nano", tf_path], check=False)`),
  3) lecture du contenu du fichier,
  4) suppression du fichier temporaire.

> Prérequis : `nano` doit être disponible sur le système.

#### 2.4.3 Politique “Zero Waste” (annulation immédiate si entrée vide)
Le wrapper applique une politique **Zero Waste** sur `implement` :
* si l’instruction saisie est vide (ou uniquement des espaces), l’action est **annulée immédiatement**,
* le wrapper **ne construit pas** le contexte projet,
* le wrapper **n’appelle pas** l’API IA,
* aucun artefact n’est généré.

Cela évite de consommer des tokens et du temps sur des invocations accidentelles.

#### 2.4.4 Interactive Review Mode (Diff View + Validation Atomique)
La commande `implement` inclut désormais un **Interactive Review Mode** qui sert de garde-fou avant d’impacter le dépôt Git.

**Objectif :** transformer l’étape “validation humaine” en une validation **explicite, visuelle et atomique**, basée sur une vue diff.

##### A) Diff View (validation par comparaison)
Après génération des fichiers par l’IA dans `artifacts/<step_id>/`, Albert :
1. parcourt tous les fichiers générés dans ce dossier,
2. calcule pour chacun la **destination réelle** dans le projet en retirant le préfixe `artifacts/<step_id>/` (ex: `artifacts/step_123/src/x.py` -> `src/x.py`),
3. affiche un **unified diff** entre :
   * l’état actuel du fichier destination (si existant), et
   * le nouveau contenu produit dans l’artefact.

Cette vue diff est la preuve locale et immédiate de ce qui va changer.

##### B) Validation atomique (Accept-All / Abort-All)
La validation est **atomique** :
* l’utilisateur doit accepter **tous** les changements proposés (fichier par fichier),
* si l’utilisateur refuse un seul fichier (`n` / `abort`), alors **aucun fichier n’est copié** vers les destinations finales.

> Conséquence : pas d’état “partiellement appliqué” via `implement`. Soit tout passe, soit rien ne passe.

##### C) Auto-merge + Auto-commit + Auto-push (en cas de succès)
Si (et seulement si) la revue interactive est validée pour **tous** les fichiers :
1. Albert **copie** l’ensemble des fichiers depuis `artifacts/<step_id>/...` vers leurs chemins cibles dans le projet (merge local).
2. Albert exécute ensuite la séquence Git suivante :
   * `git add .`
   * `git commit -m <message>` (le message est dérivé de l’instruction utilisateur)
   * `git push`

3. Albert écrit une entrée dans `audit_log.jsonl` (transaction `success`) incluant les tokens.
4. Albert affiche en console : **Token Usage** et **Estimated Cost**.

**Résultat :** une exécution `implement` validée aboutit à une modification **appliquée**, **commitée** et **poussée** automatiquement.

> Note importante : l’affichage diff et la validation atomique constituent la barrière de sécurité qui autorise ensuite l’auto-merge/auto-push.

#### 2.4.5 Commande `status` (état Git rapide)
La commande `status` fournit une vue concise de l'état du dépôt.

**Comportement :**
1. affiche l’en-tête : `--- Repository Status ---`,
2. exécute `git status -s` pour lister les changements en attente,
3. exécute `git log -1 --format="%h - %s (%cr)"` pour afficher le dernier commit,
4. si Git n’est pas disponible (ex: binaire absent) ou si la commande échoue (ex: dossier non-initialisé), Albert affiche un message d’erreur **amical** (avec détails techniques optionnels).

## 2.5 The 'albert' Launcher
Le projet fournit un script Bash portable `albert` à la racine du dépôt, conçu comme **launcher universel** pour exécuter la CLI sans dépendre du répertoire courant.

* **Portabilité & “symlink-proof” :** le script résout son propre chemin réel via `realpath`, ce qui garantit un comportement correct même si `albert` est appelé via un lien symbolique.
* **Résolution automatique de la racine :** à partir de ce chemin résolu, il déduit la racine du projet.
* **Auto-venv :** le launcher active automatiquement l’environnement virtuel `.venv` (si présent / attendu) avant de lancer la CLI.
* **Lancement standard :** exécute la CLI via `python -m src.main`.
* **Appel global possible :** si `albert` est lié dans le `PATH` (par exemple via un symlink vers `/usr/local/bin/albert`), la commande `albert` devient utilisable globalement, tout en pointant toujours vers la bonne racine projet.

## 3. Structure des Données
Les sessions sont isolées par date. Le Ledger est global au projet.
